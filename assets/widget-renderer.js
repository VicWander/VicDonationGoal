(function (global) {
  'use strict';
  const NS = 'http://www.w3.org/2000/svg';
  let serial = 0;
  const finite = (v, fallback = 0) => Number.isFinite(Number(v)) ? Number(v) : fallback;
  const clamp = (v, min, max) => Math.max(min, Math.min(max, v));
  function publicState(input) {
    const s = input || {}, last = s.lastDonation || {};
    const current = finite(s.current), goal = finite(s.goal);
    return { title: String(s.title || ''), current, goal, remaining: Math.max(0, goal - current),
      percent: goal > 0 ? Math.max(0, current / goal * 100) : 0, currency: String(s.currency || ''),
      lastName: String(s.lastName ?? last.username ?? last.name ?? ''),
      lastAmount: s.lastAmount ?? last.amount ?? '', lastMessage: String(s.lastMessage ?? last.message ?? '') };
  }
  function number(value, settings) {
    const f = settings || {}, d = clamp(finite(f.decimals), 0, 4), factor = 10 ** d;
    let n = finite(value);
    n = (f.rounding === 'floor' ? Math.floor(n * factor) : Math.round((n + Number.EPSILON) * factor)) / factor;
    return n.toLocaleString('ru-RU', { minimumFractionDigits: d, maximumFractionDigits: d,
      ...(f.compact ? { notation: 'compact' } : {}) });
  }
  function format(text, state, settings) {
    const s = publicState(state), f = settings || {};
    let currency = s.currency;
    if (f.currency === 'none') currency = '';
    if (f.currency === 'symbol' && currency) {
      try { currency = new Intl.NumberFormat('ru-RU', {style:'currency',currency}).formatToParts(0).find(p => p.type === 'currency').value; } catch (_) {}
    }
    const values = { ...s, currency };
    for (const key of ['current','goal','remaining','percent','lastAmount']) values[key] = s[key] === '' ? '' : number(s[key], f);
    return String(text || '').replace(/\{\{\s*(title|current|goal|remaining|percent|currency|lastName|lastAmount|lastMessage)\s*\}\}/g, (_, key) => values[key]);
  }
  // Installed inside the isolated iframe; no access to renderer or administrator state.
  function installPreviewClock(){
    const nativeNow=performance.now.bind(performance),nativeDate=Date.now.bind(Date);
    const raf=requestAnimationFrame.bind(window),caf=cancelAnimationFrame.bind(window),timeout=setTimeout.bind(window),clear=clearTimeout.bind(window);
    const epoch=nativeDate()-nativeNow();
    const tasks=new Map(),animations=new Set(),svgClocks=new Set();let serial=0,paused=false,pauseTime=0,offset=0;
    const now=()=> (paused?pauseTime:nativeNow())-offset;
    Object.defineProperty(performance,'now',{value:now,configurable:true});
    Date.now=()=>Math.floor(epoch+now());
    function schedule(id,item){
      if(paused)return;
      if(item.frame)item.handle=raf(()=>{if(!tasks.delete(id))return;item.callback.call(window,now());});
      else item.handle=timeout(()=>{if(!tasks.has(id))return;if(item.interval){item.due=now()+item.delay;schedule(id,item);}else tasks.delete(id);item.callback.apply(window,item.args);},Math.max(0,item.due-now()));
    }
    function cancel(id){const item=tasks.get(id);if(item){item.frame?caf(item.handle):clear(item.handle);tasks.delete(id);}}
    window.requestAnimationFrame=callback=>{const id=++serial,item={frame:true,callback};tasks.set(id,item);schedule(id,item);return id;};
    window.cancelAnimationFrame=cancel;
    function timer(callback,delay,interval,args){if(typeof callback!=='function')throw new TypeError('Используй функцию в таймере');delay=Math.max(interval?1:0,Math.min(2147483647,Number(delay)||0));const id=++serial,item={callback,delay,interval,args,due:now()+delay};tasks.set(id,item);schedule(id,item);return id;}
    window.setTimeout=(callback,delay,...args)=>timer(callback,delay,false,args);
    window.setInterval=(callback,delay,...args)=>timer(callback,delay,true,args);
    window.clearTimeout=window.clearInterval=cancel;
    function freezeAnimations(){for(const animation of document.getAnimations()){if(animation.playState==='running'){animation.pause();animations.add(animation);}}for(const svg of document.querySelectorAll('svg'))if(svg.pauseAnimations&&!svg.animationsPaused()){svg.pauseAnimations();svgClocks.add(svg);}}
    addEventListener('message',event=>{
      if(event.source!==parent||event.data?.type!=='vdg:pause'||paused===Boolean(event.data.paused))return;
      if(event.data.paused){pauseTime=nativeNow();paused=true;for(const item of tasks.values())item.frame?caf(item.handle):clear(item.handle);freezeAnimations();}
      else{offset+=nativeNow()-pauseTime;paused=false;for(const animation of animations)if(animation.playState==='paused')animation.play();animations.clear();for(const svg of svgClocks)svg.unpauseAnimations();svgClocks.clear();for(const [id,item]of tasks)schedule(id,item);}
      document.documentElement.dataset.vdgPaused=String(paused);
    });
    new MutationObserver(()=>{if(paused)freezeAnimations();}).observe(document.documentElement,{subtree:true,childList:true,attributes:true});
  }
  function installMotion(){
    const channels=new Map();let frame=0;
    const reduce=()=>window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
    function draw(key,item){try{item.update(item.current);}catch(error){channels.delete(key);queueMicrotask(()=>{throw error;});}}
    function tick(now){frame=0;let pending=false;for(const [key,item] of channels){if(item.current===item.target)continue;const t=reduce()||item.duration===0?1:Math.min(1,Math.max(0,(now-item.start)/item.duration));item.current=t===1?item.target:item.from+(item.target-item.from)*(1-Math.pow(1-t,3));draw(key,item);if(t<1)pending=true;}if(pending)frame=requestAnimationFrame(tick);}
    function value(key,target,options={}){
      key=String(key);target=Number(target);if(!Number.isFinite(target))throw Error('VDGMotion: цель должна быть конечным числом');
      let item=channels.get(key);
      if(!item){if(channels.size>=100)throw Error('VDGMotion: максимум 100 каналов движения');const initial=Number(options.initial??target);if(!Number.isFinite(initial))throw Error('VDGMotion: неверное начальное значение');item={current:initial,target:initial,update:typeof options.update==='function'?options.update:()=>{}};channels.set(key,item);draw(key,item);}
      if(typeof options.update==='function')item.update=options.update;
      if(item.target===target)return item.current;
      item.from=item.current;item.target=target;item.start=performance.now();const duration=Number(options.duration??1000);item.duration=Number.isFinite(duration)?Math.min(60000,Math.max(0,duration)):1000;
      if(reduce()||item.duration===0){item.current=target;draw(key,item);}else if(!frame)frame=requestAnimationFrame(tick);return item.current;
    }
    window.VDGMotion=Object.freeze({value,stop:key=>channels.delete(String(key)),stopAll:()=>{channels.clear();if(frame)cancelAnimationFrame(frame);frame=0;}});
  }
  function mount(container, initialDocument, options) {
    const opts = { editor:false, animate:true, assets:[], ...options };
    const root = document.createElement('div');
    root.className = 'vdg-widget-root'; root.dataset.editor = String(opts.editor);
    container.append(root);
    const reduced = global.matchMedia && global.matchMedia('(prefers-reduced-motion: reduce)').matches;
    let doc, state = publicState({}), records = [], frame = 0, disposed = false, hasState = false, paused = false, pausedAt = 0;
    const fonts = new Map();
    const customError=event=>{if(disposed||event.data?.type!=='vdg:custom-error'||typeof event.data.message!=='string')return;if(records.some(r=>r.iframe?.contentWindow===event.source))opts.onError?.(event.data.message.slice(0,1500));};
    global.addEventListener('message',customError);
    const color = value => String(value || 'transparent').startsWith('@') ? (doc.palette || {})[String(value).slice(1)] || 'transparent' : value || 'transparent';
    const asset = id => {
      if (!id) return '';
      const found = opts.assets.find(item => item.id === id);
      // Never allow a document or asset list to load remote or arbitrary local URLs.
      const local = '/widget-assets/' + encodeURIComponent(id);
      return found && /^\/widget-assets\/[a-zA-Z0-9_.%-]+$/.test(found.url || '') ? found.url : local;
    };
    const svg = (tag, attrs, parent) => {
      const node = document.createElementNS(NS, tag);
      for (const [key,value] of Object.entries(attrs || {})) node.setAttribute(key, value);
      if (parent) parent.append(node);
      return node;
    };
    function buildProgress(record) {
      const e = record.e, p = e.progress || {}, w = e.width, h = e.height;
      const graphic = svg('svg', {viewBox:`0 0 ${w} ${h}`,preserveAspectRatio:'none'}, record.content);
      const defs = svg('defs', {}, graphic), gradientId = 'vdg-gradient-' + (++serial);
      const angle = finite(e.style.gradientAngle) * Math.PI / 180;
      const gradient = svg('linearGradient', {id:gradientId,x1: .5-Math.cos(angle)/2,y1:.5-Math.sin(angle)/2,x2:.5+Math.cos(angle)/2,y2:.5+Math.sin(angle)/2}, defs);
      const stop1 = svg('stop', {offset:0}, gradient), stop2 = svg('stop', {offset:1}, gradient);
      record.paint = fill => {
        stop1.setAttribute('stop-color', fill); stop2.setAttribute('stop-color', color(e.style.fill2));
        return e.style.gradient ? `url(#${gradientId})` : fill;
      };
      if (p.shape === 'ring' || p.shape === 'arc') {
        const thick = Math.min(w,h, Math.max(1,finite(p.thickness,12))), radius = Math.max(.1,(Math.min(w,h)-thick)/2);
        const sweep = p.shape === 'ring' ? 359.999 : clamp(finite(p.sweep,270),1,359.999), start = finite(p.startAngle,-90);
        const point = a => [w/2+radius*Math.cos(a*Math.PI/180),h/2+radius*Math.sin(a*Math.PI/180)];
        const a = point(start), b = point(start+sweep);
        const path = `M ${a[0]} ${a[1]} A ${radius} ${radius} 0 ${sweep>180?1:0} 1 ${b[0]} ${b[1]}`;
        svg('path',{d:path,fill:'none',stroke:color(p.track),'stroke-width':thick,'stroke-linecap':'round'},graphic);
        record.fill = svg('path',{d:path,fill:'none','stroke-width':thick,'stroke-linecap':'round',pathLength:100},graphic);
        record.draw = value => { record.fill.setAttribute('stroke-dasharray',`${value*100} 100`);record.fill.setAttribute('stroke-dashoffset', ['left','up'].includes(p.direction)?-(100-value*100):p.direction==='center'?-(100-value*100)/2:0); record.fill.style.visibility=value>0?'visible':'hidden'; };
      } else if (p.shape === 'segments') {
        const count = clamp(Math.round(finite(p.segments,10)),1,200), vertical = ['up','down'].includes(p.direction);
        const length = vertical ? h : w, gap = Math.min(Math.max(0,finite(p.gap,4)),length/count), size = Math.max(0,(length-gap*(count-1))/count);
        record.segments = [];
        for(let i=0;i<count;i++) {
          const pos=i*(size+gap), attrs={x:vertical?0:pos,y:vertical?pos:0,width:vertical?w:size,height:vertical?size:h,rx:Math.min(finite(e.style.radius),size/2)};
          svg('rect',{...attrs,fill:color(p.track)},graphic);
          record.segments.push(svg('rect',attrs,graphic));
        }
        record.draw = value => record.segments.forEach((node,i) => {
          const reverse = ['left','up'].includes(p.direction), index=p.direction==='center'?Math.abs(i-(count-1)/2)*2:reverse?count-1-i:i;
          node.style.opacity=String(clamp(value*count-index,0,1));
        });
      } else {
        let target=graphic;
        if(p.shape === 'mask' && p.maskAsset) {
          const maskId='vdg-mask-'+(++serial), mask=svg('mask',{id:maskId,maskUnits:'userSpaceOnUse',x:0,y:0,width:w,height:h},defs);
          mask.style.maskType='alpha'; svg('image',{href:asset(p.maskAsset),width:w,height:h,preserveAspectRatio:'none'},mask);
          target=svg('g',{mask:`url(#${maskId})`},graphic);
        }
        svg('rect',{width:w,height:h,rx:e.style.radius,fill:color(p.track)},target);
        record.fill = svg('rect',{width:w,height:h,rx:e.style.radius},target);
        if(p.imageAsset) {
          const clipId='vdg-image-clip-'+(++serial), clip=svg('clipPath',{id:clipId},defs);
          record.imageClip=svg('rect',{width:w,height:h},clip);
          svg('image',{href:asset(p.imageAsset),width:w,height:h,preserveAspectRatio:'xMidYMid slice','clip-path':`url(#${clipId})`},target);
        }
        record.draw=value=>{
          let x=0,y=0,fw=w,fh=h;
          if(['up','down'].includes(p.direction)){fh=h*value;if(p.direction==='up')y=h-fh;}
          else{fw=w*value;if(p.direction==='left')x=w-fw;if(p.direction==='center')x=(w-fw)/2;}
          for(const node of [record.fill,record.imageClip].filter(Boolean)) for(const [k,v] of Object.entries({x,y,width:fw,height:fh}))node.setAttribute(k,v);
        };
      }
    }
    function customFrame(record) {
      const custom=record.e.custom||{}, iframe=document.createElement('iframe');
      iframe.title=record.e.name||'HTML виджет'; iframe.setAttribute('sandbox','allow-scripts');
      iframe.referrerPolicy='no-referrer';
      // User code stays in an opaque origin. The bridge receives only whitelisted goal data.
      const bridge=`(${installMotion.toString()})();(()=>{const report=message=>parent.postMessage({type:'vdg:custom-error',message:String(message).slice(0,1500)},'*');addEventListener('error',e=>{report(e.message||'Ошибка сценария');e.preventDefault();});addEventListener('unhandledrejection',e=>{report(e.reason?.message||e.reason||'Ошибка асинхронного сценария');e.preventDefault();});addEventListener('securitypolicyviolation',e=>report('Недоступный ресурс: '+e.violatedDirective));addEventListener('message',e=>{if(e.source!==parent||!e.data||e.data.type!=='vdg:update')return;const d=e.data.payload;document.querySelectorAll('[data-vdg-text]').forEach(n=>{const key=n.dataset.vdgText,value=d.state[key];const numeric=['current','goal','remaining','percent','lastAmount'].includes(key)&&value!==''&&Number.isFinite(Number(value));const requested=Number(n.getAttribute('data-vdg-decimals')??2),places=Number.isFinite(requested)?Math.max(0,Math.min(4,Math.trunc(requested))):2;const text=numeric?Number(value).toLocaleString('ru-RU',{maximumFractionDigits:places}):String(value??'');if(n.textContent!==text)n.textContent=text;});document.querySelectorAll('[data-vdg-field]').forEach(n=>n.textContent=d.values[n.dataset.vdgField]??'');document.querySelectorAll('[data-vdg-progress]').forEach(n=>n.style.width=Math.max(0,Math.min(100,d.state.percent))+'%');dispatchEvent(new CustomEvent('vdg:update',{detail:d}));});})();`;
      const escapeEnd=value=>String(value||'').replace(/<\/script/gi,'<\\/script');
      iframe.srcdoc='<!doctype html><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="default-src \'none\'; script-src \'unsafe-inline\'; style-src \'unsafe-inline\'; img-src data:; font-src data:; connect-src \'none\'; form-action \'none\'; base-uri \'none\'"><style>html,body{margin:0;background:transparent;overflow:hidden}'+String(custom.css||'').replace(/<\/style/gi,'<\\/style')+'</style>'+String(custom.html||'')+'<script>'+bridge+'<\/script><script>'+escapeEnd(custom.js)+'<\/script>';
      if(opts.editor)iframe.srcdoc=iframe.srcdoc.replace('<script>'+bridge,'<script>('+installPreviewClock.toString()+')();'+bridge);
      record.iframe=iframe; iframe.addEventListener('load',()=>{record.lastCustomPayload=null;if(opts.editor)iframe.contentWindow.postMessage({type:'vdg:pause',paused},'*');sendCustom(record);});record.content.append(iframe);
    }
    function sendCustom(record) {
      if(!record.iframe || disposed)return;
      const custom=record.e.custom||{}, values={};
      for(const field of custom.fields||[]) values[field.key]=(custom.values||{})[field.key]??field.default;
      const safeDocument={schemaVersion:doc.schemaVersion,id:doc.id,name:doc.name,width:doc.width,height:doc.height,background:doc.background,palette:doc.palette};
      const payload={state:publicState(state),values,document:safeDocument},signature=JSON.stringify(payload);if(record.lastCustomPayload===signature)return;record.lastCustomPayload=signature;record.iframe.contentWindow.postMessage({type:'vdg:update',payload},'*');
    }
    function build() {
      if(frame)cancelAnimationFrame(frame);frame=0;
      for(const r of records)if(r.effect)r.effect.cancel();
      root.replaceChildren(); records=[];
      root.style.width=doc.width+'px';root.style.height=doc.height+'px';root.style.background=color(doc.background);
      const nodes=global.VDGWidgetModel.layout(doc), byId=new Map(nodes.map(e=>[e.id,e]));
      for(const e of nodes) {
        const node=document.createElement('div'),content=document.createElement('div'),s=e.style;
        node.className='vdg-widget-element';node.dataset.widgetElement=e.id;node.dataset.widgetType=e.type;
        Object.assign(node.style,{left:e.absoluteX+'px',top:e.absoluteY+'px',width:e.width+'px',height:e.height+'px',transform:`rotate(${e.rotation}deg)`,borderRadius:s.radius+'px',borderColor:color(s.stroke),borderWidth:s.strokeWidth+'px',boxShadow:`${s.shadowX}px ${s.shadowY}px ${s.shadowBlur}px ${color(s.shadowColor)}`});
        // Layout is flat, so explicitly compose the ancestor transforms and visibility.
        let parent=byId.get(e.parentId), ancestors=[];
        while(parent){ancestors.push(parent);parent=byId.get(parent.parentId);}
        if(ancestors.some(p=>p.rotation)) {
          const rotations=ancestors.slice().reverse().map(p=>{const x=p.absoluteX+p.width/2-e.absoluteX-e.width/2,y=p.absoluteY+p.height/2-e.absoluteY-e.height/2;return `translate(${x}px,${y}px) rotate(${p.rotation}deg) translate(${-x}px,${-y}px)`;});
          node.style.transform=rotations.join(' ')+` rotate(${e.rotation}deg)`;
        }
        content.className='vdg-widget-content';content.style.borderRadius=s.radius+'px';node.append(content);root.append(node);
        const r={e,node,content,ancestors,current:0,target:0};records.push(r);
        if(e.type==='text') {
          node.style.boxShadow='none';
          content.classList.add('vdg-widget-text');content.dataset.fit=e.textFit;const span=document.createElement('span');content.append(span);r.textNode=span;
          Object.assign(content.style,{fontFamily:s.fontFamily,fontSize:s.fontSize+'px',fontWeight:s.fontWeight,lineHeight:s.lineHeight,letterSpacing:s.letterSpacing+'px',textAlign:s.textAlign,textTransform:s.textTransform,textShadow:`${s.shadowX}px ${s.shadowY}px ${s.shadowBlur}px ${color(s.shadowColor)}`,WebkitTextStroke:`${s.textStrokeWidth}px ${color(s.textStrokeColor)}`,'--vdg-text-width':e.width+'px'});
          if(s.fontAsset){const family='vdg-'+s.fontAsset;content.style.fontFamily=`"${family}", ${s.fontFamily}`;
            if(!fonts.has(s.fontAsset)&&global.FontFace){const font=new FontFace(family,`url("${asset(s.fontAsset)}")`);fonts.set(s.fontAsset,font);font.load().then(loaded=>{if(!disposed){document.fonts.add(loaded);update(state);}}).catch(error=>opts.onError?.(error));}}
        } else if(e.type==='progress')buildProgress(r);
        else if(e.type==='image'){const img=document.createElement('img');img.alt='';if(e.image.asset)img.src=asset(e.image.asset);img.style.objectFit=e.image.fit==='stretch'?'fill':e.image.fit;img.style.objectPosition=`${e.image.positionX}% ${e.image.positionY}%`;content.append(img);}
        else if(e.type==='custom')customFrame(r);
      }
    }
    function condition(e) {
      const c=e.condition||{}, matches=c.enabled&&(c.op==='lte'?state[c.metric]<=c.value:state[c.metric]>=c.value);
      return {visible:e.visible!==false&&(!c.enabled||c.action!=='show'||matches)&&(!matches||c.action!=='hide'),fill:matches&&c.action==='color'?color(c.color):color(e.style.fill)};
    }
    function tick(now) {
      frame=0;if(paused)return;let pending=false;
      for(const r of records){if(!r.draw)continue;const t=r.duration?clamp((now-r.start)/r.duration,0,1):1;
        let eased=t;const easing=r.e.animation.easing;
        if(easing==='ease-in')eased=t*t;else if(easing==='ease-in-out')eased=t<.5?2*t*t:1-(-2*t+2)**2/2;else if(easing!=='linear')eased=1-(1-t)**3;
        r.current=r.from+(r.target-r.from)*eased;r.draw(r.current);if(t<1)pending=true;}
      if(pending&&!disposed)frame=requestAnimationFrame(tick);
    }
    function animateEvent(r,event,previous) {
      const a=r.e.animation;if(!hasState||!event||!opts.animate||reduced||a.effect==='none'||a.event==='none')return;
      const fired=a.event==='donation'&&(event==='donation'||event.type==='donation')||a.event==='goal'&&previous.percent<100&&state.percent>=100||a.event==='milestone'&&previous.percent<a.threshold&&state.percent>=a.threshold;
      if(!fired||!r.content.animate)return;
      if(r.effect)r.effect.cancel();const intensity=finite(a.intensity,1);
      const effects={fade:[{opacity:.2},{opacity:1}],pulse:[{transform:'scale(1)'},{transform:`scale(${1+.08*intensity})`},{transform:'scale(1)'}],slide:[{transform:`translateY(${20*intensity}px)`,opacity:0},{transform:'translateY(0)',opacity:1}],glow:[{filter:'brightness(1)'},{filter:`brightness(${1+intensity})`},{filter:'brightness(1)'}]};
      r.effect=r.content.animate(effects[a.effect]||effects.fade,{duration:a.duration,easing:a.easing||'ease-out'});if(paused)r.effect.pause();
    }
    function update(input, meta) {
      if(disposed)return;
      const previous=state,initial=!hasState;state=publicState(input);const now=paused?pausedAt:performance.now();
      for(const r of records){const e=r.e,s=e.style,c=condition(e);r.node.hidden=!c.visible||r.ancestors.some(p=>!condition(p).visible);
        r.node.style.opacity=String(e.opacity*r.ancestors.reduce((value,p)=>value*p.opacity,1));
        if(r.textNode){r.content.style.color=c.fill;r.textNode.textContent=format(e.text,state,e.format);
          if(e.textFit==='shrink'){let size=s.fontSize;r.content.style.fontSize=size+'px';const min=Math.min(size,e.minFontSize);while(size>min&&(r.content.scrollWidth>e.width||r.content.scrollHeight>e.height)){size=Math.max(min,size-1);r.content.style.fontSize=size+'px';}}}
        else if(e.type==='shape'||e.type==='group')r.content.style.background=s.gradient?`linear-gradient(${s.gradientAngle}deg,${c.fill},${color(s.fill2)})`:c.fill;
        if(r.draw){const paint=r.paint(c.fill);if(r.fill)r.fill.setAttribute(['ring','arc'].includes(e.progress.shape)?'stroke':'fill',paint);if(r.segments)r.segments.forEach(n=>n.setAttribute('fill',paint));
          const target=clamp(state.percent/100,0,1);
          if(r.target!==target||r.start===undefined){r.from=r.current;r.target=target;r.start=now;r.duration=opts.animate&&!reduced&&hasState?finite(e.animation.duration,450):0;}
        }
        sendCustom(r);animateEvent(r,meta&&meta.event,previous);
      }
      hasState=true;if(paused){if(initial)for(const r of records)if(r.draw){r.current=r.target;r.draw(r.current);}return;}if(!frame)tick(now);
    }
    function setPaused(value){
      if(disposed||paused===Boolean(value))return;
      if(value){paused=true;pausedAt=performance.now();if(frame)cancelAnimationFrame(frame);frame=0;}
      else{const elapsed=performance.now()-pausedAt;for(const r of records)if(r.start!==undefined)r.start+=elapsed;paused=false;}
      root.dataset.paused=String(paused);
      if(opts.editor)for(const record of records)record.iframe?.contentWindow.postMessage({type:'vdg:pause',paused},'*');
      for(const animation of root.getAnimations({subtree:true}))paused?animation.pause():animation.play();
      if(!paused&&!frame)tick(performance.now());
    }
    function setDocument(next){if(disposed)return;const normalized=global.VDGWidgetModel.normalize(next),validation=global.VDGWidgetModel.validate(normalized);if(!validation.ok)throw new Error(validation.errors.join('; '));doc=normalized;build();const had=hasState;hasState=false;update(state);hasState=had;}
    try{setDocument(initialDocument);}catch(error){global.removeEventListener('message',customError);root.remove();throw error;}
    return {update,setDocument,setPaused,destroy(){disposed=true;global.removeEventListener('message',customError);if(frame)cancelAnimationFrame(frame);for(const r of records)if(r.effect)r.effect.cancel();for(const font of fonts.values())document.fonts.delete(font);root.remove();}};
  }
  global.VDGWidgetRenderer={mount,format,publicState};
})(window);
