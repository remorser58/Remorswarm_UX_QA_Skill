// Manual local-only regression: one owned Chrome profile, injected about:blank HTML,
// no provider/model call, no product URL, no external resources, unchanged viewport.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { pageScrollTarget, runScrollAttempt } from '../skills/remorsearch-ux-qa/drivers/web/scale_browser_cdp.mjs';

process.umask(0o077);
const root=path.resolve(fileURLToPath(new URL('..',import.meta.url)));
const artifactDir=fs.mkdtempSync(path.join(root,'.ux-loop','scroll-regression-'));
const profile=path.join(artifactDir,'owned-profile');
fs.mkdirSync(profile,{mode:0o700});
const result={schema_version:'local-scroll-regression.v1',started_at:new Date().toISOString(),
  network_policy:'about:blank inline fixture only; deny proxy plus page URL blocking',
  viewport_override:false,
  driver_sha256:crypto.createHash('sha256').update(fs.readFileSync(new URL('../skills/remorsearch-ux-qa/drivers/web/scale_browser_cdp.mjs',import.meta.url))).digest('hex')};
let chrome,ws,sequence=0;
const pending=new Map(),networkRequests=[];
const pause=ms=>new Promise(resolve=>setTimeout(resolve,ms));
function send(method,params={}){
  const id=++sequence;
  return new Promise((resolve,reject)=>{
    const timer=setTimeout(()=>{pending.delete(id);reject(new Error('local_cdp_timeout:'+method));},5000);
    pending.set(id,{resolve,reject,timer});
    ws.send(JSON.stringify({id,method,params}));
  });
}
async function evaluate(expression){
  const response=await send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});
  if(response.exceptionDetails)throw new Error('fixture_evaluation_failed');
  return response.result.value;
}
const fixture=String.raw`<!doctype html><meta charset="utf-8"><style>
*{box-sizing:border-box}html,body{margin:0}body{position:fixed;inset:0;overflow:hidden}
#background{height:3000px;background:#ddd}
.sheet{position:fixed;left:50%;top:96px;transform:translateX(-50%);width:520px;
max-width:calc(100vw - 32px);height:221px;max-height:calc(100dvh - 192px);
display:flex;flex-direction:column;overflow:hidden;background:white}
header{height:60px;flex:0 0 60px}footer{height:77px;flex:0 0 77px}
#scroll-body{flex:1;min-height:0;overflow-y:auto;overscroll-behavior:contain}
#content{position:relative;height:1000px;background:linear-gradient(#eee,#aaa)}
#just-below-fold{position:absolute;top:100px;height:24px}
#cover{display:none;position:absolute;top:60px;left:0;right:0;height:84px;z-index:5}
</style><div id="background">Owned synthetic background</div>
<section class="sheet" role="dialog" aria-modal="true">
<header>Owned short modal</header><article id="scroll-body"><div id="content">Long synthetic content
<button id="just-below-fold" type="button">Owned tab</button></div></article>
<footer>Fixed footer</footer><aside id="cover">Cover</aside></section>`;
try{
  chrome=spawn('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',[
    '--headless=new','--disable-gpu','--no-first-run','--no-default-browser-check',
    '--disable-background-networking','--disable-component-update','--disable-sync','--disable-extensions',
    '--disable-features=Translate,MediaRouter','--disable-quic',
    '--proxy-server=http://127.0.0.1:9','--proxy-bypass-list=<-loopback>',
    '--remote-debugging-port=0','--remote-allow-origins=*','--user-data-dir='+profile,'about:blank',
  ],{stdio:'ignore'});
  let port;
  for(let count=0;count<200;count++){
    if(chrome.exitCode!==null)throw new Error('owned_chrome_exited');
    try{port=Number(fs.readFileSync(path.join(profile,'DevToolsActivePort'),'utf8').split('\n')[0]);}catch{}
    if(port)break;await pause(50);
  }
  assert.ok(port,'owned Chrome must expose its temporary debugging port');
  const targets=await (await fetch('http://127.0.0.1:'+port+'/json/list')).json();
  const target=targets.find(value=>value.type==='page'&&value.url==='about:blank');
  assert.ok(target,'use only the owned initial about:blank target');
  ws=new WebSocket(target.webSocketDebuggerUrl);
  ws.addEventListener('message',event=>{
    const data=JSON.parse(String(event.data));
    if(data.method==='Network.requestWillBeSent')networkRequests.push(data.params.request.url);
    const waiter=pending.get(data.id);
    if(waiter){pending.delete(data.id);clearTimeout(waiter.timer);data.error?waiter.reject(new Error(data.error.message)):waiter.resolve(data.result);}
  });
  await new Promise((resolve,reject)=>{ws.addEventListener('open',resolve,{once:true});ws.addEventListener('error',reject,{once:true});});
  await send('Page.enable');await send('Runtime.enable');await send('Network.enable');
  await send('Network.setBlockedURLs',{urls:['http://*','https://*','ws://*','wss://*','ftp://*','file://*']});
  const {frameTree}=await send('Page.getFrameTree');
  await send('Page.setDocumentContent',{frameId:frameTree.frame.id,html:fixture});
  await evaluate('new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))');
  result.viewport=await evaluate('({width:innerWidth,height:innerHeight})');
  const inspect=async(delta,expected)=>evaluate('('+pageScrollTarget.toString()+')('+JSON.stringify(delta)+','+JSON.stringify(expected)+')');
  const metrics=()=>evaluate('({body:document.getElementById("scroll-body").scrollTop,x:scrollX,y:scrollY,background:document.getElementById("background").scrollTop})');
  const controlVisibility=()=>evaluate('(()=>{const e=document.getElementById("just-below-fold"),r=e.getBoundingClientRect(),b=document.getElementById("scroll-body").getBoundingClientRect();return {fully_visible:r.top>=b.top&&r.bottom<=b.bottom,hit_testable:document.elementFromPoint((r.left+r.right)/2,(r.top+r.bottom)/2)===e};})()');
  const capture=async name=>{const value=await send('Page.captureScreenshot',{format:'png'});fs.writeFileSync(path.join(artifactDir,name),Buffer.from(value.data,'base64'),{flag:'wx',mode:0o600});};
  const nativeWheels=[];
  const io={inspect,move:point=>send('Input.dispatchMouseEvent',{type:'mouseMoved',...point}),
    wheel:async(point,delta)=>{nativeWheels.push({point,delta});await send('Input.dispatchMouseEvent',{type:'mouseWheel',...point,deltaX:0,deltaY:delta});},
    pause,now:()=>Date.now()};
  result.initial=await metrics();
  result.initial_control=await controlVisibility();assert.equal(result.initial_control.fully_visible,false);
  result.selected=await inspect(400,null);
  assert.equal(result.selected.status,'ready');assert.equal(result.selected.scope,'modal');
  assert.ok(result.selected.target.client_height>0&&result.selected.target.client_height<120);
  assert.ok(result.selected.target.point.y<result.selected.modal_bounds.bottom);
  await capture('before.png');
  // Reproduce the saved runner defect within this owned fixture.
  await send('Input.dispatchMouseEvent',{type:'mouseWheel',x:500,y:400,deltaX:0,deltaY:400});
  await pause(250);
  result.old_fixed_point_after=await metrics();
  assert.deepEqual(result.old_fixed_point_after,result.initial,'old off-modal wheel must not move the modal');
  result.modal_scroll=await runScrollAttempt(io,400);
  result.after=await metrics();
  result.after_control=await controlVisibility();
  assert.equal(result.after_control.fully_visible,true);assert.equal(result.after_control.hit_testable,true);
  await capture('after.png');result.captures=['before.png','after.png'];
  assert.equal(result.modal_scroll.dispatched,true);assert.equal(result.modal_scroll.moved,true);
  assert.equal(result.modal_scroll.outcome,'scrolled');assert.equal(result.modal_scroll.background_moved,false);
  assert.ok(result.after.body>result.initial.body);
  assert.equal(result.after.x,result.initial.x);assert.equal(result.after.y,result.initial.y);
  assert.equal(result.after.background,result.initial.background);
  assert.equal(nativeWheels.length,1);
  assert.ok(Math.abs(result.modal_scroll.delta)<=result.selected.target.client_height*.8);
  await evaluate('document.getElementById("scroll-body").style.cssText="flex:0 0 0px;height:0px";true');
  result.zero_height=await runScrollAttempt(io,400);
  assert.equal(result.zero_height.outcome,'scroll_area_has_no_usable_height');
  assert.equal(result.zero_height.dispatched,false);assert.equal(nativeWheels.length,1);
  await evaluate('document.getElementById("scroll-body").style.cssText="";document.getElementById("content").style.height="1px";document.getElementById("just-below-fold").style.display="none";true');
  result.fitting_content=await runScrollAttempt(io,400);
  assert.equal(result.fitting_content.outcome,'no_scrollable_area');
  assert.equal(result.fitting_content.dispatched,false);assert.equal(nativeWheels.length,1);
  await evaluate('document.getElementById("content").style.height="1000px";document.getElementById("cover").style.display="block";true');
  result.covered_body=await runScrollAttempt(io,400);
  assert.equal(result.covered_body.outcome,'scroll_target_occluded');
  assert.equal(result.covered_body.dispatched,false);assert.equal(nativeWheels.length,1);
  result.page_network_requests=networkRequests;
  assert.deepEqual(networkRequests,[],'fixture must issue no network requests');
  result.native_wheels=nativeWheels;result.passed=true;
}catch(error){
  result.passed=false;result.error=String(error?.stack||error);process.exitCode=1;
}finally{
  for(const waiter of pending.values())clearTimeout(waiter.timer);
  try{ws?.close();}catch{}
  if(chrome&&chrome.exitCode===null&&chrome.signalCode===null){
    await new Promise(resolve=>{
      const timer=setTimeout(()=>{if(chrome.exitCode===null&&chrome.signalCode===null)chrome.kill('SIGKILL');resolve();},3000);
      chrome.once('exit',()=>{clearTimeout(timer);resolve();});chrome.kill('SIGTERM');
    });
  }
  fs.rmSync(profile,{recursive:true,force:true});
  result.profile_removed=!fs.existsSync(profile);
  result.finished_at=new Date().toISOString();
  const output=path.join(artifactDir,'result.json');
  fs.writeFileSync(output,JSON.stringify(result,null,2)+'\n',{flag:'wx',mode:0o600});
  console.log(JSON.stringify({passed:result.passed,artifact:output,viewport:result.viewport,
    scroll_delta:result.modal_scroll?.observed_delta,zero_height:result.zero_height?.outcome,
    page_network_requests:networkRequests.length,profile_removed:result.profile_removed,error:result.error}));
}
