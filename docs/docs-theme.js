/* Standalone reference controls: no app data or external dependency required. */
(() => {
  'use strict';
  const slot=document.getElementById('sidebarThemeSlot');
  let mode=matchMedia('(prefers-color-scheme: light)').matches?'light':'dark';
  try{mode=localStorage.getItem('vdg-reference-theme')||mode;}catch(_){}
  const button=document.createElement('button');button.type='button';
  function apply(){document.body.dataset.docTheme=mode;button.textContent=mode==='dark'?'Светлая тема':'Тёмная тема';}
  button.onclick=()=>{mode=mode==='dark'?'light':'dark';apply();try{localStorage.setItem('vdg-reference-theme',mode);}catch(_){}};
  slot.append(button);apply();
  if(['127.0.0.1','localhost','[::1]'].includes(location.hostname)&&['3333','3347'].includes(location.port))document.querySelector('.local-admin').hidden=false;
  const heads=[...document.querySelectorAll('main h2[id],main h3[id],main h4[id]')];
  const entries=heads.map(heading=>{
    let text='';for(let el=heading.nextElementSibling;el&&!/^H[1-4]$/.test(el.tagName);el=el.nextElementSibling)text+=' '+el.textContent;
    return {heading,title:heading.firstChild.textContent,text:text.replace(/\s+/g,' ').trim()};
  });
  const input=document.getElementById('docSearch'),results=document.getElementById('docSearchResults');
  input.addEventListener('input',()=>{
    const query=input.value.trim().toLocaleLowerCase('ru');results.replaceChildren();results.hidden=!query;if(!query)return;
    const words=query.split(/\s+/),found=entries.filter(e=>words.every(word=>(e.title+' '+e.text).toLocaleLowerCase('ru').includes(word)));
    const label=document.createElement('p');label.setAttribute('role','status');label.textContent=found.length?'Найдено разделов: '+found.length:'Совпадений нет. Попробуйте имя параметра или сервиса.';results.append(label);
    for(const e of found.slice(0,15)){const link=document.createElement('a');link.href='#'+e.heading.id;link.textContent=e.title;const snippet=document.createElement('small');const first=e.text.toLocaleLowerCase('ru').indexOf(words[0]);snippet.textContent=(first>40?'…':'')+e.text.slice(Math.max(0,first-40),Math.max(0,first-40)+160)+'…';link.append(snippet);results.append(link);}
  });
  input.addEventListener('keydown',event=>{if(event.key==='Escape'){input.value='';input.dispatchEvent(new Event('input'));}});
  const nav=[...document.querySelectorAll('.nav a')];
  if('IntersectionObserver' in window){const observer=new IntersectionObserver(entries=>{for(const entry of entries)if(entry.isIntersecting)nav.forEach(link=>{if(link.hash==='#'+entry.target.id)link.setAttribute('aria-current','location');else link.removeAttribute('aria-current');});},{rootMargin:'-5% 0px -75% 0px'});document.querySelectorAll('main h2[id]').forEach(h=>observer.observe(h));}
})();
