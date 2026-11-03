/* Read the same maintained manual in Studio and in the standalone documentation. */
(() => {
  'use strict';
  const sources=new Map(), requests=new Map();
  let activeContainer, activeKey='', generation=0;
  async function load(guide='editor'){
    const key=guide==='streamerbot'?'streamerbot':'appearance';
    if(sources.has(key))return sources.get(key);
    if(!requests.has(key))requests.set(key,fetch(key==='streamerbot'?'/docs/streamerbot-alert.html':'/docs/widget-editor.html').then(async response=>{
      if(!response.ok)throw Error('Не удалось загрузить руководство.');
      const parsed=new DOMParser().parseFromString(await response.text(),'text/html');
      const main=parsed.querySelector('main');
      if(!main)throw Error('В руководстве не найден текст.');
      sources.set(key,main);return main;
    }).catch(error=>{requests.delete(key);throw error;}));
    return requests.get(key);
  }
  function wireCodeCopy(container){
    container.querySelectorAll('[data-alert-copy]').forEach(button=>button.onclick=async()=>{
      const code=container.querySelector('[data-alert-code]')?.textContent;
      const status=container.querySelector('[data-alert-copy-status]');
      if(!code)return;
      try {
        try {await navigator.clipboard.writeText(code);}
        catch(error){const field=document.createElement('textarea');field.value=code;field.style.cssText='position:fixed;opacity:0';document.body.append(field);field.select();const copied=document.execCommand('copy');field.remove();button.focus();if(!copied)throw error;}
        status.textContent='Код скопирован';
      } catch(error){status.textContent='Не удалось скопировать. Выдели код и скопируй вручную.';}
    });
  }
  async function mountAlertExample(container){
    if(container.dataset.loaded)return;
    container.textContent='Загружаю пример…';
    try {
      const main=await load('streamerbot'),code=main.querySelector('[data-alert-code]');
      if(!code)throw Error('Пример не найден. Открой полный гайд.');
      container.innerHTML='<div class="guidebook-code-actions"><button type="button" class="secondary" data-alert-copy>Скопировать код</button><span data-alert-copy-status role="status"></span></div><pre class="guidebook-code"><code data-alert-code></code></pre>';
      container.querySelector('[data-alert-code]').textContent=code.textContent;
      container.dataset.loaded='true';wireCodeCopy(container);
    } catch(error){container.textContent=error.message;const retry=document.createElement('button');retry.textContent='Попробовать ещё раз';retry.onclick=()=>mountAlertExample(container);container.append(retry);}
  }
  const route=(guide,chapter='')=>'#guidebook/appearance/'+guide+(chapter?'/'+encodeURIComponent(chapter):'');
  async function mount(container,guide='',chapter=''){
    if(!guide){
      ++generation;activeContainer=container;activeKey='catalog';
      const icons={editor:'M4 4h16v16H4Z M4 9h16 M9 9v11 M13 13h4 M13 16h4',ai:'M8 4h8v4h4v12H4V8h4Z M9 12h.01 M15 12h.01 M9 16h6',streamerbot:'M6 17h12l-2-3V9a4 4 0 0 0-8 0v5Z M10 20h4'};
      container.innerHTML='<section class="guidebook" data-guidebook-catalog><div class="guidebook-tiles">'+[['editor','Гайд по оформлению','Слои, прогресс, маски, шрифты и подключение готового виджета к OBS'],['ai','Гайд по нейросетям','Как описать идею, получить совместимый код и доработать результат в редакторе'],['streamerbot','Оповещение о донате','Streamer.bot и OBS: оформление с нуля, готовый код, очередь и необязательный звук']].map(([id,title,description])=>'<a class="guidebook-tile" href="'+route(id)+'">'+(id==='ai'?'<span class="guidebook-ai-mark" aria-hidden="true">AI</span>':'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><path d="'+icons[id]+'"/></svg>')+'<h3>'+title+'</h3><p>'+description+'</p><span>Читать гайд →</span></a>').join('')+'</div></section>';
      return;
    }
    guide=['ai','streamerbot'].includes(guide)?guide:'editor';
    const key=guide+'/'+chapter,ticket=++generation;
    if(activeContainer===container&&activeKey===key)return;
    activeContainer=container;activeKey=key;
    container.innerHTML='<section class="guidebook" aria-label="Гайдбук"><a class="guidebook-back" href="#guidebook/appearance">← Все гайды</a><div class="guidebook-layout"><nav class="guidebook-chapters" aria-label="Главы гайда" data-guidebook-chapters></nav><article class="guidebook-article" data-guidebook-article aria-live="polite"><p>Загружаю руководство…</p></article></div></section>';

    try{
      const main=await load(guide);if(ticket!==generation)return;
      const article=container.querySelector('[data-guidebook-article]');article.replaceChildren();
      const heading=document.createElement('h2');heading.textContent=guide==='ai'?'Создание виджета с ИИ':guide==='streamerbot'?'Оповещение о донате в Streamer.bot':'Создание своего донат-гола';article.append(heading);
      let ai=false;
      for(const node of main.children){
        if(node.id==='ai-introduction')ai=true;
        if((guide==='ai')!==ai||node.tagName==='H1'||node.id==='ai-introduction')continue;
        article.append(node.cloneNode(true));
      }
      // The guide is trusted local documentation; do not execute scripts or carry page-level IDs into Studio.
      article.querySelectorAll('script,iframe,object,embed').forEach(node=>node.remove());
      for(const node of article.querySelectorAll('[id]'))node.id='guidebook-'+node.id;
      for(const link of article.querySelectorAll('a[href^="#"]')){const id=link.getAttribute('href').slice(1);link.href=route(guide==='streamerbot'?'streamerbot':id.startsWith('ai-')?'ai':'editor',id);}
      wireCodeCopy(article);
      const chapters=container.querySelector('[data-guidebook-chapters]');
      for(const title of article.querySelectorAll('h2[id]')){
        const id=title.id.slice('guidebook-'.length),link=document.createElement('a');
        link.href=route(guide,id);link.dataset.guidebookChapter=id;link.textContent=title.textContent;
        if(id===chapter)link.setAttribute('aria-current','location');chapters.append(link);
      }
      if(chapter){const target=article.querySelector('#'+CSS.escape('guidebook-'+chapter));if(target)target.scrollIntoView({block:'start',behavior:'instant'});}
    }catch(error){if(ticket!==generation)return;activeKey='';const article=container.querySelector('[data-guidebook-article]');article.textContent=error.message;const retry=document.createElement('button');retry.className='secondary';retry.textContent='Попробовать ещё раз';retry.onclick=()=>mount(container,guide,chapter);article.append(retry);}
  }
  window.VDGGuidebook={mount,mountAlertExample};
})();
