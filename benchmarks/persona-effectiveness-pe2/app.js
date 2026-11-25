'use strict';
const id = new URLSearchParams(location.search).get('case');
const cases={V7Q:{kind:'plant',fault:false},J2N:{kind:'audio',fault:true},H8C:{kind:'walk',fault:false},R5B:{kind:'plant',fault:true},L9F:{kind:'audio',fault:false},D3W:{kind:'walk',fault:true}};
const c=cases[id],root=document.getElementById('app');
const esc=x=>String(x).replace(/[&<>"']/g,z=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[z]));
if(!c){root.innerHTML='<p>Select a case using the runner.</p>';} else {
root.innerHTML=`<h2>Case ${id}</h2><section id="work"></section>`;
const work=document.getElementById('work');
if(c.kind==='plant'){
 let bad=false;
 work.innerHTML='<h3>Plant care note</h3><p>Fern needs a watering interval of 1–14 whole days.</p><label>Interval in days<input aria-label="Interval in days" inputmode="numeric" value="7"></label><button>Save care note</button><p role="alert"></p><p role="status">No care note saved.</p>';
 const input=work.querySelector('input'),alert=work.querySelector('[role=alert]'),status=work.querySelector('[role=status]');
 input.oninput=()=>{if(!c.fault){bad=false;alert.textContent='';}};
 work.querySelector('button').onclick=()=>{const n=Number(input.value);if(!/^\d+$/.test(input.value)||n<1||n>14){bad=true;alert.textContent='Enter a whole number from 1 to 14.';return;}if(bad&&c.fault){alert.textContent='Enter a whole number from 1 to 14.';return;}alert.textContent='';status.textContent=`Saved: Fern, every ${n} days.`;};
}
if(c.kind==='audio'){
 let queue=['Morning Birds','River Sounds'],pending=false;
 const render=()=>{work.innerHTML='<h3>Listening queue</h3><p>Remove one episode only after confirming. Cancel keeps the queue unchanged.</p><ul>'+queue.map(x=>`<li>${esc(x)}</li>`).join('')+'</ul>'+(queue.includes('Morning Birds')&&!pending?'<button>Remove Morning Birds</button>':'')+(pending?'<div role="dialog" aria-label="Remove episode"><p>Remove Morning Birds from this queue?</p><button>Confirm removal</button><button>Cancel</button></div>':'')+'<p role="status">'+(queue.length===2?'2 episodes queued.':'1 episode queued.')+'</p>'; for(const b of work.querySelectorAll('button'))b.onclick=()=>{if(b.textContent==='Remove Morning Birds'){pending=true;}else if(b.textContent==='Confirm removal'){queue=queue.filter(x=>x!=='Morning Birds');pending=false;}else{if(c.fault)queue=queue.filter(x=>x!=='Morning Birds');pending=false;}render();};};render();
}
if(c.kind==='walk'){
 let first=true;
 work.innerHTML='<h3>Park walk plan</h3><p>Choose a route preference. The first preview attempt deliberately encounters a simulated temporary outage. Retry should retain your choice.</p><label>Route preference<select aria-label="Route preference"><option>Shortest path</option><option>Avoid stairs</option></select></label><button>Preview walk</button><p role="alert"></p><p role="status">No preview yet.</p>';
 const select=work.querySelector('select'),button=work.querySelector('button'),alert=work.querySelector('[role=alert]'),status=work.querySelector('[role=status]');
 button.onclick=()=>{if(first){first=false;alert.textContent='Temporary preview outage. Retry your request.';button.textContent='Retry preview';return;}if(c.fault)select.value='Shortest path';alert.textContent='';status.textContent=select.value==='Avoid stairs'?'Preview: Riverside ramp, 1.2 km, no stairs.':'Preview: Hill steps, 0.8 km, includes stairs.';button.textContent='Preview walk';};
}
}
