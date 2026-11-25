#!/usr/bin/env node
// Dedicated headless Chrome CDP transport for ScaleExecution. Never attaches to user Chrome.
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { spawn } from 'node:child_process';
import readline from 'node:readline';
import http from 'node:http';
import { pathToFileURL } from 'node:url';
let chrome, ws, proxy, targetOrigin, pageUrl, sequence = 0, pending = new Map(), profileDir, evidenceDir, fixturesDir, fixtureManifest, typedInputs = new Map(), proxyBlockedRequests = 0;
let startupController=null, startupSignal=null, closePromise=null, chromeSpawnFailed=false;
let lifecycleInitialized=false, proxyListenPending=false;
const proxyConnections=new Set();
const hash = b => crypto.createHash('sha256').update(b).digest('hex');
export const DRIVER_DEADLINES_MS=Object.freeze({start:60000,act:80000,reply:5000});
export const CDP_DEADLINES_MS=Object.freeze({default:10000,screenshot:30000});
// The parent owns this Node process group. Every child inherits that group;
// there is no detached child and no attachment to an existing browser.
export async function runBounded(operation,timeoutMs,code,signal) {
  const controller=new AbortController();
  const abort=()=>controller.abort(signal?.reason||new Error(code));
  if(signal?.aborted)abort();
  else signal?.addEventListener('abort',abort,{once:true});
  let rejectAbort;
  const aborted=new Promise((resolve,reject)=>{rejectAbort=reject;});
  const stop=()=>rejectAbort(controller.signal.reason instanceof Error
    ?controller.signal.reason:new Error(code));
  controller.signal.addEventListener('abort',stop,{once:true});
  const timer=setTimeout(()=>controller.abort(new Error(code)),timeoutMs);
  try {
    if(controller.signal.aborted)throw controller.signal.reason;
    return await Promise.race([
      Promise.resolve().then(()=>{controller.signal.throwIfAborted();return operation(controller.signal);}),aborted,
    ]);
  } finally {
    clearTimeout(timer);signal?.removeEventListener('abort',abort);
    controller.signal.removeEventListener('abort',stop);
  }
}
const startupIO=(operation,signal)=>runBounded(operation,DRIVER_DEADLINES_MS.start,'browser_start_timeout',signal);
const safeDir = async (p,signal) => {
  if(!path.isAbsolute(p))throw new Error('private_directory');
  const real=await startupIO(()=>fs.promises.realpath(p),signal);
  const stat=await startupIO(()=>fs.promises.stat(p),signal);
  if(real!==p||!stat.isDirectory()||(stat.mode&0o077))throw new Error('private_directory');
  return p;
};
export async function validateFixtureFiles(manifest,directory,signal,io=fs.promises,
    {timeoutMs=DRIVER_DEADLINES_MS.start,code='browser_start_timeout'}={}) {
  const read=operation=>runBounded(operation,timeoutMs,code,signal);
  for(const row of manifest.files) {
    signal?.throwIfAborted();
    if(!row||typeof row.name!=='string'||path.basename(row.name)!==row.name
        ||!/^[a-zA-Z0-9._-]+$/.test(row.name)||!/^[a-f0-9]{64}$/.test(row.sha256)
        ||!Number.isSafeInteger(row.bytes)||row.bytes<0||row.bytes>134217729)
      throw new Error('fixture_manifest_entry');
    const filename=path.join(directory,row.name);
    const stat=await read(()=>io.lstat(filename));
    const real=await read(()=>io.realpath(filename));
    if(!stat.isFile()||stat.isSymbolicLink()||real!==filename||stat.size!==row.bytes)
      throw new Error('fixture_integrity');
    const bytes=await read(inner=>io.readFile(filename,{signal:inner}));
    if(bytes.length!==row.bytes||hash(bytes)!==row.sha256)throw new Error('fixture_integrity');
  }
}
export class ActionBudget {
  constructor({timeoutMs=DRIVER_DEADLINES_MS.act,record=async()=>{},now=()=>performance.now()}={}) {
    this.timeoutMs=timeoutMs;this.record=record;this.now=now;this.active=null;this.poisoned=false;
  }
  check() {
    const active=this.active;
    if(!active)return;
    if(this.now()>=active.deadline)active.controller.abort(new Error('browser_action_timeout'));
    active.signal?.throwIfAborted();active.controller.signal.throwIfAborted();
  }
  abort() {this.active?.controller.abort(new Error('browser_action_aborted'));}
  get signal() {return this.active?.signal;}
  async phase(phase,extra={}) {
    this.check();
    const active=this.active;
    if(!active)return;
    const now=this.now(),previous=active.phase;
    const detail={command_id:active.commandId,action:active.tool,action_phase:phase,
      elapsed_ms:Math.round(now-active.started),previous_phase:previous,
      previous_phase_ms:Math.round(now-active.phaseStarted),...extra};
    active.phase=phase;active.phaseStarted=now;
    await this.record('action_phase',detail);this.check();
  }
  async run(commandId,tool,operation) {
    if(this.poisoned)throw new Error('browser_action_transport_uncertain');
    if(this.active)throw new Error('browser_action_already_running');
    const started=this.now(),controller=new AbortController();
    const active={commandId,tool,started,deadline:started+this.timeoutMs,controller,
      signal:null,phase:'accepted',phaseStarted:started};
    this.active=active;
    try {
      return await runBounded(async signal=>{
        active.signal=signal;
        await this.phase('started');
        const result=await operation(this);
        this.check();await this.phase('completed');return result;
      },this.timeoutMs,'browser_action_timeout',controller.signal);
    }catch(error) {
      this.poisoned=active.signal?.aborted===true||controller.signal.aborted
        ||this.now()>=active.deadline||String(error?.message).startsWith('cdp_timeout:');
      if(this.poisoned&&!controller.signal.aborted)controller.abort(new Error('browser_action_aborted'));
      try {await this.record('action_failed',{command_id:commandId,action:tool,
        action_phase:active.phase,elapsed_ms:Math.round(this.now()-started),
        error:String(error?.message||'browser_action_failed').slice(0,120),channel_poisoned:this.poisoned});}catch{}
      throw error;
    }finally {
      // Keep the aborted signal after timeout: a late asynchronous read/write
      // must never regain permission to dispatch a browser action.
      if(!this.poisoned)this.active=null;
    }
  }
}
const actionBudget=new ActionBudget({record:lifecycle});
export async function writeCaptureBytes(directory,name,bytes,signal,io=fs.promises) {
  if(typeof name!=='string'||path.basename(name)!==name||!/^browser-\d+\.png$/.test(name)
      ||!Buffer.isBuffer(bytes))throw new Error('capture_path_invalid');
  return await runBounded(async inner=>{
    let handle;
    try {
      handle=await io.open(path.join(directory,name),'wx',0o600);
      // open() itself is not cancellable. A late exclusive open is closed
      // without writing, never admitted as a completed capture or retried.
      inner.throwIfAborted();
      const before=await handle.stat();inner.throwIfAborted();
      if(!before.isFile()||(before.mode&0o077))throw new Error('capture_permissions');
      await handle.writeFile(bytes,{signal:inner});inner.throwIfAborted();
      const after=await handle.stat();inner.throwIfAborted();
      if(after.size!==bytes.length||(after.mode&0o077))throw new Error('capture_write_unconfirmed');
      return {path:name,sha256:hash(bytes)};
    }finally {if(handle)await handle.close();}
  },DRIVER_DEADLINES_MS.act,'browser_action_timeout',signal);
}
export async function writeReplyOnce(stream,packet,{timeoutMs=DRIVER_DEADLINES_MS.reply}={}) {
  const bytes=JSON.stringify(packet)+'\n';
  await runBounded(()=>new Promise((resolve,reject)=>{
    stream.write(bytes,error=>error?reject(error):resolve());
  }),timeoutMs,'browser_reply_flush_timeout');
  return Buffer.byteLength(bytes);
}
export async function fetchJsonBounded(url,{signal,timeoutMs=5000,fetcher=fetch}={}) {
  return await runBounded(async inner=>{
    const response=await fetcher(url,{signal:inner,redirect:'error'});
    if(!response.ok)throw new Error('cdp_discovery_http');
    return await response.json();
  },timeoutMs,'cdp_discovery_timeout',signal);
}
export async function openSocketBounded(socket,{signal,timeoutMs=5000}={}) {
  let opened,failed,closed;
  const opening=new Promise((resolve,reject)=>{
    opened=()=>resolve();failed=()=>reject(new Error('cdp_websocket_error'));
    closed=()=>reject(new Error('cdp_websocket_closed_before_open'));
    socket.addEventListener('open',opened,{once:true});
    socket.addEventListener('error',failed,{once:true});
    socket.addEventListener('close',closed,{once:true});
  });
  // A parent abort can win before runBounded invokes its operation. The
  // disposal close event must still have a rejection observer in that case.
  void opening.catch(()=>{});
  try {await runBounded(()=>opening,timeoutMs,'cdp_websocket_open_timeout',signal);}
  catch(error){try{socket.close();}catch{}throw error;}
  finally {
    socket.removeEventListener('open',opened);socket.removeEventListener('error',failed);
    socket.removeEventListener('close',closed);
  }
}
export function childHasExited(child) {
  return !child||(child.exitCode!==null&&child.exitCode!==undefined)
    ||(child.signalCode!==null&&child.signalCode!==undefined);
}
function waitChildExit(child,timeoutMs,signalName) {
  if(childHasExited(child))return Promise.resolve(true);
  return new Promise(resolve=>{
    let timer;
    const finish=value=>{clearTimeout(timer);child.removeListener('exit',exited);resolve(value);};
    const exited=()=>finish(true);
    child.once('exit',exited);
    timer=setTimeout(()=>finish(childHasExited(child)),timeoutMs);
    // Subscribe before signalling: a synchronous/very fast exit must not be lost.
    try {child.kill(signalName);}catch{finish(childHasExited(child));}
  });
}
export async function terminateOwnedChild(child,{termMs=3000,killMs=2000}={}) {
  if(childHasExited(child))return true;
  if(await waitChildExit(child,termMs,'SIGTERM'))return true;
  return await waitChildExit(child,killMs,'SIGKILL');
}
export async function closeOwnedProxy(server,connections,{timeoutMs=2000,isListenPending=()=>false}={}) {
  if(!server)return true;
  for(const connection of connections){try{connection.destroy();}catch{}}
  try {server.closeAllConnections?.();}catch{}
  try {
    await runBounded(()=>new Promise((resolve,reject)=>{
      server.close(error=>error&&error.code!=='ERR_SERVER_NOT_RUNNING'?reject(error):resolve());
    }),timeoutMs,'proxy_close_timeout');
    return !isListenPending()&&server.listening!==true;
  }catch{return false;}
}
async function lifecycle(phase,extra={}) {
  if(!evidenceDir)return;
  const row={schema_version:'scale-browser-lifecycle.v1',at:new Date().toISOString(),phase,
    node_pid:process.pid,chrome_pid:chrome?.pid??null,profile_dir:profileDir??null,...extra};
  try {
    await runBounded(signal=>fs.promises.appendFile(path.join(evidenceDir,'browser-driver-lifecycle.jsonl'),
      JSON.stringify(row)+'\n',{mode:0o600,flag:lifecycleInitialized?'a':'wx',signal}),1000,'lifecycle_write_timeout');
    lifecycleInitialized=true;
  }catch{/* Host ownership metadata remains authoritative when disk I/O is unavailable. */}
}
export function sendCdpRequest({socket,pending,id,method,params={},signal,
    check=()=>{},now=()=>performance.now(),setTimer=setTimeout,clearTimer=clearTimeout}) {
  const timeoutMs=method==='Page.captureScreenshot'?CDP_DEADLINES_MS.screenshot:CDP_DEADLINES_MS.default;
  const deadline=now()+timeoutMs;
  return new Promise((resolve, reject) => {
    let timer,settled=false;
    const current=()=>{
      // The enclosing action deadline wins even when its timer is delayed.
      check();signal?.throwIfAborted();
      if(now()>=deadline)throw new Error('cdp_timeout:'+method);
    };
    const finish=(error,value)=>{
      if(settled)return;
      settled=true;
      if(timer!==undefined)clearTimer(timer);
      pending.delete(id);signal?.removeEventListener('abort',aborted);
      // A response callback may run before an overdue timer callback.
      try {current();}catch(reason){error=reason;}
      error?reject(error):resolve(value);
    };
    const aborted=()=>finish(signal.reason||new Error('browser_start_aborted'));
    try {
      current();
      const packet=JSON.stringify({id,method,params});
      current();
      pending.set(id,{resolve:value=>finish(null,value),reject:error=>finish(error)});
      signal?.addEventListener('abort',aborted,{once:true});
      timer=setTimer(()=>finish(new Error('cdp_timeout:'+method)),Math.max(0,deadline-now()));
      current();socket.send(packet);
    }catch(error){finish(error);}
  });
}
function send(method, params = {}) {
  actionBudget.check();
  return sendCdpRequest({socket:ws,pending,id:++sequence,method,params,
    signal:actionBudget.signal||startupSignal,check:()=>actionBudget.check()});
}

const CLICK_REJECTED = 'click_target_not_allowed_or_visible';
let observedControls = [];
let activeImportAttemptId = null;
let legacySeedReceipt=null, initialFreshStorage=null, legacySeedAllowed=false;
let freshOwnedProfile=false, seedConsumed=false, mutationsBeforeSeed=0;
const DEFAULT_PROGRESS_CONTRACT = Object.freeze({
  active_markers: [],
  analysis_markers: [],
  complete_markers: [],
  cancel_label: '',
});
const canonical=value=>JSON.stringify(value, function(key,item) {
  return item&&typeof item==='object'&&!Array.isArray(item)
    ? Object.fromEntries(Object.entries(item).sort(([a],[b])=>a<b?-1:a>b?1:0)) : item;
});

function matchesAnyMarker(text, markers) {
  return Array.isArray(markers) && markers.some(marker => typeof marker === 'string' && marker && text.includes(marker));
}

export function validateLegacySeedFixture(bytes,manifest) {
  const descriptor=manifest?.coverage?.legacy_seed;
  const legacyFile=descriptor?.fixture;
  const entry=typeof legacyFile==='string'&&legacyFile
    ? manifest?.files?.find(row=>row.name===legacyFile)
    : null;
  const proof=descriptor?.product_validation;
  const required=Array.isArray(descriptor?.required_checks)&&descriptor.required_checks.length
    ? descriptor.required_checks
    : ['legacy_excluded_from_selection','known_empty_is_known'];
  const snapshotId=Array.isArray(descriptor?.snapshot_ids)&&descriptor.snapshot_ids.length===1
    ? descriptor.snapshot_ids[0]
    : null;
  if(!Buffer.isBuffer(bytes)||bytes.length<1||bytes.length>=65536
      ||!entry||entry.scenario!=='validated-legacy-state-missing-provenance'
      ||entry.bytes!==bytes.length||entry.sha256!==hash(bytes)
      ||descriptor?.schema_version!=='ux-legacy-seed-fixture.v1'
      ||descriptor.fixture_sha256!==entry.sha256
      ||typeof descriptor.storage_key!=='string'||!descriptor.storage_key
      ||typeof descriptor.target_key!=='string'||!descriptor.target_key
      ||typeof descriptor.product_commit!=='string'||!descriptor.product_commit
      ||typeof descriptor.product_loader_sha256!=='string'||!descriptor.product_loader_sha256
      ||typeof snapshotId!=='string'||!snapshotId
      ||descriptor.source_included_files_absent!==true||descriptor.source_list_completeness_absent!==true
      ||proof?.schema_version!=='ux-legacy-product-validation.v1'
      ||proof.product_commit!==descriptor.product_commit||proof.product_loader_sha256!==descriptor.product_loader_sha256
      ||proof.fixture_sha256!==entry.sha256
      ||proof.raw_included_files_absent!==true||proof.raw_list_completeness_absent!==true
      ||JSON.stringify(proof.migrated_snapshot_ids)!==JSON.stringify([snapshotId])
      ||required.some(key=>proof.checks?.[key]!==true)
      ||descriptor.product_validation_sha256!==hash(Buffer.from(canonical(proof)+'\n')))
    throw new Error('legacy_seed_fixture_unvalidated');
  let state;
  try {state=JSON.parse(bytes.toString('utf8'));}catch{throw new Error('legacy_seed_fixture_malformed');}
  const snapshot=state?.snapshots?.[0];
  const primaryList = Array.isArray(snapshot?.primaryRecords) ? snapshot.primaryRecords : snapshot?.followers;
  const secondaryList = Array.isArray(snapshot?.secondaryRecords) ? snapshot.secondaryRecords : snapshot?.following;
  const ownerId = typeof snapshot?.ownerId === 'string' ? snapshot.ownerId : snapshot?.accountHandle;
  if(!Array.isArray(state?.snapshots)||state.snapshots.length!==1||snapshot?.id!==snapshotId
      ||snapshot.isSample!==false||typeof ownerId!=='string'
      ||!Array.isArray(primaryList)||!primaryList.length
      ||!Array.isArray(secondaryList)||!secondaryList.length
      ||Object.hasOwn(snapshot,'includedSources')||Object.hasOwn(snapshot,'recordCompleteness')
      ||Object.hasOwn(snapshot,'includedFiles')||Object.hasOwn(snapshot,'listCompleteness')
      ||state.activeSnapshotId!==snapshotId||state.comparisonSnapshotId!==snapshotId
      ||hash(Buffer.from(ownerId))!==descriptor.owner_sha256)
    throw new Error('legacy_seed_fixture_malformed');
  return descriptor;
}

export function requireFreshOwnedProfile(profile,evidence) {
  if(path.dirname(profile)!==evidence||path.basename(profile)!=='browser-profile'
      ||fs.realpathSync(profile)!==profile||!fs.statSync(profile).isDirectory()
      ||(fs.statSync(profile).mode&0o077)||fs.readdirSync(profile).length)
    throw new Error('legacy_seed_profile_not_fresh_owned');
  return true;
}

export function requireLegacySeedReady({allowed,owned,consumed,mutations,initial,current}) {
  if(!allowed)throw new Error('legacy_seed_not_authorized');
  if(consumed)throw new Error('legacy_seed_already_attempted');
  if(!owned||mutations!==0||initial?.fresh!==true||current?.fresh!==true
      ||initial.sha256!==current.sha256)
    throw new Error('legacy_seed_profile_not_fresh_owned');
}

// Parameterized fresh-state check. No raw storage value is returned to the model.
export async function pageFreshStorage(spec = null) {
  try {
    const keys=Object.keys(localStorage).sort();
    const values=keys.map(key=>[key,localStorage.getItem(key)]);
    const digest=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(JSON.stringify(values)));
    const sha256=[...new Uint8Array(digest)].map(x=>x.toString(16).padStart(2,'0')).join('');
    if(!spec||typeof spec.target_key!=='string'||!spec.target_key){
      return {available:true,fresh:keys.length===0,sha256,keys};
    }
    const ordered=value=>JSON.stringify(value,function(key,item) {
      return item&&typeof item==='object'&&!Array.isArray(item)
        ?Object.fromEntries(Object.entries(item).sort(([a],[b])=>a<b?-1:a>b?1:0)):item;
    });
    const optionalKeys=spec.optional_keys&&typeof spec.optional_keys==='object'?spec.optional_keys:{};
    const allowedSet=new Set([spec.target_key,...Object.keys(optionalKeys)]);
    const allowedKeys=keys.includes(spec.target_key)&&keys.every(key=>allowedSet.has(key));
    const optionalValid=Object.entries(optionalKeys).every(([optKey,optAllowed])=>{
      const currentVal=localStorage.getItem(optKey);
      return currentVal===null||(Array.isArray(optAllowed)&&optAllowed.includes(currentVal));
    });
    const raw=localStorage.getItem(spec.target_key);
    const matchesExpected=spec.expected_initial_state===undefined
      ? typeof raw==='string'&&raw.length<4096
      : typeof raw==='string'&&raw.length<4096&&ordered(JSON.parse(raw))===ordered(spec.expected_initial_state);
    const fresh=allowedKeys&&optionalValid&&matchesExpected;
    return {available:true,fresh,sha256,keys};
  }catch{return {available:false,fresh:false,sha256:null,keys:[]};}
}

export async function pageApplyLegacySeed(raw,fixtureSha,initialSha,origin,spec) {
  if(location.origin!==origin)throw new Error('legacy_seed_origin_changed');
  if(!spec||typeof spec.storage_key!=='string'||!spec.storage_key||typeof spec.target_key!=='string'||!spec.target_key)
    throw new Error('legacy_seed_spec_missing');
  const digest=async text=>[...new Uint8Array(await crypto.subtle.digest('SHA-256',
    new TextEncoder().encode(text)))].map(x=>x.toString(16).padStart(2,'0')).join('');
  const keys=Object.keys(localStorage).sort();
  const serialized=JSON.stringify(keys.map(key=>[key,localStorage.getItem(key)]));
  const before=await digest(serialized);
  const optionalKeys=spec.optional_keys&&typeof spec.optional_keys==='object'?spec.optional_keys:{};
  const allowedSet=new Set([spec.target_key,...Object.keys(optionalKeys)]);
  const allowedKeys=keys.includes(spec.target_key)&&keys.every(key=>allowedSet.has(key));
  const optionalValid=Object.entries(optionalKeys).every(([optKey,optAllowed])=>{
    const currentVal=localStorage.getItem(optKey);
    return currentVal===null||(Array.isArray(optAllowed)&&optAllowed.includes(currentVal));
  });
  if(before!==initialSha||!allowedKeys||!optionalValid
      ||await digest(raw)!==fixtureSha)throw new Error('legacy_seed_storage_changed');
  if(JSON.stringify(Object.keys(localStorage).sort().map(key=>[key,localStorage.getItem(key)]))!==serialized)
    throw new Error('legacy_seed_storage_changed');
  localStorage.setItem(spec.storage_key,raw);
  if(localStorage.getItem(spec.storage_key)!==raw)throw new Error('legacy_seed_write_unconfirmed');
  localStorage.removeItem(spec.target_key);
  if(localStorage.getItem(spec.target_key)!==null)throw new Error('legacy_seed_removal_unconfirmed');
  return {written:true};
}

export async function pageReadLegacyState(attemptId,spec) {
  const result={schema_version:'ux-legacy-state.v1',seed_attempt_id:attemptId,available:false};
  try {
    if(!spec||typeof spec.target_key!=='string'||!spec.target_key)return result;
    const raw=localStorage.getItem(spec.target_key);
    if(!raw||raw.length>=65536||!raw.startsWith('{'))return result;
    const state=JSON.parse(raw);
    if(!Array.isArray(state.snapshots)||state.snapshots.length>10)return result;
    const digest=async text=>[...new Uint8Array(await crypto.subtle.digest('SHA-256',
      new TextEncoder().encode(text)))].map(x=>x.toString(16).padStart(2,'0')).join('');
    const rows=[];
    for(const snapshot of state.snapshots) {
      const ownerId = typeof snapshot.ownerId === 'string' ? snapshot.ownerId : snapshot.accountHandle;
      const includedSources = Array.isArray(snapshot.includedSources) ? snapshot.includedSources : snapshot.includedFiles;
      const completeness = snapshot.recordCompleteness ?? snapshot.listCompleteness ?? null;
      if(typeof snapshot.id!=='string'||snapshot.id.length>100
          ||typeof ownerId!=='string'||ownerId.length>30
          ||typeof snapshot.isSample!=='boolean'||!Array.isArray(includedSources)
          ||includedSources.length>20
          ||includedSources.some(item=>typeof item!=='string'||item.length>40))return result;
      rows.push({id:snapshot.id,account_sha256:await digest(ownerId),
        is_sample:snapshot.isSample,list_completeness:completeness,
        included_files:includedSources});
    }
    const readKeys=Array.isArray(spec.read_keys)&&spec.read_keys.length
      ? spec.read_keys
      : [spec.target_key, ...(spec.storage_key?[spec.storage_key]:[])];
    const values=readKeys.map(key=>[key,localStorage.getItem(key)]).filter(row=>row[1]!==null);
    return {...result,available:true,storage_sha256:await digest(JSON.stringify(values)),
      snapshots:rows,active_snapshot_id:state.activeSnapshotId,comparison_snapshot_id:state.comparisonSnapshotId};
  }catch{return result;}
}

export function isValidatedLegacyMigration(state,descriptor) {
  const row=state?.snapshots?.[0];
  const snapshotId=Array.isArray(descriptor?.snapshot_ids)&&descriptor.snapshot_ids[0];
  const expectedFiles=Array.isArray(descriptor?.expected_included_files)
    ? descriptor.expected_included_files
    : ['primary','secondary'];
  return state?.available===true&&state.snapshots.length===1&&Boolean(snapshotId)&&row?.id===snapshotId
    &&row.account_sha256===descriptor.owner_sha256&&row.is_sample===false
    &&row.list_completeness==='unknown'
    &&JSON.stringify(row.included_files)===JSON.stringify(expectedFiles)
    &&state.active_snapshot_id===null&&state.comparison_snapshot_id===null;
}

// Serialized into the owned page; no arbitrary caller-provided script is accepted.
export function pageClickTarget(selector, label, requireActiveImport = false, progressMarkers = null) {
  const norm = s => String(s || '').replace(/\s+/g, ' ').trim();
  const structural = e => {
    const parts = [];
    while (e && e.nodeType === 1 && e !== document.body) {
      let n = 1;
      for (let p = e.previousElementSibling; p; p = p.previousElementSibling) if (p.tagName === e.tagName) n++;
      parts.unshift(e.tagName.toLowerCase() + ':nth-of-type(' + n + ')'); e = e.parentElement;
    }
    return 'body>' + parts.join('>');
  };
  const candidate = e => {
    if (!e || !e.getBoundingClientRect || e.disabled) return false;
    const r = e.getBoundingClientRect(), s = getComputedStyle(e);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'
      && (e.tagName === 'SUMMARY' || !e.closest('details:not([open])'))
      && e.type !== 'submit' && !(e.closest('form') && e.tagName === 'BUTTON' && e.type !== 'button');
  };
  if (requireActiveImport) {
    const status = norm(document.querySelector('[role=status][aria-live=polite]')?.textContent);
    const markers = Array.isArray(progressMarkers) ? progressMarkers : [];
    if (!markers.some(marker => marker && status.includes(marker))) return null;
  }
  let e;
  try { e = document.querySelector(selector); } catch { return null; }
  if (!candidate(e) || norm(e.getAttribute('aria-label') || e.innerText || e.textContent) !== norm(label)) return null;
  e.scrollIntoView({block:'center',inline:'nearest'});
  const r = e.getBoundingClientRect();
  const left = Math.max(0,r.left), right = Math.min(innerWidth,r.right);
  const top = Math.max(0,r.top), bottom = Math.min(innerHeight,r.bottom);
  if (right <= left || bottom <= top) return null;
  const x=(left+right)/2, y=(top+bottom)/2, hit=document.elementFromPoint(x,y);
  if (!hit || !(hit===e || e.contains(hit) || hit.closest('button,a,summary,[role=button],[role=link]')===e)) return null;
  return {x,y,tag:e.tagName,href:e.tagName==='A'?e.href:null,
    label:norm(e.getAttribute('aria-label') || e.innerText || e.textContent),selector:structural(e)};
}

export function pageVerifyClick(box, requireActiveImport = false, progressMarkers = null) {
  const norm = s => String(s || '').replace(/\s+/g,' ').trim();
  let e;
  try { e=document.querySelector(box.selector); } catch { return false; }
  if (!e || e.disabled || norm(e.getAttribute('aria-label') || e.innerText || e.textContent)!==norm(box.label)) return false;
  if (requireActiveImport) {
    const text=norm(document.querySelector('[role=status][aria-live=polite]')?.textContent);
    const markers = Array.isArray(progressMarkers) ? progressMarkers : [];
    if (!markers.some(marker => marker && text.includes(marker))) return false;
  }
  const r=e.getBoundingClientRect(), s=getComputedStyle(e);
  if (s.visibility==='hidden' || s.display==='none' || r.width<=0 || r.height<=0
      || box.x<r.left || box.x>r.right || box.y<r.top || box.y>r.bottom) return false;
  const hit=document.elementFromPoint(box.x,box.y);
  return !!hit && (hit===e || e.contains(hit) || hit.closest('button,a,summary,[role=button],[role=link]')===e);
}

export async function dispatchVerifiedClick(resolveTarget, verifyTarget, emit) {
  const box=await resolveTarget();
  if (!box) throw new Error(CLICK_REJECTED);
  await emit('mouseMoved',box);
  // Recheck after scroll/mouse movement, immediately before the first button event.
  if (!await verifyTarget(box)) throw new Error(CLICK_REJECTED);
  await emit('mousePressed',box);
  await emit('mouseReleased',box);
  return box;
}

// Read-only DOM planning. A wheel is never aimed at a fixed viewport coordinate
// or a background page while an active modal owns the interaction.
export function pageScrollTarget(delta, expected = null) {
  const modalQuery='[role="dialog"][aria-modal="true"],[role="alertdialog"][aria-modal="true"],dialog[open]';
  const viewport={width:innerWidth,height:innerHeight};
  const selector=e=>{
    if(e===document.documentElement)return 'html';
    if(e===document.body)return 'body';
    const parts=[];
    while(e&&e.nodeType===1&&e!==document.body){
      let n=1;for(let p=e.previousElementSibling;p;p=p.previousElementSibling)if(p.tagName===e.tagName)n++;
      parts.unshift(e.tagName.toLowerCase()+':nth-of-type('+n+')');e=e.parentElement;
    }
    return 'body>'+parts.join('>');
  };
  const shown=e=>{const s=getComputedStyle(e);return s.display!=='none'&&s.visibility!=='hidden'&&s.visibility!=='collapse';};
  const clip=r=>({left:Math.max(0,r.left),right:Math.min(innerWidth,r.right),
    top:Math.max(0,r.top),bottom:Math.min(innerHeight,r.bottom)});
  const area=r=>Math.max(0,r.right-r.left)*Math.max(0,r.bottom-r.top);
  const points=r=>area(r)>0?[ [.5,.5],[.25,.25],[.75,.25],[.25,.75],[.75,.75] ]
    .map(([x,y])=>({x:r.left+(r.right-r.left)*x,y:r.top+(r.bottom-r.top)*y})):[];
  const modalAt=p=>document.elementFromPoint(p.x,p.y)?.closest(modalQuery)||null;
  const modals=[...document.querySelectorAll(modalQuery)].filter(shown);
  const base={viewport,document_scroll:{x:window.scrollX,y:window.scrollY},blocked_areas:[]};
  if(modals.length>8)return {...base,status:'modal_scan_limit',target:null};
  const visible=modals.filter(e=>area(clip(e.getBoundingClientRect()))>0), beneath=new Set();
  for(const a of visible)for(const b of visible){
    if(a===b)continue;
    const ar=clip(a.getBoundingClientRect()),br=clip(b.getBoundingClientRect());
    const overlap={left:Math.max(ar.left,br.left),right:Math.min(ar.right,br.right),
      top:Math.max(ar.top,br.top),bottom:Math.min(ar.bottom,br.bottom)};
    if(points(overlap).some(p=>modalAt(p)===b))beneath.add(a);
  }
  let exposed=visible.filter(e=>!beneath.has(e)&&points(clip(e.getBoundingClientRect())).some(p=>modalAt(p)===e));
  if(exposed.length>1){
    const focused=document.activeElement?.closest(modalQuery);
    exposed=focused&&exposed.includes(focused)?[focused]:[];
  }
  if(modals.length&&exposed.length!==1)
    return {...base,status:visible.length?'modal_not_uniquely_exposed':'modal_has_no_usable_area',target:null};
  const modal=exposed[0]||null,scope=modal||document.body;
  const scopeSelector=modal?selector(modal):null;
  Object.assign(base,{scope:modal?'modal':'page',modal_selector:scopeSelector,
    modal_bounds:modal?{...clip(modal.getBoundingClientRect())}:null});
  const nodes=[scope,...scope.querySelectorAll('*')];
  if(!modal&&document.scrollingElement&&!nodes.includes(document.scrollingElement))nodes.unshift(document.scrollingElement);
  if(nodes.length>1500)return {...base,status:'scroll_scan_limit',target:null};
  const metrics=e=>{
    const s=getComputedStyle(e),r=clip(e.getBoundingClientRect());
    return {selector:selector(e),scroll_top:e.scrollTop,scroll_height:e.scrollHeight,client_height:e.clientHeight,
      content_height:Math.max(0,e.clientHeight-(parseFloat(s.paddingTop)||0)-(parseFloat(s.paddingBottom)||0)),
      max_scroll_top:Math.max(0,e.scrollHeight-e.clientHeight),overflow_y:s.overflowY,
      bounds:r,visible_area:area(r)};
  };
  const styled=e=>{
    if(!e||!shown(e))return false;
    const overflow=getComputedStyle(e).overflowY;
    return ['auto','scroll','overlay'].includes(overflow)||
      (!modal&&e===document.scrollingElement&&!['hidden','clip'].includes(overflow));
  };
  const usable=e=>{
    if(!styled(e))return false;
    const m=metrics(e);
    return m.client_height>0&&m.content_height>0&&m.visible_area>0&&m.max_scroll_top>1;
  };
  const receiver=hit=>{
    for(let e=hit;e&&e.nodeType===1;e=e.parentElement){
      if(usable(e))return e;
      if(modal&&e===modal)break;
    }
    return null;
  };
  const hitTarget=(e,p)=>{
    const r=clip(e.getBoundingClientRect());
    if(p.x<r.left||p.x>=r.right||p.y<r.top||p.y>=r.bottom)return false;
    const hit=document.elementFromPoint(p.x,p.y);
    return !!hit&&(hit===e||e.contains(hit))&&(!modal||hit.closest(modalQuery)===modal)&&receiver(hit)===e;
  };
  const describe=(e,p)=>{
    const m=metrics(e),canMove=delta>0?m.scroll_top<m.max_scroll_top-1:m.scroll_top>1;
    return {...base,status:delta===0?'zero_delta':canMove?'ready':'at_boundary',target:{...m,point:p}};
  };
  base.blocked_areas=nodes.filter(styled).map(metrics)
    .filter(m=>m.client_height<=0||m.content_height<=0||m.visible_area<=0).slice(0,8);
  if(expected){
    if(expected.modal_selector!==scopeSelector)return {...base,status:'active_scope_changed',target:null};
    let e;try{e=document.querySelector(expected.selector);}catch{}
    if(!e||!nodes.includes(e)||!usable(e)||!hitTarget(e,expected.point))
      return {...base,status:'target_not_visible_or_scrollable',target:null};
    return describe(e,expected.point);
  }
  const candidates=nodes.filter(usable).sort((a,b)=>metrics(b).visible_area-metrics(a).visible_area);
  for(const e of candidates){
    const point=points(clip(e.getBoundingClientRect())).find(p=>hitTarget(e,p));
    if(point)return describe(e,point);
  }
  return {...base,status:base.blocked_areas.length?'scroll_area_has_no_usable_height':
    candidates.length?'scroll_target_occluded':'no_scrollable_area',target:null};
}

export async function runScrollAttempt(io, requestedDelta) {
  if(!Number.isInteger(requestedDelta))throw new Error('scroll_delta_invalid');
  const delta=Math.max(-900,Math.min(900,requestedDelta)),started=io.now();
  const selected=await io.inspect(delta,null);
  const result={schema_version:'owned-scroll-attempt.v1',requested_delta:requestedDelta,delta:0,
    viewport:selected.viewport,scope:selected.scope||null,modal_selector:selected.modal_selector||null,
    modal_bounds:selected.modal_bounds||null,blocked_areas:selected.blocked_areas||[],
    dispatched:false,moved:false,outcome:selected.status,before:selected.target,after:null,
    document_before:selected.document_scroll,document_after:null};
  if(selected.status!=='ready'||!selected.target)return result;
  const expected={selector:selected.target.selector,modal_selector:selected.modal_selector,
    point:selected.target.point};
  await io.move(expected.point);
  const verified=await io.inspect(delta,expected);
  if(verified.status!=='ready'||!verified.target)
    return {...result,outcome:verified.status,before:verified.target,blocked_areas:verified.blocked_areas||[]};
  result.before=verified.target;result.document_before=verified.document_scroll;
  result.viewport=verified.viewport;result.modal_bounds=verified.modal_bounds||null;
  // Keep overlap in short panes so a just-below-fold control is not skipped.
  const visibleHeight=Math.min(verified.target.client_height,
    verified.target.bounds.bottom-verified.target.bounds.top);
  result.delta=Math.sign(delta)*Math.min(Math.abs(delta),Math.max(1,Math.floor(visibleHeight*.8)));
  // Any exception after this send propagates as uncertainty. Never replay a wheel.
  await io.wheel(expected.point,result.delta);result.dispatched=true;
  const settleStarted=io.now();
  for(let sample=0;sample<12&&io.now()-settleStarted<300;sample++){
    await io.pause(25);
    const observed=await io.inspect(delta,expected);
    result.document_after=observed.document_scroll;
    if(!observed.target){result.outcome='target_changed_after_dispatch';break;}
    result.after=observed.target;
    const movement=result.after.scroll_top-result.before.scroll_top;
    result.observed_delta=movement;
    if(movement!==0){result.moved=true;result.outcome='scrolled';break;}
    result.outcome='no_movement';
  }
  result.background_moved=!!result.document_after&&(
    result.document_after.x!==result.document_before.x||result.document_after.y!==result.document_before.y);
  if(result.scope==='modal'&&result.background_moved)result.outcome='background_moved';
  result.observation_window_ms=io.now()-started;
  return result;
}

export function pageImportState(contract = DEFAULT_PROGRESS_CONTRACT) {
  const norm=s=>String(s||'').replace(/\s+/g,' ').trim();
  const hasAny=(text,list)=>Array.isArray(list)&&list.some(item=>typeof item==='string'&&item&&text.includes(item));
  const phase=norm(document.querySelector('[role=status][aria-live=polite]')?.textContent);
  const analysis=hasAny(phase,contract?.analysis_markers);
  const active=hasAny(phase,contract?.active_markers)||analysis;
  const complete=hasAny(phase,contract?.complete_markers);
  const cancelLabel=typeof contract?.cancel_label==='string'?contract.cancel_label:'';
  const structural=e=>{
    const parts=[];
    while(e&&e.nodeType===1&&e!==document.body){
      let n=1;for(let p=e.previousElementSibling;p;p=p.previousElementSibling)if(p.tagName===e.tagName)n++;
      parts.unshift(e.tagName.toLowerCase()+':nth-of-type('+n+')');e=e.parentElement;
    }
    return 'body>'+parts.join('>');
  };
  const candidates=cancelLabel?[...document.querySelectorAll('button,[role=button]')]
    .filter(e=>norm(e.getAttribute('aria-label')||e.innerText||e.textContent)===cancelLabel):[];
  const visible=candidates.filter(e=>{
    const r=e.getBoundingClientRect(),s=getComputedStyle(e);
    if(e.disabled||r.width<=0||r.height<=0||s.visibility==='hidden'||s.display==='none')return false;
    const left=Math.max(0,r.left),right=Math.min(innerWidth,r.right),top=Math.max(0,r.top),bottom=Math.min(innerHeight,r.bottom);
    if(right<=left||bottom<=top)return false;
    const hit=document.elementFromPoint((left+right)/2,(top+bottom)/2);
    return !!hit&&(hit===e||e.contains(hit)||hit.closest('button,[role=button]')===e);
  });
  return {phase,active,analysis,complete,cancel_control_present:candidates.length>0,
    cancel:visible.length===1?{selector:structural(visible[0]),label:cancelLabel}:null};
}

export async function pageStorageSnapshot(keys = null) {
  try {
    const selected = Array.isArray(keys) && keys.length
      ? keys
      : (typeof Object.keys === 'function' ? Object.keys(localStorage).sort() : []);
    const values=selected.map(key=>[key,localStorage.getItem(key)]).filter(row=>row[1]!==null);
    const bytes=new TextEncoder().encode(JSON.stringify(values));
    const digest=await globalThis.crypto.subtle.digest('SHA-256',bytes);
    return {available:true,keys:values.map(row=>row[0]),
      sha256:[...new Uint8Array(digest)].map(value=>value.toString(16).padStart(2,'0')).join('')};
  } catch { return {available:false,keys:[],sha256:null}; }
}

export function pageArmStorageFailure(targetKey) {
  if(typeof targetKey!=='string'||!targetKey)throw new Error('storage_fault_key_required');
  const name='__remorsearchOwnedStorageFailure';
  if (window[name]) throw new Error('storage_fault_already_armed');
  const original=Storage.prototype.setItem;
  const state={key:targetKey,armed:true,consumed:false,restored:false,restore_reason:null};
  let timer;
  const cleanup=reason=>{
    if (Storage.prototype.setItem===wrapped) Storage.prototype.setItem=original;
    state.armed=false;state.restored=Storage.prototype.setItem===original;
    state.restore_reason=state.restore_reason||reason;
    if(timer)clearTimeout(timer);
  };
  function wrapped(key,value) {
    if(this===localStorage && String(key)===state.key && state.armed){
      state.consumed=true;cleanup('consumed');
      throw new DOMException('Owned synthetic one-shot storage failure','QuotaExceededError');
    }
    return original.call(this,key,value);
  }
  window[name]={state,cleanup};
  try {
    Storage.prototype.setItem=wrapped;
    timer=setTimeout(()=>cleanup('timeout'),5000);
  } catch (error) { cleanup('arm_failed');delete window[name];throw error; }
  return {...state};
}

export function pageReadStorageFailure(cleanup = false) {
  const name='__remorsearchOwnedStorageFailure',holder=window[name];
  if(!holder)return null;
  if(cleanup)holder.cleanup('finally');
  const state={...holder.state};
  if(cleanup)delete window[name];
  return state;
}

// One compound action owns the timing-sensitive UI sequence. It never retries a
// dispatched click, and reports a missed window rather than a product failure.
export async function runCancellationAttempt(io) {
  const started=io.now(), phases=[];
  let cancelActive=false, cancelDispatched=false, terminal='window_not_observed', last=null;
  while(io.now()-started<5000){
    const state=await io.readPhase();last=state;
    if(state.phase && phases.at(-1)?.text!==state.phase && phases.length<32)
      phases.push({elapsed_ms:io.now()-started,text:state.phase});
    if(state.complete){terminal='already_completed';break;}
    if(state.active && state.analysis && state.cancel){
      const current=await io.readPhase();last=current;
      if(!current.active || !current.analysis || !current.cancel){
        if(current.complete){terminal='already_completed';break;}
        await io.pause(10);continue;
      }
      cancelActive=true;
      try { await io.dispatchCancel(current.cancel);cancelDispatched=true; }
      catch(error){
        if(String(error?.message)!==CLICK_REJECTED)throw error;
        terminal='cancel_target_rejected';break;
      }
      const settled=io.now();
      while(io.now()-settled<1000){
        last=await io.readPhase();
        if(last.complete){terminal='completed_after_cancel';break;}
        await io.pause(25);
      }
      if(terminal!=='completed_after_cancel')
        terminal=last?.active?'still_active_after_cancel':'inactive_after_cancel';
      break;
    }
    await io.pause(10);
  }
  return {phase_samples:phases,cancel_active:cancelActive,cancel_dispatched:cancelDispatched,
    terminal_state:terminal,post_state:last,observation_window_ms:io.now()-started};
}

async function persistence() {
  return await evaluate('('+pageStorageSnapshot.toString()+')('+JSON.stringify(fixtureManifest?.storage_keys || null)+')');
}
async function guardedClick(selector,label,requireActiveImport=false) {
  const progressMarkers = fixtureManifest?.progress_contract?.active_markers || [];
  return await dispatchVerifiedClick(
    async()=>{
      const box=await evaluate('('+pageClickTarget.toString()+')('+JSON.stringify(selector)+','+JSON.stringify(label)+','+JSON.stringify(requireActiveImport)+','+JSON.stringify(progressMarkers)+')');
      if(box?.href && new URL(box.href).origin!==targetOrigin)throw new Error('cross_origin_link_blocked');
      return box;
    },
    box=>evaluate('('+pageVerifyClick.toString()+')('+JSON.stringify(box)+','+JSON.stringify(requireActiveImport)+','+JSON.stringify(progressMarkers)+')'),
    (type,box)=>send('Input.dispatchMouseEvent',{type,x:box.x,y:box.y,...(type!=='mouseMoved'?{button:'left',clickCount:1}:{})})
  );
}

async function start(input) {
  if (chrome || closePromise || Number(process.versions.node.split('.')[0]) < 22) throw new Error('node_runtime');
  startupController=new AbortController();
  try {
    return await runBounded(async signal=>{
      startupSignal=signal;
      return await startWithinBudget(input,signal);
    },DRIVER_DEADLINES_MS.start,'browser_start_timeout',startupController.signal);
  } catch(error) {
    await lifecycle('start_failed',{error:String(error?.message||'browser_start_failed').slice(0,120)});
    throw error;
  } finally {startupController=null;startupSignal=null;}
}
async function startWithinBudget(input,signal) {
  const url = new URL(input.url);
  if (url.protocol !== 'http:' || !['127.0.0.1','localhost','[::1]'].includes(url.hostname) || url.username || url.password) throw new Error('target_must_be_loopback_http');
  targetOrigin = url.origin; pageUrl = url.href; typedInputs = new Map(); proxyBlockedRequests = 0;
  evidenceDir=await safeDir(input.evidence_path,signal);
  profileDir=await safeDir(input.profile_dir,signal);
  if(path.dirname(profileDir)!==evidenceDir||path.basename(profileDir)!=='browser-profile'
      ||(await startupIO(()=>fs.promises.readdir(profileDir),signal)).length)
    throw new Error('legacy_seed_profile_not_fresh_owned');
  freshOwnedProfile=true;
  await lifecycle('profile_validated');signal.throwIfAborted();
  legacySeedAllowed=input.legacy_seed_allowed===true;
  fixturesDir = await safeDir(input.fixtures_dir,signal);
  const manifestPath = path.join(fixturesDir, 'fixture-manifest.json');
  const manifestStat = await startupIO(()=>fs.promises.lstat(manifestPath),signal);
  const manifestReal = await startupIO(()=>fs.promises.realpath(manifestPath),signal);
  if (!manifestStat.isFile() || manifestStat.isSymbolicLink() || manifestReal!==manifestPath) throw new Error('fixture_manifest_invalid');
  fixtureManifest = JSON.parse(await startupIO(inner=>fs.promises.readFile(manifestPath,{encoding:'utf8',signal:inner}),signal));
  if (fixtureManifest.schema_version !== 'ux-synthetic-fixtures.v1' || !Array.isArray(fixtureManifest.files)) throw new Error('fixture_manifest_schema');
  if (fixtureManifest.groups !== undefined) {
    if (!fixtureManifest.groups || typeof fixtureManifest.groups !== 'object' || Array.isArray(fixtureManifest.groups)) throw new Error('fixture_manifest_groups');
    for (const [group,names] of Object.entries(fixtureManifest.groups)) {
      if (!/^[a-zA-Z0-9._-]{1,80}$/.test(group) || !Array.isArray(names) || !names.length || names.length>513 || names.some(name=>typeof name!=='string'||path.basename(name)!==name)) throw new Error('fixture_manifest_group_entry');
    }
  }
  await lifecycle('fixtures_validating');signal.throwIfAborted();
  await validateFixtureFiles(fixtureManifest,fixturesDir,signal);
  await lifecycle('fixtures_validated',{fixture_count:fixtureManifest.files.length});signal.throwIfAborted();
  const binary = input.chrome;
  if(!path.isAbsolute(binary))throw new Error('chrome_binary');
  const binaryStat=await startupIO(()=>fs.promises.stat(binary),signal);
  if(!binaryStat.isFile())throw new Error('chrome_binary');
  const proxyHost = url.hostname === 'localhost' ? '127.0.0.1' : url.hostname;
  const proxyPort = Number(url.port || 80);
  proxy = http.createServer((req,res) => {
    let requested;
    try { requested = new URL(req.url); } catch { res.writeHead(400); res.end(); return; }
    if (requested.origin !== targetOrigin || requested.protocol !== 'http:') {
      proxyBlockedRequests += 1;
      res.writeHead(403, {'Cache-Control':'no-store'}); res.end('blocked'); return;
    }
    const upstream = http.request({hostname:proxyHost,port:proxyPort,
      path:requested.pathname+requested.search,method:req.method,
      headers:{...req.headers,host:url.host}}, response => {
        res.writeHead(response.statusCode || 502, response.headers);
        response.pipe(res);
      });
    proxyConnections.add(upstream);upstream.once('close',()=>proxyConnections.delete(upstream));
    upstream.on('error',()=>{ if(!res.headersSent) res.writeHead(502); res.end(); });
    req.pipe(upstream);
  });
  proxy.on('connection',socket=>{
    proxyConnections.add(socket);socket.once('close',()=>proxyConnections.delete(socket));
    socket.on('error',()=>{});
  });
  proxy.on('clientError',(error,socket)=>{if(socket.writable)socket.end('HTTP/1.1 400 Bad Request\r\nConnection: close\r\n\r\n');});
  proxy.on('connect',(req,socket)=>{proxyBlockedRequests+=1;socket.end('HTTP/1.1 403 Forbidden\r\nConnection: close\r\n\r\n');});
  proxy.on('upgrade',(req,socket)=>{proxyBlockedRequests+=1;socket.end('HTTP/1.1 403 Forbidden\r\nConnection: close\r\n\r\n');});
  await runBounded(()=>new Promise((resolve,reject)=>{
    proxyListenPending=true;
    proxy.once('error',error=>{proxyListenPending=false;reject(error);});
    proxy.listen(0,'127.0.0.1',()=>{proxyListenPending=false;resolve();});
  }),5000,'proxy_listen_timeout',signal);
  await lifecycle('proxy_listening');signal.throwIfAborted();
  const proxyPortLocal = proxy.address().port;
  chrome = spawn(binary, ['--headless=new','--disable-gpu','--no-first-run','--no-default-browser-check',
    '--disable-background-networking','--disable-component-update','--disable-sync','--disable-extensions',
    '--disable-features=Translate,MediaRouter','--disable-quic',
    '--proxy-server=http://127.0.0.1:'+proxyPortLocal,'--proxy-bypass-list=<-loopback>',
    '--remote-debugging-port=0','--remote-allow-origins=*','--user-data-dir='+profileDir,'about:blank'],
    {stdio:'ignore'});
  chrome.once('error',()=>{chromeSpawnFailed=!Number.isSafeInteger(chrome.pid);});
  await lifecycle('chrome_spawned');signal.throwIfAborted();
  const activeFile = path.join(profileDir,'DevToolsActivePort');
  const port=await runBounded(async inner=>{
    while(!childHasExited(chrome)&&!chromeSpawnFailed) {
      inner.throwIfAborted();
      try {
        const text=await startupIO(readSignal=>fs.promises.readFile(activeFile,{encoding:'utf8',signal:readSignal}),inner);
        const value=Number(text.split('\n')[0]);
        if(!Number.isInteger(value)||value<1||value>65535)throw new Error('chrome_debug_port_invalid');
        return value;
      }catch(error){if(error.code!=='ENOENT')throw error;}
      await runBounded(()=>new Promise(resolve=>setTimeout(resolve,100)),1000,'chrome_start_failed',inner);
    }
    throw new Error('chrome_start_failed');
  },15000,'chrome_start_timeout',signal);
  await lifecycle('cdp_discovery');signal.throwIfAborted();
  const targets = await fetchJsonBounded('http://127.0.0.1:'+port+'/json/list',{signal});
  if(!Array.isArray(targets))throw new Error('chrome_targets_invalid');
  const page = targets.find(x=>x.type==='page');
  if (!page?.webSocketDebuggerUrl) throw new Error('chrome_page_missing');
  const socketUrl=new URL(page.webSocketDebuggerUrl);
  if(socketUrl.protocol!=='ws:'||socketUrl.hostname!=='127.0.0.1'||Number(socketUrl.port)!==port
      ||socketUrl.username||socketUrl.password)throw new Error('chrome_socket_not_owned_loopback');
  ws = new WebSocket(page.webSocketDebuggerUrl);
  await openSocketBounded(ws,{signal});
  ws.addEventListener('error',()=>{ for(const item of pending.values())item.reject(new Error('cdp_websocket_error')); });
  ws.addEventListener('close',()=>{ for(const item of pending.values())item.reject(new Error('cdp_websocket_closed')); });
  ws.addEventListener('message',event=>{
    let m; try {m=JSON.parse(event.data);} catch {return;}
    if (m.id && pending.has(m.id)) { const p=pending.get(m.id); m.error?p.reject(new Error(m.error.message||'cdp_error')):p.resolve(m.result||{}); }
  });
  await lifecycle('websocket_open');signal.throwIfAborted();
  await send('Page.enable'); await send('Runtime.enable'); await send('Network.enable');
  await send('Network.setBlockedURLs',{urls:['ws://*','wss://*','ftp://*','file://*']});
  await lifecycle('page_navigate');signal.throwIfAborted();
  await send('Page.navigate',{url:pageUrl});
  await runBounded(()=>new Promise(r=>setTimeout(r,700)),1000,'page_settle_timeout',signal);
  const snap=await observe();
  initialFreshStorage=await evaluate('('+pageFreshStorage.toString()+')('+JSON.stringify(fixtureManifest?.coverage?.legacy_seed || null)+')');
  await lifecycle('started');signal.throwIfAborted();
  return {started:true,url:snap.url,title:snap.title,origin:targetOrigin,available_fixtures:fixtureManifest.files.map(row=>row.name)};
}
async function evaluate(expression) {
  const r=await send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true,userGesture:true});
  if (r.exceptionDetails) throw new Error('page_evaluation_failed:' + String(r.exceptionDetails.exception?.description || r.exceptionDetails.text || 'unknown').slice(0,180));
  return r.result?.value;
}
async function observe() {
  await actionBudget.phase('observe_dom');
  const expression = "(() => {const rendered=e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>0&&r.height>0&&s.visibility!=='hidden'&&s.display!=='none'&&(e.tagName==='SUMMARY'||!e.closest('details:not([open])'))};const visible=e=>{if(!rendered(e))return false;const r=e.getBoundingClientRect();if(r.bottom<=0||r.top>=innerHeight||r.right<=0||r.left>=innerWidth)return false;const x=Math.min(innerWidth-1,Math.max(0,r.x+r.width/2)),y=Math.min(innerHeight-1,Math.max(0,r.y+r.height/2)),hit=document.elementFromPoint(x,y);return !!hit&&(hit===e||e.contains(hit)||hit.closest('button,a,summary,[role=button],[role=link]')===e)};const selector=e=>{const parts=[];while(e&&e.nodeType===1&&e!==document.body){let n=1;for(let p=e.previousElementSibling;p;p=p.previousElementSibling)if(p.tagName===e.tagName)n++;parts.unshift(e.tagName.toLowerCase()+':nth-of-type('+n+')');e=e.parentElement;}return 'body>'+parts.join('>');};const controls=[...document.querySelectorAll('button,a,summary,input,textarea,select,[role=button],[role=link]')].filter(rendered).slice(0,100).map((e,i)=>({index:i,selector:selector(e),tag:e.tagName.toLowerCase(),id:e.id||null,role:e.getAttribute('role'),type:e.type||null,label:(e.getAttribute('aria-label')||e.innerText||e.textContent||e.getAttribute('placeholder')||'').trim().slice(0,180),placeholder:e.getAttribute('placeholder')||null,title:e.getAttribute('title')||null,multiple:e.multiple===true,disabled:!!e.disabled,visible:visible(e),href:e.tagName==='A'?e.href:null}));const fileInputs=[...document.querySelectorAll('input[type=file]')].map((e,i)=>({index:i,selector:selector(e),accept:e.accept,multiple:e.multiple,disabled:!!e.disabled,hidden:!visible(e)}));const listRows=[...document.querySelectorAll('[data-row-key]')].map(e=>({key:e.getAttribute('data-row-key'),text:(e.innerText||e.textContent||'').trim().slice(0,180)}));let storageKeys=[],storageAccess='denied';try{storageKeys=Object.keys(localStorage);storageAccess='available';}catch{}return {url:location.href,title:document.title,text:(document.body?.innerText||'').slice(0,12000),controls,file_inputs:fileInputs,list_rows:listRows,storage_keys:storageKeys,storage_access:storageAccess,viewport:{width:innerWidth,height:innerHeight}};})()";
  const data=await evaluate(expression);
  if (!data || new URL(data.url).origin!==targetOrigin) throw new Error('origin_changed');
  await actionBudget.phase('observe_inputs');
  const values = await evaluate("(() => {const out={};for(const selector of "+JSON.stringify([...typedInputs.keys()])+ "){try{const e=document.querySelector(selector);out[selector]=e&&('value' in e)?String(e.value):null;}catch{out[selector]=null;}}return out;})()");
  data.typed_input_checks = Object.entries(values||{}).map(([selector,value])=>({
    selector, retained:value!==null && hash(Buffer.from(value,'utf8'))===typedInputs.get(selector),
    expected_sha256:typedInputs.get(selector), actual_sha256:value===null?null:hash(Buffer.from(value,'utf8'))
  }));
  data.network_policy = {allowed_origin:targetOrigin,external_requests_blocked:true,blocked_request_count:proxyBlockedRequests};
  data.available_fixtures = fixtureManifest.files.map(row=>row.name);
  observedControls=data.controls.map(row=>({...row}));
  await actionBudget.phase('observe_storage');
  data.storage_snapshot=await persistence();
  if(activeImportAttemptId)data.import_attempt_id=activeImportAttemptId;
  if(legacySeedReceipt) {
    data.legacy_seed=structuredClone(legacySeedReceipt);
    const seedSpec = fixtureManifest?.coverage?.legacy_seed || null;
    data.legacy_state=await evaluate('('+pageReadLegacyState.toString()+')('+JSON.stringify(legacySeedReceipt.attempt_id)+','+JSON.stringify(seedSpec)+')');
  }
  return data;
}
async function screenshot() {
  await actionBudget.phase('screenshot_capture');
  const r=await send('Page.captureScreenshot',{format:'png',fromSurface:true,captureBeyondViewport:false});
  const bytes=Buffer.from(r.data,'base64');
  const name='browser-'+String(++sequence).padStart(5,'0')+'.png';
  await actionBudget.phase('screenshot_write',{capture:name,bytes:bytes.length});
  const receipt=await writeCaptureBytes(evidenceDir,name,bytes,actionBudget.signal);
  await actionBudget.phase('screenshot_written',{capture:name,bytes:bytes.length});
  return receipt;
}
export function approvedCancelFixture(entries) {
  return Array.isArray(entries) && entries.length===1
    && (entries[0]?.cancel_eligible===true
        || ['large-valid-progress','recognized-relationship-json-progress'].includes(entries[0]?.scenario));
}
async function seedLegacyUnknown(args) {
  if(seedConsumed)throw new Error('legacy_seed_already_attempted');
  const seedSpec=fixtureManifest?.coverage?.legacy_seed;
  const legacyFile=seedSpec?.fixture;
  if(!seedSpec||typeof legacyFile!=='string'||!legacyFile)throw new Error('legacy_seed_not_configured');
  if(Object.keys(args).length!==1||args.file!==legacyFile)throw new Error('legacy_seed_fixed_fixture_only');
  const fullPath=path.join(fixturesDir,legacyFile),stat=fs.lstatSync(fullPath);
  if(!stat.isFile()||stat.isSymbolicLink()||fs.realpathSync(fullPath)!==fullPath)
    throw new Error('legacy_seed_fixture_integrity');
  const bytes=fs.readFileSync(fullPath),descriptor=validateLegacySeedFixture(bytes,fixtureManifest);
  const current=await evaluate('('+pageFreshStorage.toString()+')('+JSON.stringify(seedSpec)+')');
  const before=await persistence();
  const ready={allowed:legacySeedAllowed,owned:freshOwnedProfile,consumed:seedConsumed,
    mutations:mutationsBeforeSeed,initial:initialFreshStorage,current};
  const attemptId='legacy-seed-'+(++sequence);
  legacySeedReceipt={schema_version:'ux-legacy-seed.v1',attempt_id:attemptId,
    fixture:legacyFile,fixture_sha256:descriptor.fixture_sha256,
    product_commit:descriptor.product_commit,product_loader_sha256:descriptor.product_loader_sha256,
    product_validation_sha256:descriptor.product_validation_sha256,
    fresh_owned_profile:freshOwnedProfile&&current.fresh===true,
    initial_storage_match:initialFreshStorage?.sha256===current.sha256,
    source_key:descriptor.storage_key,target_key:descriptor.target_key,
    source_snapshot_ids:descriptor.snapshot_ids,source_included_files_absent:true,source_list_completeness_absent:true,
    storage_before:before,storage_after:before,reload_observed:false,migration_validated:false,status:'rejected'};
  const record=suffix=>fs.writeFileSync(path.join(evidenceDir,attemptId+'-'+suffix+'.json'),
    JSON.stringify(legacySeedReceipt)+'\n',{mode:0o600,flag:'wx'});
  // The latch is consumed before the first possible storage mutation. An error
  // or lost response can never cause the same profile to receive another seed.
  seedConsumed=true;
  try {requireLegacySeedReady(ready);}
  catch(error){record('rejected');throw error;}
  legacySeedReceipt.status='uncertain';
  record('intent');
  try {
    await evaluate('('+pageApplyLegacySeed.toString()+')('+JSON.stringify(bytes.toString('utf8'))+','+
      JSON.stringify(descriptor.fixture_sha256)+','+JSON.stringify(initialFreshStorage.sha256)+','+
      JSON.stringify(targetOrigin)+','+JSON.stringify(seedSpec)+')');
    await send('Page.reload',{ignoreCache:true});
    const until=Date.now()+3500;
    let state;
    do {
      await new Promise(resolve=>setTimeout(resolve,100));
      try {
        state=await evaluate('('+pageReadLegacyState.toString()+')('+JSON.stringify(attemptId)+','+JSON.stringify(seedSpec)+')');
        if(isValidatedLegacyMigration(state,descriptor))break;
      }catch(error) {
        // Reload destroys the old execution context. Poll only the new document;
        // no write, reload, browser action or model call is retried.
        if(!String(error.message).includes('context')&&!String(error.message).includes('page_evaluation_failed'))throw error;
      }
    }while(Date.now()<until);
    legacySeedReceipt.storage_after=await persistence();
    legacySeedReceipt.reload_observed=state?.available===true;
    legacySeedReceipt.migration_validated=isValidatedLegacyMigration(state,descriptor)
      &&state.storage_sha256===legacySeedReceipt.storage_after.sha256
      &&legacySeedReceipt.storage_after.sha256!==before.sha256;
    if(!legacySeedReceipt.migration_validated)throw new Error('legacy_seed_migration_unconfirmed');
    legacySeedReceipt.status='validated';
    record('receipt');
  }catch(error) {
    legacySeedReceipt.status='uncertain';
    try {legacySeedReceipt.storage_after=await persistence();}catch{}
    record('uncertain');
    throw new Error('legacy_seed_uncertain_no_retry:'+String(error.message).slice(0,100));
  }
}
export function observationResult(state,capture) {
  return {text:'URL '+state.url+'\nTitle '+state.title+'\n'+state.text,
    facts:{...state,last_action:'observe'},captures:[capture],checks:[]};
}
async function act(input,commandId) {
  return await actionBudget.run(commandId,input.name,()=>actWithinBudget(input));
}
async function actWithinBudget(input) {
  const name=input.name, args=input.arguments||{};
  let uploadedFixture=null, uploadProgressSamples=[], importAttempt=null, clickDispatch=null, scrollAttempt=null;
  const extraCaptures=[];
  if (name==='observe') {
    const state=await observe(); const capture=await screenshot();
    return observationResult(state,capture);
  }
  if(name!=='seed_legacy_unknown'&&!['observe','wait'].includes(name))mutationsBeforeSeed++;
  if(name==='seed_legacy_unknown') {
    await actionBudget.phase('legacy_seed');
    await seedLegacyUnknown(args);
  } else if (['upload','upload_cancel','upload_save_failure'].includes(name)) {
    const selector=args.selector, filename=args.file;
    if (typeof filename!=='string' || path.basename(filename)!==filename) throw new Error('fixture_name_invalid');
    const groupName=filename.startsWith('@group:')?filename.slice(7):null;
    const names=groupName?(fixtureManifest.groups?.[groupName]||[]):[filename];
    if (!names.length || names.some(name=>typeof name!=='string'||path.basename(name)!==name)) throw new Error('fixture_not_allowlisted');
    const entries=names.map(name=>fixtureManifest.files.find(row=>row.name===name));
    if (entries.some(entry=>!entry)) throw new Error('fixture_not_allowlisted');
    const legacyFile = fixtureManifest?.coverage?.legacy_seed?.fixture;
    if(legacyFile && names.includes(legacyFile))throw new Error('legacy_seed_requires_bounded_tool');
    if(name==='upload_cancel' && !approvedCancelFixture(entries))
      throw new Error('cancel_fixture_not_allowlisted');
    const faultKey = fixtureManifest?.storage_fault_key || args.storage_key || '';
    if(name==='upload_save_failure' && (entries.length!==1 || entries[0].bytes>1048576
        || entries[0].storage_fault_eligible===false || !faultKey))
      throw new Error('storage_fault_fixture_not_allowlisted');
    await actionBudget.phase('upload_fixture_validation',{fixture_count:entries.length});
    await validateFixtureFiles({files:entries},fixturesDir,actionBudget.signal,fs.promises,
      {timeoutMs:DRIVER_DEADLINES_MS.act,code:'browser_action_timeout'});
    const fullPaths=names.map(name=>path.join(fixturesDir,name));
    await actionBudget.phase('upload_target_resolution');
    const document=await send('DOM.getDocument',{depth:-1,pierce:false});
    const found=await send('DOM.querySelector',{nodeId:document.root.nodeId,selector});
    if (!found.nodeId) throw new Error('upload_target_missing');
    const described=await send('DOM.describeNode',{nodeId:found.nodeId});
    const node=described.node;
    const attrs=Object.fromEntries((node.attributes||[]).reduce((out,value,index,array)=>{if(index%2===0)out.push([value,array[index+1]]);return out;},[]));
    if (node.nodeName!=='INPUT' || attrs.type!=='file') throw new Error('upload_target_not_single_file_input');
    const before=await persistence();
    if(name==='upload_save_failure' && (!before.available || !before.keys.includes(faultKey)))
      throw new Error('storage_fault_baseline_missing');
    importAttempt={schema_version:'ux-import-attempt.v1',attempt_id:'upload-'+String(sequence),
      tool:name,fixture:filename,fixture_sha256:entries.length===1?entries[0].sha256:null,
      storage_before:before,phase_samples:[],cancel_active:false,cancel_dispatched:false};
    activeImportAttemptId=importAttempt.attempt_id;
    if(name!=='upload')extraCaptures.push(await screenshot());
    let faultArmed=false;
    const progressContract = fixtureManifest?.progress_contract || DEFAULT_PROGRESS_CONTRACT;
    const progressMarkers = progressContract?.active_markers || [];
    try {
      if(name==='upload_save_failure'){
        await evaluate('('+pageArmStorageFailure.toString()+')('+JSON.stringify(faultKey)+')');faultArmed=true;
      }
      await actionBudget.phase('upload_dispatch');
      await send('DOM.setFileInputFiles',{files:fullPaths,nodeId:found.nodeId});
      uploadedFixture=filename;
      if(name==='upload_cancel'){
        const cancellation=await runCancellationAttempt({
          readPhase:()=>evaluate('('+pageImportState.toString()+')('+JSON.stringify(progressContract)+')'),
          dispatchCancel:target=>guardedClick(target.selector,target.label,progressMarkers.length > 0),
          pause:ms=>new Promise(resolve=>setTimeout(resolve,ms)),now:()=>Date.now()
        });
        Object.assign(importAttempt,cancellation);
        uploadProgressSamples=cancellation.phase_samples;
      } else {
        const started=Date.now();let lastPhase=null;
        while(Date.now()-started<(name==='upload_save_failure'?5000:1200)){
          const current=await evaluate('('+pageImportState.toString()+')('+JSON.stringify(progressContract)+')');
          if(current.phase && current.phase!==lastPhase && uploadProgressSamples.length<32){
            uploadProgressSamples.push({elapsed_ms:Date.now()-started,text:current.phase});lastPhase=current.phase;
          }
          if(name==='upload_save_failure'){
            const fault=await evaluate('('+pageReadStorageFailure.toString()+')()');
            if(fault?.consumed){await new Promise(resolve=>setTimeout(resolve,100));break;}
          } else if(current.complete || (!current.active && Date.now()-started>500))break;
          await new Promise(resolve=>setTimeout(resolve,25));
        }
        importAttempt.phase_samples=uploadProgressSamples;
      }
    } finally {
      if(faultArmed)importAttempt.storage_fault=await evaluate('('+pageReadStorageFailure.toString()+')(true)');
    }
    await actionBudget.phase('upload_observed');
  } else if (name==='click') {
    const selector=args.selector,label=args.label,norm=value=>String(value||'').replace(/\s+/g,' ').trim();
    if (typeof label!=='string' || !label.trim() || label.length>180) throw new Error('click_label_required');
    if(!observedControls.some(row=>row.selector===selector && row.visible===true && !row.disabled && norm(row.label)===norm(label)))
      throw new Error(CLICK_REJECTED);
    const box=await guardedClick(selector,label);
    clickDispatch={dispatched:true,hit_test:true,requested_selector:selector,verified_selector:box.selector,label:box.label};
  } else if (name==='type') {
    const selector=args.selector, value=args.value;
    if (typeof value!=='string'||value.length>500||/[\r\n]/.test(value)) throw new Error('typed_value_limit');
    const expression="(() => {const e=document.querySelector("+JSON.stringify(selector)+");if(!e||!['INPUT','TEXTAREA'].includes(e.tagName)||['password','email','tel','hidden'].includes(e.type)||e.disabled||e.readOnly) return false;e.focus();e.select();return true;})()";
    const focused=await evaluate(expression);
    if (!focused) throw new Error('type_target_not_allowed');
    await send('Input.insertText',{text:value});
    typedInputs.set(selector,hash(Buffer.from(value,'utf8')));
  } else if (name==='scroll') {
    scrollAttempt=await runScrollAttempt({
      inspect:(delta,expected)=>evaluate('('+pageScrollTarget.toString()+')('+JSON.stringify(delta)+','+JSON.stringify(expected)+')'),
      move:point=>send('Input.dispatchMouseEvent',{type:'mouseMoved',...point}),
      wheel:(point,delta)=>send('Input.dispatchMouseEvent',{type:'mouseWheel',...point,deltaX:0,deltaY:delta}),
      pause:ms=>new Promise(resolve=>setTimeout(resolve,ms)),now:()=>Date.now(),
    },args.delta);
  } else if (name==='wait') {
    const ms=Math.max(0,Math.min(3000,args.ms)); await new Promise(r=>setTimeout(r,ms));
  } else throw new Error('unknown_tool');
  const state=await observe(); const capture=await screenshot();
  if(importAttempt){
    importAttempt.storage_after=state.storage_snapshot;
    importAttempt.persistence_unchanged=importAttempt.storage_before.available && state.storage_snapshot.available
      ? importAttempt.storage_before.sha256===state.storage_snapshot.sha256 : null;
    if(importAttempt.terminal_state==='inactive_after_cancel' && importAttempt.persistence_unchanged===true)
      importAttempt.terminal_state='cancelled_without_new_result';
    if(name==='upload_save_failure')importAttempt.terminal_state=importAttempt.storage_fault?.consumed
      ? 'storage_fault_consumed' : 'storage_fault_not_consumed';
  }
  const actionText=scrollAttempt?'Scroll '+scrollAttempt.outcome+'; wheel dispatched='+scrollAttempt.dispatched+
    ', observed movement='+(scrollAttempt.observed_delta||0)+'.':'Action '+name+' completed.';
  return {text:actionText+'\nURL '+state.url+'\nTitle '+state.title+'\n'+state.text,
    facts:{...state,last_action:name,...(name==='click'?{last_action_label:args.label,click_dispatch:clickDispatch}:{}),
      ...(scrollAttempt?{scroll_attempt:scrollAttempt}:{}),
      ...(uploadedFixture?{uploaded_fixture:uploadedFixture,upload_progress_samples:uploadProgressSamples,import_attempt:importAttempt}:{})},
    captures:[...extraCaptures,capture],checks:[]};
}
async function close() {
  if(closePromise)return await closePromise;
  startupController?.abort(new Error('browser_shutdown_requested'));
  actionBudget.abort();
  closePromise=(async()=>{
    await lifecycle('close_started');
    for(const item of pending.values())item.reject(new Error('browser_shutdown_requested'));
    try {ws?.close();}catch{}
    const browserStopped=chromeSpawnFailed||await terminateOwnedChild(chrome);
    const proxyStopped=await closeOwnedProxy(proxy,proxyConnections,{isListenPending:()=>proxyListenPending});
    const result={stopped:browserStopped&&proxyStopped,browser_stopped:browserStopped,proxy_stopped:proxyStopped};
    await lifecycle(result.stopped?'closed':'close_unconfirmed',result);
    // Retain references and ownership diagnostics even when exit is unconfirmed.
    return result;
  })();
  return await closePromise;
}
export async function main() {
process.umask(0o077);
const input = readline.createInterface({input:process.stdin});
const stop=()=>{
  startupController?.abort(new Error('host_shutdown_signal'));
  actionBudget.abort();
  input.close();
  void close().then(result=>process.exit(result.stopped?0:1),()=>process.exit(1));
};
process.once('SIGTERM',stop);process.once('SIGINT',stop);
try {
  for await (const line of input) {
    if(line.length>65536) break;
    let m,replyAttempted=false;
    const commandStarted=performance.now();
    try {m=JSON.parse(line);let result;
      if(m.kind==='start') result=await start(m.payload);
      else if(m.kind==='close') result=await close();
      else result=await act(m.payload,m.id);
      if(m.kind!=='close')await lifecycle('reply_writing',{command_id:m.id,
        command:m.kind,elapsed_ms:Math.round(performance.now()-commandStarted)});
      replyAttempted=true;
      const bytes=await writeReplyOnce(process.stdout,{id:m.id,result},
        {timeoutMs:m.kind==='close'?1000:DRIVER_DEADLINES_MS.reply});
      if(m.kind!=='close')await lifecycle('reply_written',{command_id:m.id,
        command:m.kind,elapsed_ms:Math.round(performance.now()-commandStarted),bytes});
      if(m.kind==='close') break;
    } catch (err) {
      // A timed-out write may already have sent bytes. Never append a second
      // response to that command; the parent preserves its uncertain delivery.
      if(replyAttempted) {
        await lifecycle('reply_uncertain',{command_id:m?.id??null,
          elapsed_ms:Math.round(performance.now()-commandStarted),
          error:String(err?.message||'reply_failed').slice(0,120)});
        break;
      }
      replyAttempted=true;
      try {await writeReplyOnce(process.stdout,{id:m?.id,error:String(err?.message||'browser_tool_failed').slice(0,160)});}
      catch{break;}
      if(m?.kind==='act'&&!closePromise&&!actionBudget.poisoned)continue;
      break;
    }
  }
} finally {
  input.close();
  await close().catch(()=>{});
  process.removeListener('SIGTERM',stop);process.removeListener('SIGINT',stop);
}
}
if (process.argv[1] && import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href) await main();
