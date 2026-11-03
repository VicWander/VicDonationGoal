(function (global) {
  'use strict';
  let serial = 0;
  const clone = value => JSON.parse(JSON.stringify(value));
  const uid = () => 'w-' + Date.now().toString(36) + '-' + (++serial).toString(36) + '-' + Math.random().toString(36).slice(2, 9);
  const palette = { primary: '#3bc7da', secondary: '#23489e', text: '#ffffff', surface: '#172136', track: '#535353' };
  const types = ['text', 'progress', 'shape', 'image', 'group', 'custom'];
  function createElement(type) {
    return { id: uid(), type: types.includes(type) ? type : 'text', name: type || 'text', parentId: null, x: 0, y: 0, width: 240, height: 60, rotation: 0, opacity: 1, visible: true, locked: false,
      style: { fill: type === 'group' ? 'transparent' : '@primary', fill2: '@secondary', gradient: false, gradientAngle: 0, stroke: 'transparent', strokeWidth: 0, radius: 0, shadowColor: 'transparent', shadowBlur: 0, shadowX: 0, shadowY: 0, fontFamily: 'Arial', fontAsset: '', fontSize: 30, fontWeight: 700, lineHeight: 1.2, letterSpacing: 0, textAlign: 'left', textTransform: 'none', textStrokeColor: 'transparent', textStrokeWidth: 0 },
      text: type === 'text' ? '{{title}}' : '', format: { decimals: 0, currency: 'code', compact: false, rounding: 'round' }, textFit: 'wrap', minFontSize: 12,
      progress: { shape: 'bar', direction: 'right', track: '@track', gap: 4, segments: 10, startAngle: -90, sweep: 360, thickness: 12, maskAsset: '', imageAsset: '', overflow: 'clamp' },
      image: { asset: '', fit: 'contain', positionX: 50, positionY: 50 }, group: { layout: 'free', gap: 8, padding: 0, align: 'start' }, anchor: { horizontal: 'left', vertical: 'top' },
      condition: { enabled: false, metric: 'percent', op: 'gte', value: 100, action: 'show', color: '@primary' }, animation: { duration: 450, easing: 'ease-out', event: 'none', effect: 'none', threshold: 50, intensity: 1 }, custom: { html: '', css: '', js: '', fields: [], values: {} } };
  }
  function createDocument(name) { return { schemaVersion: 1, id: uid(), name: name || 'Новый виджет', width: 760, height: 180, background: 'transparent', palette: clone(palette), elements: [] }; }
  function normalize(doc) {
    const source = doc && typeof doc === 'object' ? doc : {}, out = createDocument();
    for (const key of ['schemaVersion', 'id', 'name', 'width', 'height', 'background']) if (source[key] !== undefined) out[key] = clone(source[key]);
    out.palette = Object.assign(out.palette, source.palette || {});
    out.elements = (Array.isArray(source.elements) ? source.elements : []).map(raw => {
      const e = createElement(raw.type); Object.keys(e).forEach(key => { if (raw[key] !== undefined) e[key] = typeof e[key] === 'object' && e[key] !== null && !Array.isArray(e[key]) ? Object.assign(e[key], clone(raw[key])) : clone(raw[key]); }); return e;
    }); return out;
  }
  function validate(doc) {
    const errors = [], fail = message => errors.push(message), finite = (v, lo, hi) => typeof v === 'number' && Number.isFinite(v) && v >= lo && v <= hi;
    if (!doc || typeof doc !== 'object') return { ok: false, errors: ['Document must be an object'] };
    if (doc.schemaVersion !== 1) fail('Unsupported schema version');
    if (typeof doc.id !== 'string' || !doc.id || doc.id.length > 80) fail('Invalid document ID');
    if (typeof doc.name !== 'string' || doc.name.length > 160) fail('Invalid document name');
    for (const key of ['width', 'height']) if (!Number.isInteger(doc[key]) || !finite(doc[key], 16, 8192)) fail('Invalid canvas ' + key);
    const color = value => typeof value === 'string' && value.length <= 120 && (/^@(primary|secondary|text|surface|track)$/.test(value) || /^(?:#[0-9a-f]{3,4}|#[0-9a-f]{6}|#[0-9a-f]{8}|[a-z]{1,30}|(?:rgb|rgba|hsl|hsla)\([0-9.,%+\- /]+\))$/i.test(value));
    if (!color(doc.background)) fail('Invalid background');
    for (const key of Object.keys(palette)) if (!doc.palette || !color(doc.palette[key])) fail('Invalid palette ' + key);
    if (!Array.isArray(doc.elements) || doc.elements.length > 100) return { ok: false, errors: errors.concat('Invalid elements array') };
    const map = new Map();
    const enums = { 'format.currency': ['code','symbol','none'], 'format.rounding': ['round','floor'], 'progress.shape': ['bar','ring','arc','segments','mask'], 'progress.direction': ['right','left','up','down','center'], 'progress.overflow': ['clamp'], 'image.fit': ['contain','cover','stretch'], 'group.layout': ['free','horizontal','vertical'], 'group.align': ['start','center','end'], 'anchor.horizontal': ['left','center','right'], 'anchor.vertical': ['top','center','bottom'], 'condition.metric': ['percent','current','remaining'], 'condition.op': ['gte','lte'], 'condition.action': ['show','hide','color'], 'animation.event': ['none','donation','goal','milestone'], 'animation.effect': ['none','fade','pulse','slide','glow'] };
    for (const e of doc.elements) {
      if (!e || typeof e !== 'object') { fail('Invalid element'); continue; }
      if (typeof e.id !== 'string' || !e.id || e.id.length > 80 || map.has(e.id)) fail('Duplicate or invalid element ID'); map.set(e.id, e);
      if (!types.includes(e.type)) fail('Invalid element type');
      const defaults = createElement(e.type);
      for (const key of Object.keys(defaults)) if (e[key] === undefined) fail('Missing element field ' + key);
      for (const key of ['style','format','progress','image','group','anchor','condition','animation','custom']) {
        if (!e[key] || typeof e[key] !== 'object' || Array.isArray(e[key])) { fail('Invalid ' + key); continue; }
        for (const field of Object.keys(defaults[key])) if (e[key][field] === undefined) fail('Missing ' + key + '.' + field);
      }
      for (const key of ['x','y']) if (!finite(e[key], -16384, 16384)) fail('Invalid ' + key);
      for (const key of ['width','height']) if (!finite(e[key], 1, 8192)) fail('Invalid element ' + key);
      if (!finite(e.rotation, -360, 360) || !finite(e.opacity, 0, 1)) fail('Invalid rotation or opacity');
      if (typeof e.visible !== 'boolean' || typeof e.locked !== 'boolean') fail('Invalid element visibility');
      if (typeof e.name !== 'string' || e.name.length > 160 || typeof e.text !== 'string' || e.text.length > 4000) fail('Invalid element text');
      if (!['wrap','shrink','ellipsis','scroll'].includes(e.textFit)) fail('Invalid text fit');
      for (const [key, allowed] of Object.entries(enums)) { const [a,b] = key.split('.'); if (!e[a] || !allowed.includes(e[a][b])) fail('Invalid ' + key); }
      if (e.style) for (const key of ['fill','fill2','stroke','shadowColor','textStrokeColor']) if (!color(e.style[key])) fail('Invalid style color');
      const bounds = {
        'style.gradientAngle': [-360,360], 'style.strokeWidth': [0,1024], 'style.radius': [0,9999], 'style.shadowBlur': [0,1024], 'style.shadowX': [-8192,8192], 'style.shadowY': [-8192,8192],
        'style.fontSize': [1,2048], 'style.fontWeight': [100,1000], 'style.lineHeight': [.1,10], 'style.letterSpacing': [-100,100], 'style.textStrokeWidth': [0,100],
        'format.decimals': [0,4], 'progress.gap': [0,8192], 'progress.segments': [1,1000], 'progress.startAngle': [-360,360], 'progress.sweep': [0,360], 'progress.thickness': [0,8192],
        'image.positionX': [0,100], 'image.positionY': [0,100], 'group.gap': [0,8192], 'group.padding': [0,8192], 'condition.value': [-1e15,1e15], 'animation.duration': [0,60000], 'animation.threshold': [0,1000000], 'animation.intensity': [0,100]
      };
      for (const [key,bound] of Object.entries(bounds)) { const [a,b]=key.split('.'); if(!e[a]||!finite(e[a][b],bound[0],bound[1]))fail('Invalid '+key); }
      if(!finite(e.minFontSize,1,2048))fail('Invalid minimum font size');
      if(e.format&&(!Number.isInteger(e.format.decimals)||typeof e.format.compact!=='boolean'))fail('Invalid number format');
      if(e.progress&&!Number.isInteger(e.progress.segments))fail('Invalid segment count');
      if(e.style&&(!['left','center','right'].includes(e.style.textAlign)||!['none','uppercase','lowercase','capitalize'].includes(e.style.textTransform)||typeof e.style.gradient!=='boolean'))fail('Invalid text style');
      if(e.custom&&(!Array.isArray(e.custom.fields)||!e.custom.values||typeof e.custom.values!=='object'||Array.isArray(e.custom.values)))fail('Invalid custom fields');
    }
    for (const e of doc.elements) {
      if (!e) continue; const visited = new Set([e.id]); let cur = e, depth = 0;
      while (cur.parentId !== null && cur.parentId !== undefined) {
        const p = map.get(cur.parentId); if (!p || p.type !== 'group') { fail('Invalid parent'); break; }
        if (visited.has(p.id)) { fail('Parent cycle'); break; } visited.add(p.id); cur = p;
        if (++depth > 8) { fail('Hierarchy too deep'); break; }
      }
    }
    return { ok: errors.length === 0, errors };
  }
  function layout(doc) {
    const map = new Map(doc.elements.map(e => [e.id, e])), calculated = new Map(), visiting = new Set();
    function compute(e) {
      if (calculated.has(e.id)) return calculated.get(e.id);
      if (visiting.has(e.id)) return Object.assign({}, e, { absoluteX: e.x, absoluteY: e.y });
      visiting.add(e.id); let x = e.x, y = e.y, ax = 0, ay = 0; const p = map.get(e.parentId);
      if (p) {
        const parent = compute(p); ax = parent.absoluteX; ay = parent.absoluteY;
        const g = p.group;
        if (g && g.layout !== 'free') {
          const horizontal = g.layout === 'horizontal', siblings = doc.elements.filter(n => n.parentId === p.id), index = siblings.findIndex(n => n.id === e.id);
          const along = g.padding + siblings.slice(0,index).reduce((sum,n) => sum + (horizontal ? n.width : n.height) + g.gap, 0);
          const span = horizontal ? p.height : p.width, size = horizontal ? e.height : e.width;
          const across = g.align === 'center' ? (span - size) / 2 : g.align === 'end' ? span - g.padding - size : g.padding;
          x = horizontal ? along : across; y = horizontal ? across : along;
        }
      }
      const node = Object.assign({}, e, { x, y, absoluteX: ax + x, absoluteY: ay + y }); calculated.set(e.id, node); visiting.delete(e.id); return node;
    }
    return doc.elements.map(compute);
  }
  function resizeCanvas(doc, width, height) {
    const out = normalize(doc); const w = Math.min(8192, Math.max(16, Math.round(Number(width) || doc.width))), h = Math.min(8192, Math.max(16, Math.round(Number(height) || doc.height)));
    out.elements.forEach(e => { if (e.parentId) return; e.x += (w-out.width) * ({ left: 0, center: .5, right: 1 }[e.anchor.horizontal] || 0); e.y += (h-out.height) * ({ top: 0, center: .5, bottom: 1 }[e.anchor.vertical] || 0); }); out.width = w; out.height = h; return out;
  }
  function roots(doc, ids) { const wanted = new Set(ids), map = new Map(doc.elements.map(e => [e.id,e])); return doc.elements.filter(e => { if (!wanted.has(e.id)) return false; let p = map.get(e.parentId), seen = new Set(); while(p && !seen.has(p.id)) { if(wanted.has(p.id)) return false; seen.add(p.id); p=map.get(p.parentId); } return true; }); }
  function descendants(doc, ids) { const set = new Set(ids); for(let i=0;i<doc.elements.length;i++) doc.elements.forEach(e => { if(set.has(e.parentId)) set.add(e.id); }); return set; }
  function align(doc, ids, mode) {
    const out = normalize(doc), nodes = new Map(layout(out).map(e => [e.id,e])), selected = roots(out,ids); if(!selected.length) return out;
    const ns = selected.map(e => nodes.get(e.id)), left=Math.min(...ns.map(e=>e.absoluteX)), right=Math.max(...ns.map(e=>e.absoluteX+e.width)), top=Math.min(...ns.map(e=>e.absoluteY)), bottom=Math.max(...ns.map(e=>e.absoluteY+e.height));
    if(mode==='distributeX'||mode==='distributeY') {
      if(selected.length<3) return out; const horizontal=mode==='distributeX', pos=horizontal?'absoluteX':'absoluteY', size=horizontal?'width':'height', coord=horizontal?'x':'y';
      const sorted=selected.slice().sort((a,b)=>nodes.get(a.id)[pos]-nodes.get(b.id)[pos]), first=nodes.get(sorted[0].id)[pos], last=nodes.get(sorted[sorted.length-1].id), gap=(last[pos]+last[size]-first-sorted.reduce((s,e)=>s+e[size],0))/(sorted.length-1); let cursor=first;
      sorted.forEach(e=>{e[coord]+=cursor-nodes.get(e.id)[pos];cursor+=e[size]+gap;}); return out;
    }
    selected.forEach(e => { const n=nodes.get(e.id); if(mode==='left')e.x+=left-n.absoluteX; if(mode==='right')e.x+=right-n.absoluteX-e.width; if(mode==='center')e.x+=(left+right-e.width)/2-n.absoluteX; if(mode==='top')e.y+=top-n.absoluteY; if(mode==='bottom')e.y+=bottom-n.absoluteY-e.height; if(mode==='middle')e.y+=(top+bottom-e.height)/2-n.absoluteY; }); return out;
  }
  function worldPose(e,nodes) {
    const n=nodes.get(e.id);let x=n.absoluteX+e.width/2,y=n.absoluteY+e.height/2,rotation=e.rotation,opacity=e.opacity,visible=e.visible,parent=nodes.get(e.parentId);
    while(parent){const cx=parent.absoluteX+parent.width/2,cy=parent.absoluteY+parent.height/2,angle=parent.rotation*Math.PI/180,dx=x-cx,dy=y-cy;x=cx+dx*Math.cos(angle)-dy*Math.sin(angle);y=cy+dx*Math.sin(angle)+dy*Math.cos(angle);rotation+=parent.rotation;opacity*=parent.opacity;visible=visible&&parent.visible;parent=nodes.get(parent.parentId);}
    return {x,y,rotation,opacity,visible};
  }
  function group(doc, ids) {
    const out=normalize(doc), selected=roots(out,ids); if(!selected.length||out.elements.length>=100) return out;
    // A common parent preserves sibling clipping/rotation and stacking. Mixed parents move to the canvas.
    const parentId=selected.every(e=>e.parentId===selected[0].parentId)?selected[0].parentId:null, nodes=new Map(layout(out).map(e=>[e.id,e])), parent=nodes.get(parentId), px=parent?parent.absoluteX:0, py=parent?parent.absoluteY:0;
    const ns=selected.map(e=>nodes.get(e.id)), g=createElement('group'); g.name='Группа'; g.parentId=parentId; g.x=Math.min(...ns.map(e=>e.absoluteX))-px; g.y=Math.min(...ns.map(e=>e.absoluteY))-py; g.width=Math.max(...ns.map(e=>e.absoluteX+e.width))-px-g.x; g.height=Math.max(...ns.map(e=>e.absoluteY+e.height))-py-g.y;
    const mixed=parentId===null&&selected.some(e=>e.parentId!==null),poses=mixed?new Map(selected.map(e=>[e.id,worldPose(e,nodes)])):null;
    if(mixed){const bounds=selected.map(e=>{const pose=poses.get(e.id),angle=pose.rotation*Math.PI/180,w=Math.abs(Math.cos(angle))*e.width+Math.abs(Math.sin(angle))*e.height,h=Math.abs(Math.sin(angle))*e.width+Math.abs(Math.cos(angle))*e.height;return{left:pose.x-w/2,right:pose.x+w/2,top:pose.y-h/2,bottom:pose.y+h/2};});g.x=Math.min(...bounds.map(b=>b.left));g.y=Math.min(...bounds.map(b=>b.top));g.width=Math.max(...bounds.map(b=>b.right))-g.x;g.height=Math.max(...bounds.map(b=>b.bottom))-g.y;}
    if(g.width>8192||g.height>8192)return normalize(doc);
    const insert=Math.min(...selected.map(e=>out.elements.indexOf(e))); out.elements.splice(insert,0,g); selected.forEach(e=>{const n=nodes.get(e.id),pose=poses&&poses.get(e.id);e.parentId=g.id;if(pose){e.x=pose.x-e.width/2-g.x;e.y=pose.y-e.height/2-g.y;e.rotation=((pose.rotation+180)%360+360)%360-180;e.opacity=pose.opacity;e.visible=pose.visible;}else{e.x=n.absoluteX-px-g.x;e.y=n.absoluteY-py-g.y;}}); return out;
  }
  function ungroup(doc,id) {
    const out=normalize(doc), g=out.elements.find(e=>e.id===id&&e.type==='group'); if(!g)return out; const nodes=new Map(layout(out).map(e=>[e.id,e])), p=nodes.get(g.parentId);
    out.elements.forEach(e=>{if(e.parentId===id){const n=nodes.get(e.id),cx=nodes.get(id).absoluteX+g.width/2,cy=nodes.get(id).absoluteY+g.height/2,dx=n.absoluteX+e.width/2-cx,dy=n.absoluteY+e.height/2-cy,angle=g.rotation*Math.PI/180;e.parentId=g.parentId;e.x=cx+dx*Math.cos(angle)-dy*Math.sin(angle)-e.width/2-(p?p.absoluteX:0);e.y=cy+dx*Math.sin(angle)+dy*Math.cos(angle)-e.height/2-(p?p.absoluteY:0);e.rotation=((e.rotation+g.rotation+180)%360+360)%360-180;e.opacity*=g.opacity;e.visible=e.visible&&g.visible;}}); out.elements=out.elements.filter(e=>e.id!==id);return out;
  }
  function duplicate(doc,ids) { const out=normalize(doc), top=roots(out,ids), all=descendants(out,top.map(e=>e.id)), copies=out.elements.filter(e=>all.has(e.id)).map(clone); if(out.elements.length+copies.length>100)return out; const remap=new Map(copies.map(e=>[e.id,uid()])), topIds=new Set(top.map(e=>e.id)); copies.forEach(e=>{const old=e.id;e.id=remap.get(old);e.name+=' — копия';if(remap.has(e.parentId))e.parentId=remap.get(e.parentId);if(topIds.has(old)){e.x+=16;e.y+=16;}});out.elements.push(...copies);return out; }
  function remove(doc,ids) { const out=normalize(doc), all=descendants(out,ids);out.elements=out.elements.filter(e=>!all.has(e.id));return out; }
  function reorder(doc,id,direction) {
    const out=normalize(doc),e=out.elements.find(n=>n.id===id);if(!e)return out;
    const siblings=out.elements.filter(n=>n.parentId===e.parentId),rank=siblings.findIndex(n=>n.id===id);let targetRank=rank;
    if(['front','top','last'].includes(direction))targetRank=siblings.length-1;
    else if(['back','bottom','first'].includes(direction))targetRank=0;
    else if(['forward','up',1].includes(direction))targetRank=Math.min(rank+1,siblings.length-1);
    else if(['backward','down',-1].includes(direction))targetRank=Math.max(rank-1,0);
    if(targetRank===rank)return out;
    const moving=descendants(out,[id]),target=descendants(out,[siblings[targetRank].id]),block=out.elements.filter(n=>moving.has(n.id));
    const remaining=out.elements.filter(n=>!moving.has(n.id)),positions=remaining.map((n,i)=>target.has(n.id)?i:-1).filter(i=>i>=0);
    const insertion=targetRank>rank?Math.max(...positions)+1:Math.min(...positions);
    remaining.splice(insertion,0,...block);out.elements=remaining;return out;
  }
  class History {
    constructor(initial,limit) { this.limit=limit||100;this.entries=[];this.index=-1;if(initial)this.push(initial); }
    get canUndo(){return this.index>0;} get canRedo(){return this.index<this.entries.length-1;}
    push(doc){const snapshot=clone(doc);if(this.index>=0&&JSON.stringify(snapshot)===JSON.stringify(this.entries[this.index]))return clone(snapshot);this.entries.splice(this.index+1);this.entries.push(snapshot);if(this.entries.length>this.limit)this.entries.shift();this.index=this.entries.length-1;return clone(snapshot);}
    undo(){if(!this.canUndo)return null;return clone(this.entries[--this.index]);} redo(){if(!this.canRedo)return null;return clone(this.entries[++this.index]);}
    reset(doc){this.entries=[];this.index=-1;if(doc)this.push(doc);}
  }
  global.VDGWidgetModel={createDocument,createElement,normalize,clone,uid,validate,layout,resizeCanvas,align,group,ungroup,duplicate,remove,reorder,History};
})(window);
