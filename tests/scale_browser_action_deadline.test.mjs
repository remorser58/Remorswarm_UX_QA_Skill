import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import crypto from 'node:crypto';
import {getEventListeners} from 'node:events';
import {
  ActionBudget, DRIVER_DEADLINES_MS, CDP_DEADLINES_MS, sendCdpRequest,
  validateFixtureFiles, writeCaptureBytes, writeReplyOnce,
} from '../skills/remorsearch-ux-qa/drivers/web/scale_browser_cdp.mjs';

const pause=ms=>new Promise(resolve=>setTimeout(resolve,ms));
const sha=bytes=>crypto.createHash('sha256').update(bytes).digest('hex');
function memoryFixture(readFile) {
  return {lstat:async()=>({isFile:()=>true,isSymbolicLink:()=>false,size:2}),
    realpath:async value=>value,readFile};
}
const entry={name:'fixture.json',bytes:2,sha256:sha(Buffer.from('{}'))};
function captureHandle({permissions=0o600,write=async()=>{}}={}) {
  let writes=0,closed=0,size=0;
  return {get writes(){return writes;},get closed(){return closed;},
    stat:async()=>({isFile:()=>true,mode:permissions,size}),
    writeFile:async(bytes,options)=>{writes++;await write(options.signal);size=bytes.length;},
    close:async()=>{closed++;}};
}

function cdpHarness() {
  let now=0,nextId=0,nextTimer=0;
  const packets=[],pending=new Map(),timers=new Map();
  return {packets,pending,timers,get now(){return now;},set now(value){now=value;},
    send:(method,options={})=>sendCdpRequest({
      socket:{send:bytes=>packets.push(JSON.parse(bytes))},pending,id:++nextId,method,
      now:()=>now,setTimer:(callback,delay)=>{const id=++nextTimer;timers.set(id,{callback,delay});return id;},
      clearTimer:id=>timers.delete(id),...options,
    }),
    // This is the same pending entry used by the production websocket handler.
    reply:(id,result)=>pending.get(id)?.resolve(result),
  };
}

test('one screenshot reply after the former ten-second cap completes within thirty seconds without replay',async()=>{
  const h=cdpHarness(),controller=new AbortController();
  assert.deepEqual(CDP_DEADLINES_MS,{default:10000,screenshot:30000});
  const running=h.send('Page.captureScreenshot',{params:{format:'png'},signal:controller.signal});
  assert.equal(h.timers.values().next().value.delay,30000);
  assert.equal(h.pending.size,1);
  h.now=15000;h.reply(1,{data:'authored screenshot response'});
  assert.deepEqual(await running,{data:'authored screenshot response'});
  assert.deepEqual(h.packets,[{id:1,method:'Page.captureScreenshot',params:{format:'png'}}]);
  assert.equal(h.pending.size,0);assert.equal(h.timers.size,0);
  assert.equal(getEventListeners(controller.signal,'abort').length,0);
  h.reply(1,{data:'late duplicate'});assert.equal(h.packets.length,1);
});
test('ordinary CDP methods retain a ten-second deadline and dispatch only once',async()=>{
  for(const method of ['Runtime.evaluate','Page.navigate','DOM.setFileInputFiles']) {
    const h=cdpHarness(),running=h.send(method),timer=h.timers.values().next().value;
    assert.equal(timer.delay,10000);h.now=10000;timer.callback();
    await assert.rejects(running,error=>error.message==='cdp_timeout:'+method);
    assert.equal(h.packets.length,1);assert.equal(h.pending.size,0);assert.equal(h.timers.size,0);
  }
});
test('a response at its monotonic deadline is rejected before a delayed timer callback',async()=>{
  for(const [method,deadline] of [['Page.captureScreenshot',30000],['Runtime.evaluate',10000]]) {
    const h=cdpHarness(),running=h.send(method),timer=h.timers.values().next().value;
    h.now=deadline;h.reply(1,{late:true});
    await assert.rejects(running,error=>error.message==='cdp_timeout:'+method);
    timer.callback();h.reply(1,{late:true});
    assert.equal(h.packets.length,1);assert.equal(h.pending.size,0);assert.equal(h.timers.size,0);
  }
});
test('a pre-aborted screenshot request sends zero packets and creates no pending work',async()=>{
  const h=cdpHarness(),controller=new AbortController();
  controller.abort(new Error('host_shutdown_signal'));
  await assert.rejects(h.send('Page.captureScreenshot',{signal:controller.signal}),/host_shutdown_signal/);
  assert.equal(h.packets.length,0);assert.equal(h.pending.size,0);assert.equal(h.timers.size,0);
  assert.equal(getEventListeners(controller.signal,'abort').length,0);
});
test('abort after screenshot dispatch removes pending work and ignores a late response without replay',async()=>{
  const h=cdpHarness(),controller=new AbortController();
  const running=h.send('Page.captureScreenshot',{signal:controller.signal}),entry=h.pending.get(1);
  assert.equal(h.packets.length,1);assert.equal(getEventListeners(controller.signal,'abort').length,1);
  controller.abort(new Error('browser_action_aborted'));
  await assert.rejects(running,/browser_action_aborted/);
  assert.equal(h.pending.size,0);assert.equal(h.timers.size,0);
  assert.equal(getEventListeners(controller.signal,'abort').length,0);
  entry.resolve({late:true});h.reply(1,{late:true});
  assert.equal(h.packets.length,1);assert.equal(h.pending.size,0);
});
test('the overall eighty-second action deadline dominates a screenshot with fifteen seconds remaining',async()=>{
  const h=cdpHarness(),budget=new ActionBudget({now:()=>h.now});
  let dispatched,entry;
  const ready=new Promise(resolve=>{dispatched=resolve;});
  const running=budget.run(18,'observe',async current=>{
    h.now=65000;
    return await h.send('Page.captureScreenshot',{signal:current.signal,check:()=>current.check(),
      socket:{send:bytes=>{h.packets.push(JSON.parse(bytes));entry=h.pending.get(1);dispatched();}}});
  });
  await ready;
  assert.equal(h.timers.values().next().value.delay,30000);
  h.now=80000;h.reply(1,{tooLateForAction:true});
  await assert.rejects(running,/browser_action_timeout/);
  assert.equal(budget.poisoned,true);assert.equal(budget.signal.aborted,true);
  assert.equal(h.pending.size,0);assert.equal(h.timers.size,0);
  entry.resolve({late:true});
  await assert.rejects(budget.run(19,'observe',()=>h.send('Page.captureScreenshot')),/transport_uncertain/);
  assert.equal(h.packets.length,1);
});
test('an already elapsed action deadline prevents screenshot dispatch before its CDP timer begins',async()=>{
  const h=cdpHarness(),budget=new ActionBudget({now:()=>h.now});
  await assert.rejects(budget.run(20,'observe',current=>{
    h.now=80000;
    return h.send('Page.captureScreenshot',{signal:current.signal,check:()=>current.check()});
  }),/browser_action_timeout/);
  assert.equal(budget.poisoned,true);assert.equal(h.packets.length,0);
  assert.equal(h.pending.size,0);assert.equal(h.timers.size,0);
});
test('a synchronous socket send failure clears the pending timer and abort listener without retry',async()=>{
  const h=cdpHarness(),controller=new AbortController();let sends=0;
  await assert.rejects(h.send('Page.captureScreenshot',{signal:controller.signal,
    socket:{send:()=>{sends++;throw new Error('socket_send_failed');}}}),/socket_send_failed/);
  assert.equal(sends,1);assert.equal(h.pending.size,0);assert.equal(h.timers.size,0);
  assert.equal(getEventListeners(controller.signal,'abort').length,0);
});
test('websocket error and close reject every pending request and leave no timers or abort listeners',async()=>{
  for(const reason of ['cdp_websocket_error','cdp_websocket_closed']) {
    const h=cdpHarness(),controller=new AbortController();
    const first=h.send('Page.captureScreenshot',{signal:controller.signal});
    const second=h.send('Runtime.evaluate',{signal:controller.signal});
    const rejected=Promise.all([assert.rejects(first,error=>error.message===reason),
      assert.rejects(second,error=>error.message===reason)]);
    for(const entry of h.pending.values())entry.reject(new Error(reason));
    await rejected;
    assert.equal(h.packets.length,2);assert.equal(h.pending.size,0);assert.equal(h.timers.size,0);
    assert.equal(getEventListeners(controller.signal,'abort').length,0);
  }
});

test('a delayed single action response completes within its declared budget once',async()=>{
  const events=[],budget=new ActionBudget({timeoutMs:90,record:async(phase,detail)=>events.push({phase,...detail})});
  let calls=0;
  const result=await budget.run(12,'upload',async current=>{
    calls++;await current.phase('fixture_validation');await pause(35);
    current.check();await current.phase('observed');return {completed:true};
  });
  assert.deepEqual(result,{completed:true});assert.equal(calls,1);assert.equal(budget.poisoned,false);
  assert.ok(events.every(row=>row.command_id===12&&row.action==='upload'&&row.elapsed_ms>=0));
  assert.equal(events.at(-1).action_phase,'completed');
});
test('action timeout keeps an aborted signal and cannot continue or replay after a late read',async()=>{
  const budget=new ActionBudget({timeoutMs:15}),events=[];
  let release,calls=0,mutations=0;
  await assert.rejects(budget.run(1,'upload',async current=>{
    calls++;await new Promise(resolve=>{release=resolve;});current.check();mutations++;
  }),/browser_action_timeout/);
  assert.equal(budget.poisoned,true);assert.equal(budget.signal.aborted,true);
  release();await pause(5);
  await assert.rejects(budget.run(2,'upload',async()=>events.push('replayed')),/transport_uncertain/);
  assert.equal(calls,1);assert.equal(mutations,0);assert.deepEqual(events,[]);
});
test('elapsed-time check catches a delayed event loop before another mutation',async()=>{
  let now=0,mutations=0;
  const budget=new ActionBudget({timeoutMs:80,now:()=>now});
  await assert.rejects(budget.run(3,'click',async current=>{
    now=81;current.check();mutations++;
  }),/browser_action_timeout/);
  assert.equal(mutations,0);assert.equal(budget.poisoned,true);
});
test('a known nondispatched click rejection remains recoverable by a distinct observation',async()=>{
  const budget=new ActionBudget({timeoutMs:100}),calls=[];
  await assert.rejects(budget.run(4,'click',async()=>{calls.push('click');throw new Error('click_target_not_allowed_or_visible');}),/click_target/);
  assert.equal(budget.poisoned,false);
  await budget.run(5,'observe',async()=>{calls.push('observe');return {};});
  assert.deepEqual(calls,['click','observe']);
});
test('host shutdown aborts the current action and does not permit a later action',async()=>{
  const budget=new ActionBudget({timeoutMs:100});
  const running=budget.run(6,'wait',async current=>{
    await new Promise(resolve=>current.signal.addEventListener('abort',resolve,{once:true}));
    current.check();
  });
  await Promise.resolve();budget.abort();
  await assert.rejects(running,/browser_action_aborted/);
  assert.equal(budget.poisoned,true);
});
test('upload validation awaits the full hash before a single simulated dispatch',async()=>{
  const budget=new ActionBudget({timeoutMs:100});let reads=0,dispatches=0;
  const io=memoryFixture(async()=>{reads++;await pause(15);return Buffer.from('{}');});
  await budget.run(7,'upload',async current=>{
    await validateFixtureFiles({files:[entry]},'/owned',current.signal,io,
      {timeoutMs:100,code:'browser_action_timeout'});
    current.check();dispatches++;
  });
  assert.equal(reads,1);assert.equal(dispatches,1);
});
test('aborted upload validation never dispatches after the file read eventually returns',async()=>{
  const budget=new ActionBudget({timeoutMs:15});let release,reads=0,dispatches=0;
  const io=memoryFixture(()=>{reads++;return new Promise(resolve=>{release=resolve;});});
  await assert.rejects(budget.run(8,'upload',async current=>{
    await validateFixtureFiles({files:[entry]},'/owned',current.signal,io,
      {timeoutMs:100,code:'browser_action_timeout'});
    current.check();dispatches++;
  }),/browser_action_timeout/);
  release(Buffer.from('{}'));await pause(5);
  assert.equal(reads,1);assert.equal(dispatches,0);
});
test('capture creation preserves exclusive path, private mode and exact-byte digest',async()=>{
  const root=fs.mkdtempSync(path.join(os.tmpdir(),'owned-capture-test-')),bytes=Buffer.from('authored PNG bytes');
  try {
    const result=await writeCaptureBytes(root,'browser-00001.png',bytes,new AbortController().signal);
    assert.deepEqual(result,{path:'browser-00001.png',sha256:sha(bytes)});
    assert.deepEqual(fs.readFileSync(path.join(root,result.path)),bytes);
    assert.equal(fs.statSync(path.join(root,result.path)).mode&0o077,0);
    await assert.rejects(writeCaptureBytes(root,result.path,Buffer.from('changed')),/EEXIST/);
    assert.deepEqual(fs.readFileSync(path.join(root,result.path)),bytes);
    await assert.rejects(writeCaptureBytes(root,'../outside.png',bytes),/capture_path_invalid/);
    fs.symlinkSync(path.join(root,result.path),path.join(root,'browser-00002.png'));
    await assert.rejects(writeCaptureBytes(root,'browser-00002.png',bytes),/EEXIST/);
  }finally {fs.rmSync(root,{recursive:true,force:true});}
});
test('late exclusive open is closed without writing after action abort',async()=>{
  const budget=new ActionBudget({timeoutMs:15}),handle=captureHandle();let opened=0,release,admitted=0;
  const io={open:()=>{opened++;return new Promise(resolve=>{release=resolve;});}};
  await assert.rejects(budget.run(9,'observe',async current=>{
    await writeCaptureBytes('/owned','browser-00003.png',Buffer.from('x'),current.signal,io);admitted++;
  }),/browser_action_timeout/);
  release(handle);await pause(5);
  assert.equal(opened,1);assert.equal(handle.writes,0);assert.equal(handle.closed,1);assert.equal(admitted,0);
});
test('late screenshot write is never admitted or written again',async()=>{
  const budget=new ActionBudget({timeoutMs:15});let release,admitted=0;
  const handle=captureHandle({write:()=>new Promise(resolve=>{release=resolve;})});
  await assert.rejects(budget.run(10,'observe',async current=>{
    await writeCaptureBytes('/owned','browser-00004.png',Buffer.from('x'),current.signal,{open:async()=>handle});admitted++;
  }),/browser_action_timeout/);
  release();await pause(5);
  assert.equal(handle.writes,1);assert.equal(handle.closed,1);assert.equal(admitted,0);
});
test('an unexpectedly permissive capture is rejected before bytes are written',async()=>{
  const handle=captureHandle({permissions:0o644});
  await assert.rejects(writeCaptureBytes('/owned','browser-00005.png',Buffer.from('x'),null,{open:async()=>handle}),/capture_permissions/);
  assert.equal(handle.writes,0);assert.equal(handle.closed,1);
});
test('single reply tolerates backpressure and waits for the original write callback',async()=>{
  const writes=[];let release,settled=false;
  const stream={write:(bytes,callback)=>{writes.push(bytes);release=callback;return false;}};
  const writing=writeReplyOnce(stream,{id:11,result:{ok:true}},{timeoutMs:100}).then(bytes=>{settled=true;return bytes;});
  await Promise.resolve();await Promise.resolve();
  assert.equal(settled,false);assert.equal(writes.length,1);
  release();assert.equal(await writing,Buffer.byteLength(writes[0]));
  assert.deepEqual(JSON.parse(writes[0]),{id:11,result:{ok:true}});
});
test('reply flush timeout never writes a replacement packet when the callback arrives late',async()=>{
  const writes=[];let release;
  const stream={write:(bytes,callback)=>{writes.push(bytes);release=callback;return false;}};
  await assert.rejects(writeReplyOnce(stream,{id:12,result:{}},{timeoutMs:15}),/reply_flush_timeout/);
  release();await pause(5);
  assert.equal(writes.length,1);assert.equal(JSON.parse(writes[0]).id,12);
});
test('reply write error is propagated without a retry',async()=>{
  let calls=0;
  await assert.rejects(writeReplyOnce({write:(bytes,callback)=>{calls++;callback(new Error('pipe_failed'));}},{id:13,result:{}}),/pipe_failed/);
  assert.equal(calls,1);
});
test('driver phase budgets leave time for the single response write',()=>{
  assert.equal(DRIVER_DEADLINES_MS.start,60000);
  assert.equal(DRIVER_DEADLINES_MS.act,80000);
  assert.equal(DRIVER_DEADLINES_MS.reply,5000);
});
