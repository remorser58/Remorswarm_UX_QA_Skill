import test from 'node:test';
import assert from 'node:assert/strict';
import { EventEmitter } from 'node:events';
import crypto from 'node:crypto';
import {
  runBounded, validateFixtureFiles, fetchJsonBounded, openSocketBounded,
  childHasExited, terminateOwnedChild, closeOwnedProxy,
} from '../skills/remorsearch-ux-qa/drivers/web/scale_browser_cdp.mjs';

const pause=ms=>new Promise(resolve=>setTimeout(resolve,ms));
const sha=bytes=>crypto.createHash('sha256').update(bytes).digest('hex');
const fixture={name:'fixture.json',bytes:2,sha256:sha(Buffer.from('{}'))};
function fixtureIO({bytes=Buffer.from('{}'),symbolic=false}={}) {
  const reads=[];
  return {reads,
    lstat:async()=>({isFile:()=>true,isSymbolicLink:()=>symbolic,size:2}),
    realpath:async value=>value,
    readFile:async value=>{reads.push(value);return bytes;},
  };
}

test('fixture validation still hashes every file and rejects a changed final fixture',async()=>{
  const files=Array.from({length:544},(_,i)=>({...fixture,name:'fixture-'+i+'.json'}));
  const io=fixtureIO();
  await validateFixtureFiles({files},'/owned',new AbortController().signal,io);
  assert.equal(io.reads.length,544);
  const validRead=io.readFile;
  io.readFile=async value=>value.endsWith('543.json')?Buffer.from('[]'):validRead(value);
  await assert.rejects(validateFixtureFiles({files},'/owned',new AbortController().signal,io),/fixture_integrity/);
});
test('fixture validation rejects symlinks, traversal, wrong byte counts and hashes',async()=>{
  await assert.rejects(validateFixtureFiles({files:[fixture]},'/owned',null,fixtureIO({symbolic:true})),/fixture_integrity/);
  await assert.rejects(validateFixtureFiles({files:[{...fixture,name:'../outside'}]},'/owned',null,fixtureIO()),/fixture_manifest_entry/);
  await assert.rejects(validateFixtureFiles({files:[fixture]},'/owned',null,fixtureIO({bytes:Buffer.from('x')})),/fixture_integrity/);
  await assert.rejects(validateFixtureFiles({files:[fixture]},'/owned',null,fixtureIO({bytes:Buffer.from('[]')})),/fixture_integrity/);
});
test('stalled fixture read aborts before any later startup effect and is not repeated',async()=>{
  const io=fixtureIO();let release,reads=0,spawned=0;
  io.readFile=()=>{reads++;return new Promise(resolve=>{release=resolve;});};
  await assert.rejects(runBounded(async signal=>{
    await validateFixtureFiles({files:[fixture,fixture]},'/owned',signal,io);
    spawned++;
  },15,'browser_start_timeout'),/browser_start_timeout/);
  release(Buffer.from('{}'));
  await pause(5);
  assert.equal(reads,1);assert.equal(spawned,0);
});
test('an already aborted startup never begins an operation',async()=>{
  const controller=new AbortController();controller.abort(new Error('host_shutdown_signal'));
  let called=0;
  await assert.rejects(runBounded(()=>called++,20,'timeout',controller.signal),/host_shutdown_signal/);
  assert.equal(called,0);
});
test('CDP discovery bounds both headers and response JSON and aborts the request',async()=>{
  for(const phase of ['headers','body']) {
    let requestSignal,calls=0;
    const fetcher=async(url,options)=>{
      requestSignal=options.signal;calls++;
      if(phase==='headers')return await new Promise(()=>{});
      return {ok:true,json:()=>new Promise(()=>{})};
    };
    await assert.rejects(fetchJsonBounded('http://127.0.0.1:1/json/list',{timeoutMs:15,fetcher}),/cdp_discovery_timeout/);
    assert.equal(calls,1);assert.equal(requestSignal.aborted,true);
  }
});
test('CDP discovery rejects non-success HTTP without following redirects',async()=>{
  let options;
  await assert.rejects(fetchJsonBounded('http://127.0.0.1:1/json/list',{
    fetcher:async(url,value)=>{options=value;return {ok:false};},
  }),/cdp_discovery_http/);
  assert.equal(options.redirect,'error');
});
class FakeSocket extends EventTarget {
  constructor(){super();this.closed=0;this.listeners=new Set();}
  addEventListener(kind,callback,options){this.listeners.add(callback);super.addEventListener(kind,callback,options);}
  removeEventListener(kind,callback){this.listeners.delete(callback);super.removeEventListener(kind,callback);}
  close(){this.closed++;this.dispatchEvent(new Event('close'));}
}
test('WebSocket that never opens is closed at its deadline and releases listeners',async()=>{
  const socket=new FakeSocket();
  await assert.rejects(openSocketBounded(socket,{timeoutMs:15}),/cdp_websocket_open_timeout/);
  assert.equal(socket.closed,1);assert.equal(socket.listeners.size,0);
});
test('WebSocket close before open fails immediately instead of hanging',async()=>{
  const socket=new FakeSocket();
  const opening=openSocketBounded(socket,{timeoutMs:500});
  socket.dispatchEvent(new Event('close'));
  await assert.rejects(opening,/cdp_websocket_closed_before_open/);
  assert.equal(socket.listeners.size,0);
});
test('successful WebSocket open cleans up its temporary listeners',async()=>{
  const socket=new FakeSocket();
  const opening=openSocketBounded(socket,{timeoutMs:500});
  socket.dispatchEvent(new Event('open'));
  await opening;
  assert.equal(socket.closed,0);assert.equal(socket.listeners.size,0);
});
test('parent shutdown aborts a connecting WebSocket without another connection',async()=>{
  const socket=new FakeSocket(),controller=new AbortController();
  const opening=openSocketBounded(socket,{signal:controller.signal,timeoutMs:500});
  controller.abort(new Error('host_shutdown_signal'));
  await assert.rejects(opening,/host_shutdown_signal/);
  assert.equal(socket.closed,1);
});
class FakeChild extends EventEmitter {
  constructor(){super();this.pid=123;this.exitCode=null;this.signalCode=null;this.signals=[];}
  kill(signal){this.signals.push(signal);this.onKill?.(signal);return true;}
  exit(code,signal){this.exitCode=code;this.signalCode=signal;this.emit('exit',code,signal);}
}
test('already confirmed signal exit is stopped and receives no further signal',async()=>{
  const child=new FakeChild();child.exit(null,'SIGTERM');
  assert.equal(childHasExited(child),true);
  assert.equal(await terminateOwnedChild(child),true);
  assert.deepEqual(child.signals,[]);
});
test('TERM fast exit is subscribed before signal and is confirmed',async()=>{
  const child=new FakeChild();child.onKill=signal=>child.exit(null,signal);
  assert.equal(await terminateOwnedChild(child,{termMs:20,killMs:20}),true);
  assert.deepEqual(child.signals,['SIGTERM']);assert.equal(child.listenerCount('exit'),0);
});
test('KILL dispatch alone does not resolve shutdown before the actual exit event',async()=>{
  const child=new FakeChild();let killed;
  const killObserved=new Promise(resolve=>{killed=resolve;});
  child.onKill=signal=>{if(signal==='SIGKILL')killed();};
  let settled=false;
  const closing=terminateOwnedChild(child,{termMs:10,killMs:200}).then(result=>{settled=true;return result;});
  await killObserved;
  assert.equal(settled,false);
  child.exit(null,'SIGKILL');
  assert.equal(await closing,true);
  assert.deepEqual(child.signals,['SIGTERM','SIGKILL']);
});
test('child without observed exit remains unconfirmed and retains its reference',async()=>{
  const child=new FakeChild();
  assert.equal(await terminateOwnedChild(child,{termMs:10,killMs:10}),false);
  assert.equal(childHasExited(child),false);
  assert.deepEqual(child.signals,['SIGTERM','SIGKILL']);assert.equal(child.listenerCount('exit'),0);
});
test('proxy shutdown destroys only its tracked connections before waiting for close',async()=>{
  const actions=[],owned={destroy:()=>actions.push('owned')},unowned={destroy:()=>actions.push('unowned')};
  void unowned;
  const proxy={closeAllConnections:()=>actions.push('all-owned'),close:callback=>{actions.push('close');callback();}};
  assert.equal(await closeOwnedProxy(proxy,new Set([owned])),true);
  assert.deepEqual(actions,['owned','all-owned','close']);
});
test('proxy close cannot hang cleanup indefinitely or claim confirmed closure',async()=>{
  let callback;
  const proxy={close:done=>{callback=done;}};
  assert.equal(await closeOwnedProxy(proxy,new Set(),{timeoutMs:15}),false);
  callback();
});
test('proxy not-yet-listening is not confused with confirmed stopped during startup',async()=>{
  const proxy={listening:false,close:done=>done(Object.assign(new Error('not running'),{code:'ERR_SERVER_NOT_RUNNING'}))};
  assert.equal(await closeOwnedProxy(proxy,new Set(),{isListenPending:()=>true}),false);
  assert.equal(await closeOwnedProxy(proxy,new Set(),{isListenPending:()=>false}),true);
  proxy.listening=true;
  assert.equal(await closeOwnedProxy(proxy,new Set()),false);
});
