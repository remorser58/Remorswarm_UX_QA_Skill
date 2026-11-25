'use strict';
const fs=require('node:fs'),path=require('node:path'),readline=require('node:readline');
const {performance}=require('node:perf_hooks');
const CASES=['V7Q','J2N','H8C','R5B','L9F','D3W'];
async function main(){
 const out=process.env.EVIDENCE_DIR;fs.mkdirSync(out,{recursive:false});
 const {chromium}=require(process.env.PLAYWRIGHT_MODULE);
 const browser=await chromium.launch({headless:true});
 let closing=false;const close=async()=>{if(closing)return;closing=true;await browser.close();};
 for(const signal of ['SIGINT','SIGTERM'])process.once(signal,()=>{void close().finally(()=>process.exit(signal==='SIGINT'?130:143));});
 const context=await browser.newContext({viewport:{width:1100,height:800}}),page=await context.newPage();
 page.setDefaultTimeout(2500);page.setDefaultNavigationTimeout(2500);
 const origin=`http://127.0.0.1:${process.env.PORT}`;
 await context.route('**/*',r=>r.request().url().startsWith(origin+'/')?r.continue():r.abort());
 let count=0,seq=0,first=null;
 const stamp=()=>({wall:new Date().toISOString(),monotonic_ms:performance.now()});
 const elapsed=()=>first?performance.now()-first.monotonic_ms:0;
 const emit=x=>{fs.appendFileSync(path.join(out,'actions.jsonl'),JSON.stringify(x)+'\n');process.stdout.write(JSON.stringify(x)+'\n');};
 emit({ready:true,actions:count,elapsed_ms:0,case_ids:CASES});
 const input=readline.createInterface({input:process.stdin,crlfDelay:Infinity});
 try{for await(const line of input){
  const start=stamp();let cmd,ok=false,error,blocked=false,screenshot,text='',controls=[],actionEnd;
  const sequence=++seq;
  try{
   cmd=JSON.parse(line);if(!cmd||Array.isArray(cmd)||typeof cmd!=='object')throw Error('One operation object required');
   const counted=['goto','click','fill','select','key'].includes(cmd.op);
   if(counted){if(count>=60||elapsed()>=720000){blocked=true;throw Error('Blocked: action or time budget exhausted');}if(!first)first=start;count++;}
   else if(!['observe','screenshot'].includes(cmd.op))throw Error('Unsupported operation');
   if(cmd.op==='goto'){if(!CASES.includes(cmd.case))throw Error('Unknown case');await page.goto(origin+'/?case='+cmd.case,{waitUntil:'domcontentloaded'});}
   else if(counted){
    if(typeof cmd.name!=='string')throw Error('Exact accessible name required');
    let loc;if(cmd.op==='fill'||cmd.op==='select')loc=page.getByLabel(cmd.name,{exact:true});else loc=page.getByRole(cmd.role||'button',{name:cmd.name,exact:true});
    if(cmd.op==='click')await loc.click();
    if(cmd.op==='fill'){if(typeof cmd.value!=='string')throw Error('String value required');await loc.fill(cmd.value);}
    if(cmd.op==='select')await loc.selectOption({label:cmd.value});
    if(cmd.op==='key'){if(!['Enter','Tab','Space','Escape','ArrowDown','ArrowUp'].includes(cmd.key))throw Error('Unsupported key');await loc.press(cmd.key);}
   }
   ok=true;
  }catch(e){error=e.message;}finally{actionEnd=stamp();}
  try{text=await page.locator('body').innerText({timeout:2500});for(const control of await page.locator('input,select,textarea').all()){if(await control.isVisible()){const type=await control.getAttribute('type');controls.push({label:await control.getAttribute('aria-label'),value:await control.inputValue(),...(['checkbox','radio'].includes(type)?{checked:await control.isChecked()}:{})});}}screenshot=`${String(sequence).padStart(3,'0')}.png`;await page.screenshot({path:path.join(out,screenshot),timeout:2500});}catch(e){ok=false;error=(error?error+'; ':'')+'Evidence unavailable: '+e.message;}
  emit({sequence,command:cmd||line,ok,blocked,error,start,end:actionEnd,evidence_end:stamp(),first_action_origin:first,actions:count,elapsed_ms:elapsed(),text,controls,screenshot});
 }}finally{await close();}
}
main().catch(e=>{console.error(e.message);process.exitCode=1;});
