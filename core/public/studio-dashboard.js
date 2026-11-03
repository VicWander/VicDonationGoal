/* Studio dashboard layout editor. Actual data and controls are mounted by the
   shell into data-live-slot nodes; this module owns only the validated layout. */
(() => {
'use strict';
const COLUMNS=12, MAX_ROWS=128, MAX_HEIGHT=30, GAP=16;
const types={
 connections:{title:'Подключения',description:'Состояние донат-сервисов и Streamer.bot.',w:12,h:2,minW:6,minH:2},
 latest:{title:'Последние донаты',description:'Последние поступления и сообщения.',w:8,h:14,minW:4,minH:6},
 goal:{title:'Текущая цель',description:'Название, сумма и прогресс цели.',w:4,h:4,minW:4,minH:4},
 manual:{title:'Ручной донат',description:'Форма добавления доната вручную.',w:4,h:11,minW:4,minH:8},
 speech:{title:'Озвучка',description:'Состояние очереди и управление воспроизведением.',w:4,h:6,minW:4,minH:5},
 top:{title:'TopDonation',description:'Рейтинг донатеров.',w:4,h:6,minW:4,minH:5},
 summary:{title:'Сводка донатов',description:'Общая сумма и количество поступлений.',w:4,h:3,minW:4,minH:3},
 rates:{title:'Курсы валют',description:'Текущие курсы и форма их обновления.',w:4,h:7,minW:4,minH:5},
 ttsQueue:{title:'Очередь озвучки',description:'Сообщения в очереди на воспроизведение.',w:4,h:7,minW:4,minH:5},
 ttsTest:{title:'Быстрый тест озвучки',description:'Проверка голоса и отправка тестового сообщения.',w:4,h:10,minW:4,minH:6},
 ttsHistory:{title:'История озвучки',description:'Пять последних записей и их результат.',w:4,h:6,minW:4,minH:5},
 services:{title:'Сервисы и интеграции',description:'Включённые интеграции и переход к их настройкам.',w:4,h:7,minW:4,minH:4}
};
const categories=[
 {id:'donations',title:'Донаты',ids:['latest','goal','manual','top','summary','rates']},
 {id:'speech',title:'Озвучка',ids:['speech','ttsQueue','ttsTest','ttsHistory']},
 {id:'integrations',title:'Интеграции',ids:['connections','services']}
];
const defaults=()=>[
 {id:'connections',x:0,y:0,w:12,h:2}, {id:'latest',x:0,y:2,w:8,h:14},
 {id:'goal',x:8,y:2,w:4,h:4}, {id:'manual',x:8,y:6,w:4,h:11}
];
const clone=items=>items.map(item=>({...item}));
const clamp=(value,min,max)=>Math.max(min,Math.min(max,Math.round(Number(value)||0)));
const overlap=(a,b)=>a.x<b.x+b.w && a.x+a.w>b.x && a.y<b.y+b.h && a.y+a.h>b.y;
function validate(items){
 if(!Array.isArray(items)||items.length>Object.keys(types).length)throw Error('Неверный список блоков.');
 const seen=new Set(),placed=[];
 for(const raw of items){
  if(!raw||typeof raw!=='object'||!Object.hasOwn(types,raw.id)||seen.has(raw.id))throw Error('Неизвестный или повторяющийся блок.');
  if(Object.keys(raw).sort().join(',')!=='h,id,w,x,y')throw Error('Неверные поля блока.');
  const t=types[raw.id];
  if(!['x','y','w','h'].every(k=>Number.isInteger(raw[k]))||raw.x<0||raw.y<0||raw.w<t.minW||raw.h<t.minH||raw.w>COLUMNS||raw.h>MAX_HEIGHT||raw.x+raw.w>COLUMNS||raw.y+raw.h>MAX_ROWS)throw Error('Блок выходит за допустимые размеры сетки.');
  if(placed.some(other=>overlap(raw,other)))throw Error('Блоки перекрываются.');
  seen.add(raw.id);placed.push({...raw});
 }
 return placed;
}
// Stable vertical gravity preserves columns and dimensions. Process from top to
// bottom, stopping on the highest horizontally intersecting earlier block.
function compact(items){
 const sorted=validate(items).sort((a,b)=>a.y-b.y||a.x-b.x),placed=[];
 for(const raw of sorted){
  const b={...raw,y:0};
  for(const other of placed){
   if(b.x<other.x+other.w&&b.x+b.w>other.x)b.y=Math.max(b.y,other.y+other.h);
  }
  placed.push(b);
 }
 return validate(placed.sort((a,b)=>a.y-b.y||a.x-b.x));
}
// During an edit, neighbouring blocks move down. If there is no space, reject
// the entire operation rather than truncate a block or save overlapping cells.
function arrange(items,priority){
 const placed=[];
 const sorted=clone(items).sort((a,b)=>a.id===priority?-1:b.id===priority?1:a.y-b.y||a.x-b.x);
 for(const raw of sorted){
  const t=types[raw.id],b={...raw,w:clamp(raw.w,t.minW,COLUMNS),h:clamp(raw.h,t.minH,MAX_HEIGHT)};
  b.x=clamp(raw.x,0,COLUMNS-b.w);b.y=clamp(raw.y,0,MAX_ROWS-b.h);
  while(placed.some(other=>overlap(b,other))){b.y++;if(b.y+b.h>MAX_ROWS)throw Error('В сетке нет места. Перемести блок выше или уменьши его размер.');}
  placed.push(b);
 }
 return compact(placed);
}
// One vertical key press crosses the next block in the same columns. A single
// row step would be undone immediately by gravity on a compacted layout.
function keyboardMove(items,block,key){
 if(key==='ArrowLeft')return {x:block.x-1};
 if(key==='ArrowRight')return {x:block.x+1};
 const down=key==='ArrowDown';
 const neighbours=items.filter(other=>other.id!==block.id&&other.x<block.x+block.w&&other.x+other.w>block.x&&
  (down?other.y>=block.y+block.h:other.y+other.h<=block.y));
 neighbours.sort((a,b)=>down?a.y-b.y||a.x-b.x:b.y-a.y||a.x-b.x);
 const next=neighbours[0];
 return {y:next?(down?next.y+next.h:next.y):block.y};
}
let saved=defaults(),draft=clone(saved),editing=false,loading=true,saving=false,error='',api=null,drag=null;
let catalogDialog=null,loadSequence=0;
const current=()=>editing?draft:saved;
const reduced=()=>window.matchMedia&&window.matchMedia('(prefers-reduced-motion: reduce)').matches;
function toast(message){if(api&&typeof api.toast==='function')api.toast(message);}
function refresh(animate=true){
 if(!api||typeof api.render!=='function')return;
 const before=new Map([...document.querySelectorAll('.dashboard-block')].map(el=>[el.dataset.block,el.getBoundingClientRect()]));
 const scroll=window.scrollY;
 if(typeof api.beforeRender==='function')api.beforeRender();
 api.render();
 window.scrollTo(0,scroll);
 if(animate&&!reduced())document.querySelectorAll('.dashboard-block').forEach(el=>{
  if(typeof el.animate!=='function')return;
  const old=before.get(el.dataset.block),now=el.getBoundingClientRect();
  if(old&&now.width&&now.height){const dx=old.left-now.left,dy=old.top-now.top;if(dx||dy||old.width!==now.width||old.height!==now.height)el.animate([{transform:`translate(${dx}px,${dy}px) scale(${old.width/now.width},${old.height/now.height})`},{transform:'none'}],{duration:230,easing:'cubic-bezier(.16,1,.3,1)'});}
  else el.animate([{opacity:0,transform:'scale(.985)'},{opacity:1,transform:'none'}],{duration:180});
 });
}
async function request(options){
 const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),10000);
 try{const response=await fetch('/api/ui/settings',{...options,signal:controller.signal});if(!response.ok)throw Error('HTTP '+response.status);const result=await response.json();if(result.ok!==true)throw Error('Настройки не подтверждены сервером.');return result;}
 finally{clearTimeout(timer);}
}
async function load(){
 const sequence=++loadSequence;loading=true;error='';refresh(false);
 try{
  const result=await request();
  const widgets=validate(result.settings&&result.settings.dashboard&&result.settings.dashboard.widgets);
  if(sequence!==loadSequence)return;
  saved=clone(widgets);draft=clone(saved);editing=false;
 }catch(_){if(sequence===loadSequence)error='Не удалось загрузить раскладку. Показана исходная раскладка; настройка будет доступна после успешной загрузки.';}
 finally{if(sequence===loadSequence){loading=false;refresh(false);}}
}
function actions(){
 if(loading)return '<button class="secondary" disabled>Загружаю раскладку…</button>';
 if(error&&!editing)return '<button class="secondary" data-board-action="reload">Повторить загрузку</button>';
 return editing?`<button class="secondary" data-board-action="cancel" ${saving?'disabled':''}>Отмена</button><button data-board-action="save" ${saving?'disabled':''}>${saving?'Сохраняю…':'Сохранить раскладку'}</button>`:'<button class="secondary" data-board-action="edit">Настроить главную</button>';
}
function render(){
 const blocks=current();
 return `${error?'<p class="dashboard-error" role="alert">'+error+'</p>':''}${editing?`<div class="dashboard-editbar"><div><strong>Настройка главной</strong><p>Перемещай за заголовок. Размер — за нижний правый угол или через поля Ш / В. Стрелки клавиатуры тоже работают.</p></div><div class="inline-actions"><button data-board-action="catalog" ${saving?'disabled':''}>Добавить блок</button><button class="secondary" data-board-action="reset" ${saving?'disabled':''}>Исходная раскладка</button></div></div><p class="dashboard-narrow-hint">На узком окне блоки выстроены в колонку. Для свободного перемещения разверни окно шире.</p>`:''}<div class="dashboard-grid ${editing?'is-editing':''}" aria-label="Блоки главной страницы" aria-busy="${loading||saving}">${blocks.map(block=>`<section class="studio-dashboard-block dashboard-block ${editing?'editable':''}" data-block="${block.id}" style="grid-column:${block.x+1}/span ${block.w};grid-row:${block.y+1}/span ${block.h};--block-order:${block.y*12+block.x}" aria-label="${types[block.id].title}">${editing?`<div class="dashboard-block-tools"><button type="button" class="dashboard-drag" data-drag="${block.id}" ${saving?'disabled':''} aria-label="Переместить: ${types[block.id].title}" title="Перетащи или используй стрелки клавиатуры"><svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true" fill="currentColor"><circle cx="5" cy="4" r="1"/><circle cx="11" cy="4" r="1"/><circle cx="5" cy="8" r="1"/><circle cx="11" cy="8" r="1"/><circle cx="5" cy="12" r="1"/><circle cx="11" cy="12" r="1"/></svg><span>${types[block.id].title}</span></button><button type="button" class="dashboard-remove" data-board-action="remove" data-id="${block.id}" ${saving?'disabled':''} aria-label="Убрать: ${types[block.id].title}">Убрать</button></div><div class="dashboard-size"><label>Ш <input data-size="w" data-id="${block.id}" type="number" aria-label="Ширина: ${types[block.id].title}" min="${types[block.id].minW}" max="12" value="${block.w}" ${saving?'disabled':''}></label><span>/ 12</span><label>В <input data-size="h" data-id="${block.id}" type="number" aria-label="Высота: ${types[block.id].title}" min="${types[block.id].minH}" max="${Math.min(MAX_HEIGHT,MAX_ROWS-block.y)}" value="${block.h}" ${saving?'disabled':''}></label></div>`:''}<div class="dashboard-body" ${editing?'inert':''}><div data-live-slot="${block.id}"></div></div>${editing?`<button type="button" class="dashboard-resize" data-resize="${block.id}" ${saving?'disabled':''} aria-label="Изменить размер: ${types[block.id].title}" title="Потяни за угол или используй стрелки"><svg viewBox="0 0 16 16" width="16" height="16" stroke="currentColor" fill="none" stroke-width="1.5" aria-hidden="true"><path d="M6 13 13 6 M10 13l3-3"/></svg></button>`:''}</section>`).join('')}</div>${blocks.length?'':`<section class="panel dashboard-empty"><h2>Главная пока пустая</h2><p>Добавь нужные блоки. Разделы программы доступны слева независимо от раскладки.</p>${editing?'<button data-board-action="catalog">Добавить блок</button>':''}</section>`}`;
}
function closeCatalog(){if(catalogDialog){catalogDialog.close();catalogDialog.remove();catalogDialog=null;}}
function updateCatalog(){
 if(!catalogDialog)return;
 const query=catalogDialog.querySelector('[data-catalog-search]').value.trim().toLocaleLowerCase('ru');
 const filter=catalogDialog.querySelector('[data-catalog-filter]').value;
 let count=0;
 for(const group of catalogDialog.querySelectorAll('[data-catalog-group]')){
  let visible=0;
  for(const item of group.querySelectorAll('[data-catalog-item]')){
   const match=(!filter||filter===group.dataset.catalogGroup)&&(!query||item.textContent.toLocaleLowerCase('ru').includes(query));
   item.hidden=!match;if(match)visible++;
  }
  group.hidden=!visible;count+=visible;
 }
 catalogDialog.querySelector('[data-catalog-empty]').hidden=!!count;
 catalogDialog.querySelector('[data-catalog-count]').textContent=`Найдено блоков: ${count}`;
}
function catalog(){
 const previousScroll=catalogDialog?.scrollTop||0,previousType=document.activeElement?.dataset.type;
 const previousQuery=catalogDialog?.querySelector('[data-catalog-search]')?.value||'';
 const previousFilter=catalogDialog?.querySelector('[data-catalog-filter]')?.value||'';
 closeCatalog();
 catalogDialog=document.createElement('dialog');catalogDialog.className='dashboard-catalog-dialog';catalogDialog.setAttribute('aria-labelledby','dashboardCatalogTitle');
 catalogDialog.innerHTML=`<header class="dashboard-catalog-heading"><h2 id="dashboardCatalogTitle">Добавить блок</h2><button type="button" class="secondary catalog-close" data-board-action="close-catalog" aria-label="Закрыть каталог">×</button></header><p class="muted">Выбери нужные блоки по разделам. Каждый можно добавить один раз, затем изменить его размер и положение.</p><div class="dashboard-catalog-filters"><label>Поиск<input type="search" data-catalog-search placeholder="Название или назначение блока" autocomplete="off"></label><label>Раздел<select data-catalog-filter><option value="">Все разделы</option>${categories.map(c=>`<option value="${c.id}">${c.title}</option>`).join('')}</select></label></div><p class="dashboard-catalog-count" data-catalog-count aria-live="polite"></p><div class="dashboard-catalog">${categories.map(c=>`<section data-catalog-group="${c.id}" class="catalog-group"><h3>${c.title}<span>${c.ids.filter(id=>draft.some(b=>b.id===id)).length} / ${c.ids.length} добавлено</span></h3>${c.ids.map(key=>{const t=types[key],added=draft.some(b=>b.id===key);return `<div class="catalog-item ${added?'is-added':''}" data-catalog-item><div><h4>${t.title}</h4><p>${t.description}</p>${added?'<small>Уже на главной. Убрать можно в режиме настройки.</small>':''}</div><button data-board-action="add" data-type="${key}" ${added?'disabled':''}>${added?'Добавлен':'Добавить'}</button></div>`;}).join('')}</section>`).join('')}<p data-catalog-empty hidden>Ничего не найдено. Измени поиск или выбери другой раздел.</p></div><div class="dashboard-catalog-footer"><button class="secondary" data-board-action="close-catalog">Закрыть</button></div>`;
 catalogDialog.addEventListener('input',updateCatalog);catalogDialog.addEventListener('change',updateCatalog);
 document.body.append(catalogDialog);catalogDialog.showModal();
 if(previousType){const item=catalogDialog.querySelector(`[data-type="${previousType}"]`)?.closest('.catalog-item');const next=item?.nextElementSibling?.querySelector('button:not(:disabled)');(next||catalogDialog.querySelector('.catalog-close'))?.focus({preventScroll:true});}
 catalogDialog.querySelector('[data-catalog-search]').value=previousQuery;
 catalogDialog.querySelector('[data-catalog-filter]').value=previousFilter;
 updateCatalog();
 catalogDialog.scrollTop=previousScroll;
}
function alter(id,values){
 try{draft=arrange(draft.map(b=>b.id===id?{...b,...values}:b),id);error='';refresh();return true;}
 catch(problem){toast(problem.message);refresh(false);return false;}
}
async function save(){
 if(saving||!editing)return;
 const snapshot=validate(draft);saving=true;error='';refresh(false);
 try{
  const result=await request({method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({dashboard:{widgets:snapshot}})});
  const confirmed=validate(result.settings&&result.settings.dashboard&&result.settings.dashboard.widgets);
  saved=clone(confirmed);draft=clone(saved);editing=false;toast('Раскладка сохранена.');
 }catch(_){error='Не удалось сохранить раскладку. Изменения остались в режиме настройки; повтори сохранение.';toast(error);}
 finally{saving=false;refresh();}
}
document.addEventListener('click',event=>{
 const button=event.target.closest('[data-board-action]');if(!button||!api)return;
 event.preventDefault();const action=button.dataset.boardAction;
 if(action==='close-catalog'){closeCatalog();return;}
 if(saving||loading)return;
 switch(action){
  case 'reload':load();break;
  case 'edit':if(!error){editing=true;draft=clone(saved);refresh(false);}break;
  case 'cancel':endDrag(false);closeCatalog();editing=false;draft=clone(saved);error='';refresh();toast('Изменения раскладки отменены.');break;
  case 'save':save();break;
  case 'reset':if(editing){draft=defaults();error='';refresh();toast('Исходная раскладка восстановлена в черновике. Можно сохранить или отменить.');}break;
  case 'catalog':if(editing)catalog();break;
  case 'remove':if(editing){draft=compact(draft.filter(b=>b.id!==button.dataset.id));error='';refresh();}break;
  case 'add':{
   const id=button.dataset.type;if(!editing||!Object.hasOwn(types,id)||draft.some(b=>b.id===id))return;
   const t=types[id];let position=null;
   for(let y=0;y+t.h<=MAX_ROWS&&!position;y++)for(let x=0;x+t.w<=COLUMNS;x++){
    const candidate={id,x,y,w:t.w,h:t.h};if(!draft.some(b=>overlap(candidate,b))){position=candidate;break;}
   }
   if(!position){toast('Нет места для блока. Освободи пространство в сетке.');return;}
   draft=compact([...draft,position]);error='';refresh();catalog();toast(`Блок «${t.title}» добавлен.`);break;
  }
 }
});
document.addEventListener('change',event=>{
 const input=event.target.closest('[data-size]');if(!editing||saving||!input)return;
 const block=draft.find(b=>b.id===input.dataset.id);if(!block)return;
 const key=input.dataset.size;if(!['w','h'].includes(key))return;
 if(!Number.isFinite(Number(input.value))||input.value.trim()===''){refresh(false);toast('Укажи целый размер блока.');return;}
 alter(block.id,{[key]:clamp(input.value,key==='w'?types[block.id].minW:types[block.id].minH,key==='w'?COLUMNS:Math.min(MAX_HEIGHT,MAX_ROWS-block.y))});
});
document.addEventListener('pointerdown',event=>{
 const handle=event.target.closest('[data-drag],[data-resize]');if(!editing||saving||!handle||event.button!==0)return;
 const grid=handle.closest('.dashboard-grid');if(!grid)return;
 if(getComputedStyle(grid).display!=='grid'){toast('Для перетаскивания разверни окно шире. Размеры можно менять полями Ш / В.');return;}
 const id=handle.dataset.drag||handle.dataset.resize,block=draft.find(b=>b.id===id);if(!block)return;
 const rect=grid.getBoundingClientRect(),styles=getComputedStyle(grid),gap=parseFloat(styles.columnGap)||GAP,rowGap=parseFloat(styles.rowGap)||GAP;
 drag={handle,id,block:{...block},mode:handle.dataset.resize?'resize':'move',startX:event.clientX,startY:event.clientY+window.scrollY,stepX:(rect.width+gap)/COLUMNS,stepY:parseFloat(styles.gridAutoRows)+rowGap,gap,rowGap,el:handle.closest('.dashboard-block'),pointerId:event.pointerId,proposed:{...block}};
 handle.setPointerCapture(event.pointerId);drag.el.classList.add('is-dragging');const ghost=document.createElement('div');ghost.className='dashboard-drop-target';ghost.setAttribute('aria-hidden','true');grid.append(ghost);drag.ghost=ghost;drawGhost();event.preventDefault();
});
function drawGhost(){if(!drag)return;const b=drag.proposed;Object.assign(drag.ghost.style,{left:`${b.x*drag.stepX}px`,top:`${b.y*drag.stepY}px`,width:`${b.w*drag.stepX-drag.gap}px`,height:`${b.h*drag.stepY-drag.rowGap}px`});}
document.addEventListener('pointermove',event=>{
 if(!drag||event.pointerId!==drag.pointerId)return;
 const dx=event.clientX-drag.startX,dy=event.clientY+window.scrollY-drag.startY,b=drag.block,t=types[b.id];
 if(drag.mode==='move'){
  drag.proposed={...b,x:clamp(b.x+Math.round(dx/drag.stepX),0,COLUMNS-b.w),y:clamp(b.y+Math.round(dy/drag.stepY),0,MAX_ROWS-b.h)};
  drag.el.style.transform=`translate(${dx}px,${dy}px)`;
 }else drag.proposed={...b,w:clamp(b.w+Math.round(dx/drag.stepX),t.minW,COLUMNS-b.x),h:clamp(b.h+Math.round(dy/drag.stepY),t.minH,Math.min(MAX_HEIGHT,MAX_ROWS-b.y))};
 drawGhost();event.preventDefault();
});
function endDrag(commit){
 if(!drag)return;const item=drag;drag=null;
 item.el.classList.remove('is-dragging');item.el.style.transform='';item.ghost.remove();
 if(item.handle.hasPointerCapture(item.pointerId))item.handle.releasePointerCapture(item.pointerId);
 if(commit)alter(item.id,item.proposed);else refresh(false);
}
document.addEventListener('pointerup',event=>{if(drag&&event.pointerId===drag.pointerId)endDrag(true);});
document.addEventListener('pointercancel',event=>{if(drag&&event.pointerId===drag.pointerId)endDrag(false);});
document.addEventListener('lostpointercapture',event=>{if(drag&&event.pointerId===drag.pointerId)endDrag(false);});
document.addEventListener('keydown',event=>{
 if(event.key==='Escape'&&drag){event.preventDefault();endDrag(false);return;}
 const handle=event.target.closest('[data-drag],[data-resize]');if(!editing||saving||!handle||!['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(event.key))return;
 event.preventDefault();const id=handle.dataset.drag||handle.dataset.resize,b=draft.find(item=>item.id===id);if(!b)return;
 const change=handle.dataset.resize?(event.key==='ArrowLeft'?{w:b.w-1}:event.key==='ArrowRight'?{w:b.w+1}:event.key==='ArrowUp'?{h:b.h-1}:{h:b.h+1}):keyboardMove(draft,b,event.key);
 alter(id,change);document.querySelector(`[${handle.dataset.resize?'data-resize':'data-drag'}="${id}"]`)?.focus({preventScroll:true});
});
window.VDGDashboard={ready:null,connect(value){api=value;},actions,render,get:()=>({widgets:clone(current())}),isEditing:()=>editing};
window.VDGDashboard.ready=load();
})();
