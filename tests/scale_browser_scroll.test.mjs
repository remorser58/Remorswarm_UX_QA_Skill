import test from 'node:test';
import assert from 'node:assert/strict';
import { pageScrollTarget, runScrollAttempt } from '../skills/remorsearch-ux-qa/drivers/web/scale_browser_cdp.mjs';

function fakePage({modal=true,covered=false,bodyHeight=84,bodyScrollHeight=1000}={}) {
  const rect=(left,top,right,bottom)=>({left,top,right,bottom,width:right-left,height:bottom-top});
  const create=(tag,bounds,parent=null,style={})=>{
    const e={nodeType:1,tagName:tag.toUpperCase(),parentElement:parent,children:[],
      previousElementSibling:parent?.children.at(-1)||null,style:{display:'block',visibility:'visible',overflowY:'visible',paddingTop:'0',paddingBottom:'0',...style},
      bounds,scrollTop:0,scrollHeight:bounds.height,clientHeight:bounds.height,modal:false};
    if(parent)parent.children.push(e);
    e.getBoundingClientRect=()=>e.bounds;
    e.contains=hit=>{for(let p=hit;p;p=p.parentElement)if(p===e)return true;return false;};
    e.closest=()=>{for(let p=e;p;p=p.parentElement)if(p.modal)return p;return null;};
    e.querySelectorAll=()=>e.children.flatMap(child=>[child,...child.querySelectorAll('*')]);
    return e;
  };
  const html=create('html',rect(0,0,756,413)),body=create('body',rect(0,0,756,2000),html);
  html.scrollHeight=2000;
  const background=create('main',rect(0,0,756,413),body,{overflowY:'auto'});background.scrollHeight=2000;
  const sheet=create('section',rect(118,96,638,318),body,{overflowY:'hidden'});sheet.modal=modal;
  const header=create('header',rect(118,96,638,156),sheet);
  const scroller=create('article',rect(118,156,638,156+bodyHeight),sheet,{overflowY:'auto'});
  scroller.clientHeight=bodyHeight;scroller.scrollHeight=bodyScrollHeight;
  const content=create('p',rect(130,156,620,1156),scroller);
  const footer=create('footer',rect(118,240,638,318),sheet);
  const cover=create('aside',rect(118,156,638,240),sheet);
  const inside=(e,x,y)=>x>=e.bounds.left&&x<e.bounds.right&&y>=e.bounds.top&&y<e.bounds.bottom;
  const selectors=new Map([['html',html],['body',body],['body>main:nth-of-type(1)',background],
    ['body>section:nth-of-type(1)',sheet],['body>section:nth-of-type(1)>article:nth-of-type(1)',scroller]]);
  const state={covered,modal,scroller,html,sheet,background};
  const document={body,documentElement:html,scrollingElement:html,activeElement:body,
    querySelectorAll:()=>state.modal?[sheet]:[],querySelector:s=>selectors.get(s)||null,
    elementFromPoint:(x,y)=>{
      if(state.modal&&inside(sheet,x,y)){
        if(state.covered&&inside(cover,x,y))return cover;
        if(inside(scroller,x,y))return content;
        if(inside(header,x,y))return header;
        if(inside(footer,x,y))return footer;
        return sheet;
      }
      return background;
    }};
  const values={document,window:{scrollX:0,scrollY:0},innerWidth:756,innerHeight:413,getComputedStyle:e=>e.style};
  const previous=new Map(Object.keys(values).map(key=>[key,Object.getOwnPropertyDescriptor(globalThis,key)]));
  for(const [key,value] of Object.entries(values))Object.defineProperty(globalThis,key,{value,configurable:true,writable:true});
  state.restore=()=>{for(const [key,value] of previous)value?Object.defineProperty(globalThis,key,value):delete globalThis[key];};
  return state;
}
function ioFor(state,{movement=60,coverAfterMove=false,uncertain=false}={}) {
  let clock=0,reads=0;
  const events=[];
  return {events,reads:()=>reads,io:{
    now:()=>clock,pause:async ms=>{clock+=ms;},
    inspect:async(delta,expected)=>{reads++;return pageScrollTarget(delta,expected);},
    move:async point=>{events.push({type:'move',point});if(coverAfterMove)state.covered=true;},
    wheel:async(point,delta)=>{events.push({type:'wheel',point,delta});if(uncertain)throw new Error('unknown_wheel_delivery');state.scroller.scrollTop+=movement;},
  }};
}

test('short active modal selects its exposed 84px body, never the background or fixed y400',()=>{
  const page=fakePage();
  try{
    const selected=pageScrollTarget(400);
    assert.equal(selected.status,'ready');assert.equal(selected.scope,'modal');
    assert.equal(selected.target.selector,'body>section:nth-of-type(1)>article:nth-of-type(1)');
    assert.deepEqual(selected.viewport,{width:756,height:413});
    assert.equal(selected.target.client_height,84);
    assert.ok(selected.target.point.y>156&&selected.target.point.y<240);
    assert.equal(page.scroller.scrollTop,0);
  }finally{page.restore();}
});
test('covered modal body refuses a wheel instead of falling through to background',async()=>{
  const page=fakePage({covered:true}),fixture=ioFor(page);
  try{
    const result=await runScrollAttempt(fixture.io,400);
    assert.equal(result.outcome,'scroll_target_occluded');assert.equal(result.dispatched,false);
    assert.deepEqual(fixture.events,[]);
  }finally{page.restore();}
});
test('zero-height scroll body is explicit evidence and never repaired by DOM writes',async()=>{
  const page=fakePage({bodyHeight:0}),fixture=ioFor(page);
  try{
    const result=await runScrollAttempt(fixture.io,400);
    assert.equal(result.outcome,'scroll_area_has_no_usable_height');
    assert.equal(result.blocked_areas[0].client_height,0);
    assert.equal(result.dispatched,false);assert.equal(page.scroller.scrollTop,0);
    assert.deepEqual(fixture.events,[]);
  }finally{page.restore();}
});
test('content that fits the modal produces an explicit no-scrollable-area outcome',async()=>{
  const page=fakePage({bodyScrollHeight:84}),fixture=ioFor(page);
  try{
    const result=await runScrollAttempt(fixture.io,400);
    assert.equal(result.outcome,'no_scrollable_area');assert.equal(result.dispatched,false);
    assert.deepEqual(fixture.events,[]);
  }finally{page.restore();}
});
test('scrolling at the top boundary does not chain to background',async()=>{
  const page=fakePage(),fixture=ioFor(page);
  try{
    const result=await runScrollAttempt(fixture.io,-400);
    assert.equal(result.outcome,'at_boundary');assert.equal(result.dispatched,false);
    assert.deepEqual(fixture.events,[]);
  }finally{page.restore();}
});
test('new cover after pointer movement prevents native wheel dispatch',async()=>{
  const page=fakePage(),fixture=ioFor(page,{coverAfterMove:true});
  try{
    const result=await runScrollAttempt(fixture.io,400);
    assert.equal(result.outcome,'target_not_visible_or_scrollable');assert.equal(result.dispatched,false);
    assert.deepEqual(fixture.events.map(e=>e.type),['move']);
  }finally{page.restore();}
});
test('one wheel reports measured 60px movement rather than requested 400px',async()=>{
  const page=fakePage(),fixture=ioFor(page);
  try{
    const result=await runScrollAttempt(fixture.io,400);
    assert.equal(result.outcome,'scrolled');assert.equal(result.dispatched,true);
    assert.equal(result.requested_delta,400);assert.equal(result.delta,67);
    assert.equal(result.before.scroll_top,0);assert.equal(result.after.scroll_top,60);
    assert.equal(result.observed_delta,60);assert.equal(result.background_moved,false);
    assert.deepEqual(fixture.events.map(e=>e.type),['move','wheel']);
  }finally{page.restore();}
});
test('a delivered wheel with no movement is bounded and never silently retried',async()=>{
  const page=fakePage(),fixture=ioFor(page,{movement:0});
  try{
    const result=await runScrollAttempt(fixture.io,400);
    assert.equal(result.outcome,'no_movement');assert.equal(result.dispatched,true);
    assert.equal(result.moved,false);assert.equal(result.observed_delta,0);
    assert.equal(result.observation_window_ms,300);assert.equal(fixture.reads(),14);
    assert.equal(fixture.events.filter(e=>e.type==='wheel').length,1);
  }finally{page.restore();}
});
test('unknown wheel delivery propagates once without a second dispatch',async()=>{
  const page=fakePage(),fixture=ioFor(page,{uncertain:true});
  try{
    await assert.rejects(runScrollAttempt(fixture.io,400),/unknown_wheel_delivery/);
    assert.equal(fixture.events.filter(e=>e.type==='wheel').length,1);
  }finally{page.restore();}
});
test('background scroll is observed explicitly, never reported as an ordinary modal scroll',async()=>{
  const page=fakePage(),fixture=ioFor(page);
  const wheel=fixture.io.wheel;
  fixture.io.wheel=async(...args)=>{await wheel(...args);window.scrollY=20;};
  try{
    const result=await runScrollAttempt(fixture.io,400);
    assert.equal(result.outcome,'background_moved');assert.equal(result.background_moved,true);
    assert.equal(result.document_after.y,20);
  }finally{page.restore();}
});
test('page scrolling remains available when no modal owns interaction',()=>{
  const page=fakePage({modal:false});
  try{
    const result=pageScrollTarget(400);
    assert.equal(result.status,'ready');assert.equal(result.scope,'page');
    assert.equal(result.target.selector,'body>main:nth-of-type(1)');
  }finally{page.restore();}
});
test('delta is bounded and invalid input cannot cause a native event',async()=>{
  const page=fakePage(),fixture=ioFor(page);
  try{
    const result=await runScrollAttempt(fixture.io,2000);
    assert.equal(result.requested_delta,2000);assert.equal(result.delta,67);assert.equal(fixture.events[1].delta,67);
    await assert.rejects(runScrollAttempt(fixture.io,1.5),/scroll_delta_invalid/);
    assert.equal(fixture.events.filter(e=>e.type==='wheel').length,1);
  }finally{page.restore();}
});
