/* All previews use bundled widget code and synthetic state; no API or analytics. */
(() => {
  'use strict';
  const button=document.getElementById('menuToggle'),nav=document.getElementById('siteNav');
  function closeMenu(){button.setAttribute('aria-expanded','false');nav.dataset.open='false';}
  button.onclick=()=>{const open=button.getAttribute('aria-expanded')!=='true';button.setAttribute('aria-expanded',String(open));nav.dataset.open=String(open);};
  nav.addEventListener('click',event=>{if(event.target.closest('a'))closeMenu();});
  document.addEventListener('keydown',event=>{if(event.key==='Escape'&&button.getAttribute('aria-expanded')==='true'){closeMenu();button.focus();}});
  document.addEventListener('click',event=>{if(!event.target.closest('.header-inner'))closeMenu();});
  const themeButton=document.getElementById('pageTheme');
  const reduced=matchMedia('(prefers-reduced-motion: reduce)');
  const header=document.querySelector('.site-header'),brand=header.querySelector('.brand');
  function syncBrand(){const intro=document.querySelector('.hero').getBoundingClientRect().bottom>header.offsetHeight;header.dataset.intro=String(intro);brand.inert=intro;brand.setAttribute('aria-hidden',String(intro));}
  syncBrand();new IntersectionObserver(syncBrand,{threshold:[0,1],rootMargin:'-80px 0px 0px 0px'}).observe(document.querySelector('.hero'));
  addEventListener('scroll',syncBrand,{passive:true});addEventListener('resize',syncBrand);
  function applyTheme(theme){document.body.dataset.theme=theme;themeButton.textContent=theme==='light'?'Тёмная тема сайта':'Светлая тема сайта';}
  let saved='dark';try{saved=localStorage.getItem('vdg-site-theme')||'dark';}catch(_){}applyTheme(saved);
  themeButton.onclick=()=>{const theme=document.body.dataset.theme==='light'?'dark':'light';applyTheme(theme);try{localStorage.setItem('vdg-site-theme',theme);}catch(_){}};
  let imageRequest=0;
  document.querySelectorAll('[data-theme-preview]').forEach(button=>button.onclick=async()=>{
    document.querySelectorAll('[data-theme-preview]').forEach(b=>b.setAttribute('aria-pressed',String(b===button)));
    const request=++imageRequest,image=document.getElementById('dashboardPreview');
    const src='assets/dashboard-'+button.dataset.themePreview+'.jpg',preload=new Image();preload.src=src;
    try{await preload.decode();}catch(_){return;}
    if(request!==imageRequest)return;
    if(reduced.matches){image.src=src;return;}
    const fade=image.animate([{opacity:1},{opacity:0}],{duration:150,easing:'ease-out',fill:'forwards'});
    try{await fade.finished;}catch(_){return;}
    if(request!==imageRequest){fade.cancel();return;}
    image.src=src;fade.cancel();
    image.animate([{opacity:0},{opacity:1}],{duration:260,easing:'ease-out'});
  });
  const hosts=[...document.querySelectorAll('[data-demo]')],renderers=[];
  const input=document.getElementById('demoProgress'),value=document.getElementById('demoValue');
  for(const host of hosts){
    const doc=host.dataset.preset==='moon'?VDGSiteMoon:VDGWidgetPresets.create(host.dataset.preset);
    const renderer=VDGWidgetRenderer.mount(host,doc,{animate:!reduced.matches});
    const root=host.firstElementChild;
    function fit(){const scale=Math.min((host.clientWidth-28)/doc.width,(host.clientHeight-28)/doc.height);root.style.position='absolute';root.style.transformOrigin='0 0';root.style.transform='scale('+scale+')';root.style.left=((host.clientWidth-doc.width*scale)/2)+'px';root.style.top=((host.clientHeight-doc.height*scale)/2)+'px';}
    new ResizeObserver(fit).observe(host);fit();renderers.push(renderer);
  }
  let current=24800,lastName='Зритель',lastAmount=500,lastMessage='Спасибо за стрим';
  const money=amount=>amount.toLocaleString('ru-RU')+' ₽';
  function update(){const percent=current/400;value.textContent=percent.toLocaleString('ru-RU',{maximumFractionDigits:1})+'%';input.setAttribute('aria-valuetext',value.textContent);document.getElementById('feedTotal').textContent=money(current);for(const r of renderers)r.update({title:'Новый микрофон',current,goal:40000,currency:'RUB',lastName,lastAmount,lastMessage});}
  input.addEventListener('input',()=>{current=Number(input.value)*400;update();});update();
  const names=['Мира','Алекс','Nova','Саша','Тихий зритель'],messages=['Спасибо за стрим','На новый микрофон','Хорошего вечера','На шаг ближе к цели'];
  document.querySelectorAll('[data-donate]').forEach(button=>button.onclick=()=>{
    lastAmount=(1+Math.floor(Math.random()*30))*100;lastName=names[Math.floor(Math.random()*names.length)];lastMessage=messages[Math.floor(Math.random()*messages.length)];current+=lastAmount;
    input.max=String(Math.max(120,Math.ceil(current/4000)*10));input.value=String(current/400);update();
    document.getElementById('demoDonation').textContent=lastName+' · '+button.textContent+' · +'+money(lastAmount);
    const row=document.createElement('div');row.className='feed-row';
    const badge=document.createElement('span');badge.className='source-badge source-'+button.dataset.donate;badge.textContent=({da:'DA',dp:'DP',donatty:'DT',tribute:'TG',ds:'DS',dx:'DX',se:'SE',sl:'SL'})[button.dataset.donate];
    const content=document.createElement('div'),name=document.createElement('strong'),message=document.createElement('span'),amount=document.createElement('b');name.textContent=lastName;message.textContent=lastMessage;amount.textContent=money(lastAmount);content.append(name,message);row.append(badge,content,amount);
    const feed=document.getElementById('heroFeed');feed.prepend(row);while(feed.children.length>3)feed.lastElementChild.remove();
    if(!reduced.matches){row.animate([{opacity:0,transform:'translateY(-10px)'},{opacity:1,transform:'translateY(0)'}],{duration:350,easing:'ease-out'});button.animate([{transform:'scale(1)'},{transform:'scale(.96)'},{transform:'scale(1)'}],{duration:220});}
  });
  const initialFeed=document.getElementById('heroFeed').innerHTML;
  document.getElementById('resetDemo').onclick=()=>{current=24800;input.max='120';input.value='62';lastName='Зритель';lastAmount=500;lastMessage='Спасибо за стрим';update();document.getElementById('heroFeed').innerHTML=initialFeed;document.getElementById('demoDonation').textContent='Выберите сервис — все оформления ниже отреагируют на один донат';};
  if(!reduced.matches){
    const reveal=new IntersectionObserver(entries=>{for(const entry of entries){if(!entry.isIntersecting)continue;entry.target.animate([{opacity:0,transform:'translateY(18px)'},{opacity:1,transform:'translateY(0)'}],{duration:650,easing:'cubic-bezier(.2,.7,.2,1)'});reveal.unobserve(entry.target);}},{threshold:.12});
    document.querySelectorAll('.section-intro,.preset-gallery figure,.editor-description,.product-shot,.ai-help>div,.theme-foot,.automation>div,.local-inner,.start-section>div,.start-steps').forEach(el=>reveal.observe(el));
    document.querySelector('.hero-copy').animate([{opacity:0,transform:'translateY(12px)'},{opacity:1,transform:'translateY(0)'}],{duration:700,easing:'ease-out'});
  }
  window.publicationReady=true;
})();
