/* Animate state changes once, rather than replaying them on every API poll. */
(() => {
'use strict';
const reduced=()=>matchMedia('(prefers-reduced-motion: reduce)').matches;
const selectors='.donor-detail,.donation-expanded-message,.action-menu,tr.details-row';
function identity(el){const row=el.closest('[data-key],[data-donor-id],tr.details-row');return [row?.dataset.key||row?.dataset.donorId||row?.dataset.detailFor||row?.dataset.historyDetail||'',el.matches('.action-menu')?'menu':el.matches('.donor-detail')?'donor':el.matches('.donation-expanded-message')?'donation':'tts'].join(':');}
function expanded(el){return el.dataset.motionTarget?el.dataset.motionTarget==='open':el.matches('.action-menu')?el.classList.contains('open'):!el.hidden;}
function reveal(el){if(!el||reduced())return;el.animate([{opacity:0,transform:'translateY(4px)'},{opacity:1,transform:'none'}],{duration:210,easing:'cubic-bezier(.16,1,.3,1)'});}
function replace(el,html){
 if(!el||(el._vdgLastHTML===html&&el._vdgFirstChild===el.firstChild))return;
 const previous=new Map([...el.querySelectorAll(selectors)].map(node=>[identity(node),{open:expanded(node),height:node.getBoundingClientRect().height}]));
 el.innerHTML=html;el._vdgLastHTML=html;el._vdgFirstChild=el.firstChild;
 if(reduced())return;
 for(const node of el.querySelectorAll(selectors)){
  const before=previous.get(identity(node)),open=expanded(node);
  if(!before||before.open===open)continue;
  node.dataset.motionTarget=open?'open':'closed';
  const menu=node.matches('.action-menu');
  if(menu){node.classList.add('open');const animation=node.animate(open?[{opacity:0,transform:'translateY(-5px) scale(.98)'},{opacity:1,transform:'none'}]:[{opacity:1,transform:'none'},{opacity:0,transform:'translateY(-4px) scale(.98)'}],{duration:170,easing:'cubic-bezier(.16,1,.3,1)'});animation.finished.then(()=>{if(!open)node.classList.remove('open');delete node.dataset.motionTarget;}).catch(()=>{});continue;}
  node.hidden=false;const height=open?node.getBoundingClientRect().height:before.height;
  const overflow=node.style.overflow;node.style.overflow='clip';const style=getComputedStyle(node),paddingTop=style.paddingTop,paddingBottom=style.paddingBottom;
  const collapsed={height:'0px',opacity:0,paddingTop:'0px',paddingBottom:'0px'},full={height:`${height}px`,opacity:1,paddingTop,paddingBottom};
  const animation=node.animate(open?[collapsed,full]:[full,collapsed],{duration:230,easing:'cubic-bezier(.16,1,.3,1)'});
  animation.finished.then(()=>{node.hidden=!open;node.style.overflow=overflow;delete node.dataset.motionTarget;}).catch(()=>{});
 }
}
window.VDGMotion={replace,reveal};
})();
