/* Local assistant workflow: no provider account, network generation or automatic execution. */
(function(global){
'use strict';
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const BASE_HTML='<section class="vdg-goal"><h1 class="vdg-title" data-vdg-text="title"></h1><div class="vdg-amounts"><span data-vdg-text="current"></span> / <span data-vdg-text="goal"></span> <span data-vdg-text="currency"></span></div><div class="vdg-track"><div class="vdg-fill" data-vdg-progress></div></div><div class="vdg-footer"><span><span data-vdg-text="percent"></span>%</span><span>Осталось <span data-vdg-text="remaining"></span></span></div></section>';
const BASE_CSS='body{font-family:Arial,sans-serif;color:white}.vdg-goal{padding:20px;box-sizing:border-box}.vdg-title{font-size:26px;margin:0 0 12px}.vdg-amounts{font-size:22px}.vdg-track{height:14px;background:#ffffff30;border-radius:7px;margin:14px 0;overflow:hidden}.vdg-fill{height:100%;background:#38bdf8;transition:width .5s ease}.vdg-footer{display:flex;justify-content:space-between;font-size:16px}';
function parse(input,mode='custom'){
 const text=String(input||'').trim();if(!text)throw Error('Вставь ответ нейросети.');if(text.length>650000)throw Error('Ответ слишком большой. Максимум 650 000 символов.');
 const normalize=obj=>{
  if(!obj||typeof obj!=='object'||Array.isArray(obj))throw Error('Ожидается объект с HTML, CSS и JavaScript.');
  if(obj.format&&obj.format!=='vdg-ai/1')throw Error('Неизвестный формат. Нужен vdg-ai/1.');
  if(obj.document!==undefined){
   if(mode==='css')throw Error('Редактируемые слои доступны в режиме собственного виджета.');
   if(['html','css','js','javascript','fields'].some(k=>obj[k]!==undefined&&obj[k]!==''&&!(Array.isArray(obj[k])&&!obj[k].length)))throw Error('Ответ содержит и документ со слоями, и отдельный код. Оставь один вариант.');
   if(!obj.document||typeof obj.document!=='object'||!Array.isArray(obj.document.elements)||!obj.document.elements.length)throw Error('В документе нужен список elements с хотя бы одним слоем.');
   const document=global.VDGWidgetModel.normalize(obj.document),checked=global.VDGWidgetModel.validate(document);
   if(!checked.ok)throw Error('Неверные слои: '+checked.errors.join('; '));
   return {document,html:'',css:'',js:'',fields:[]};
  }
  const result={html:'',css:'',js:'',fields:[]};
  for(const key of ['html','css','js']){if(obj[key]!==undefined&&typeof obj[key]!=='string')throw Error('Поле '+key+' должно содержать текст кода.');result[key]=obj[key]||'';if(result[key].length>200000)throw Error('Поле '+key+' превышает 200 000 символов.');}
  if(obj.javascript!==undefined){if(result.js||typeof obj.javascript!=='string')throw Error('Неоднозначное поле JavaScript.');result.js=obj.javascript;}
  if(obj.fields!==undefined){if(!Array.isArray(obj.fields))throw Error('fields должен быть списком параметров.');result.fields=obj.fields;}
  if(result.fields.length>100)throw Error('Допускается до 100 параметров.');
  const keys=new Set();for(const f of result.fields){if(!f||typeof f!=='object'||Object.keys(f).some(k=>!['key','label','type','default'].includes(k))||!['text','color','number','boolean'].includes(f.type)||typeof f.key!=='string'||!/^[A-Za-z][A-Za-z0-9_]{0,79}$/.test(f.key)||keys.has(f.key)||typeof f.label!=='string'||f.label.length>160)throw Error('Проверь параметры: нужны уникальные key, label, type и default.');keys.add(f.key);if(f.type==='number'&&(typeof f.default!=='number'||!Number.isFinite(f.default)||Math.abs(f.default)>1e15)||f.type==='boolean'&&typeof f.default!=='boolean'||['text','color'].includes(f.type)&&(typeof f.default!=='string'||f.default.length>4000))throw Error('Значение параметра '+f.key+' не соответствует типу.');}
  if(mode==='custom'&&typeof DOMParser!=='undefined'&&/<(?:style|script|html|body|!doctype)\b/i.test(result.html)){
   const page=new DOMParser().parseFromString(result.html,'text/html');if(page.querySelector('script[src],link[rel=stylesheet]'))throw Error('Внешние библиотеки недоступны.');
   const styles=[...page.querySelectorAll('style')],scripts=[...page.querySelectorAll('script')];if(styles.length&&result.css.trim()||scripts.length&&result.js.trim())throw Error('Код одновременно находится внутри HTML и в отдельных полях. Оставь один вариант.');
   if(scripts.some(n=>n.type&&!['text/javascript','application/javascript'].includes(n.type)))throw Error('Модульные script не поддерживаются.');
   if(styles.length)result.css=styles.map(n=>n.textContent).join('\n');if(scripts.length)result.js=scripts.map(n=>n.textContent).join('\n');page.querySelectorAll('style,script').forEach(n=>n.remove());result.html=page.body.innerHTML;
  }
  if(mode==='css'&&(result.html.trim()||result.js.trim()||result.fields.length))throw Error('В режиме оформления нужен только CSS. Для HTML и JavaScript выбери «Собственный виджет».');
  if(mode==='css'&&!result.css.trim())throw Error('В ответе нет CSS.');
  if(mode==='custom'&&!result.html.trim())throw Error('Не найден HTML. Вставь его отдельно или попроси нейросеть вернуть HTML, CSS и JavaScript.');
  return result;
 };
 if(text.startsWith('{')){try{return normalize(JSON.parse(text));}catch(error){if(!(error instanceof SyntaxError))throw error;throw Error('Не удалось прочитать JSON. Вставь полный ответ или отдельные блоки кода.');}}
 const fence=/^\s*(`{3,}|~{3,})[ \t]*([^\r\n]*)\r?\n([\s\S]*?)^\s*\1[ \t]*$/gm;
 const blocks=[...text.matchAll(fence)];
 if(blocks.length){
  const result={},aliases={html:'html',htm:'html',css:'css',js:'js',javascript:'js'};
  for(const block of blocks){const language=block[2].trim().toLowerCase();if(language==='json'){if(blocks.length!==1)throw Error('Найден JSON вместе с другими блоками. Вставь один готовый вариант ответа.');try{return normalize(JSON.parse(block[3]));}catch(error){throw Error('Не удалось прочитать JSON: '+error.message);}}
   const key=aliases[language]||(blocks.length===1&&mode==='css'&&!language?'css':null);
   if(!key)throw Error('Блок кода не подписан как HTML, CSS или JavaScript. Вставь его в отдельное поле.');
   if(result[key]!==undefined)throw Error('Найдено несколько блоков '+language+'. Оставь один вариант или объедини код вручную.');result[key]=block[3].trim();
  }
  return normalize(result);
 }
 if(mode==='css'&&/^[\s\S]*\{[\s\S]*\}/.test(text)&&!/<\/?(?:html|script|style)\b/i.test(text))return normalize({css:text});
 if(mode==='custom'&&/^\s*(?:<!doctype\b|<html\b|<body\b|<(?:div|section|svg|main|article|style)\b)/i.test(text)){
  if(typeof DOMParser==='undefined')throw Error('Вставь полный HTML в поле HTML.');
  const page=new DOMParser().parseFromString(text,'text/html');
  if(page.querySelector('script[src],link[rel="stylesheet"]'))throw Error('В HTML есть внешние библиотеки. Нужен автономный код без внешних подключений.');
  const css=[...page.querySelectorAll('style')].map(n=>n.textContent).join('\n'),scripts=[...page.querySelectorAll('script')];
  if(scripts.some(n=>n.type&&!['text/javascript','application/javascript'].includes(n.type)))throw Error('Тип script не поддерживается: нужен обычный JavaScript без модулей.');
  const js=scripts.map(n=>n.textContent).join('\n');page.querySelectorAll('style,script').forEach(n=>n.remove());
  return normalize({html:page.body.innerHTML,css,js});
 }
 throw Error('Не удалось однозначно выделить код. Вставь подписанные блоки HTML/CSS/JavaScript, JSON vdg-ai/1 или заполни отдельные поля.');
}
let root,state,preview,previewDocument,lastError='',validated='',saving=false,percent=50;
const storageKey='vdg.widget.ai.v1',query=s=>root.querySelector(s);
function defaults(){return {mode:'css',name:'Мой виджет с ИИ',idea:'',width:760,height:220,html:BASE_HTML,css:BASE_CSS,js:'',fields:'[]',values:{},answer:'',documentJSON:'',editLayer:''};}
function persist(){try{localStorage.setItem(storageKey,JSON.stringify(state));}catch{note('Не удалось сохранить поля в браузере. Скопируй код перед закрытием вкладки.',true);}}
function note(message,error=false){lastError=error?message:'';query('[data-ai-status]').textContent=message;query('[data-ai-status]').dataset.error=String(error);}
function formState(){for(const field of root.querySelectorAll('[data-ai-value]')){const key=field.dataset.aiValue;state[key]=field.type==='number'?Number(field.value):field.value;}syncLayerCode();persist();}
function layerContract(){
 const example={format:'vdg-ai/1',document:{schemaVersion:1,name:'Мой виджет',width:760,height:240,background:'transparent',elements:[{id:'art',type:'custom',name:'Рисунок',x:0,y:0,width:240,height:240,custom:{html:'<svg viewBox="0 0 240 240"><circle cx="120" cy="120" r="90" fill="pink"/></svg>',css:'svg{width:100%;height:100%}',js:'',fields:[],values:{}}},{id:'title',type:'text',name:'Название',text:'{{title}}',x:270,y:30,width:450,height:60,style:{fontSize:28,fill:'#ffffff'}},{id:'percent',type:'text',name:'Процент',text:'{{percent}}%',x:70,y:90,width:100,height:60,style:{fontSize:30,textAlign:'center',fill:'#ffffff'}}]}};
 return `Верни один JSON {"format":"vdg-ai/1","document":{...}} без верхнеуровневых html/css/js. Это сохраняет отдельные редактируемые слои. document содержит schemaVersion:1, name, width, height, background:"transparent", elements:[...] (document.elements). Неуказанные свойства получают штатные значения, но id каждого слоя обязателен и уникален. Максимум 100 слоёв, глубина групп до 8. Все размеры и положения — числа в пикселях; ширина/высота документа 16–8192, положительные размеры слоёв.
Каждый слой: {id,type,name,x,y,width,height,rotation:0,opacity:1,visible:true,locked:false,parentId:null,...}. Порядок массива от заднего к переднему. Для вложенного слоя parentId — id группы; координаты относительно группы.
Тип text: text:"{{title}}" либо "{{percent}}%" либо "{{current}} / {{goal}} {{currency}}"; style:{fontFamily:"Arial",fontSize:28,fontWeight:700,fill:"#ffffff",textAlign:"left"}, textFit:"shrink" или wrap/ellipsis/scroll, minFontSize:12, format:{decimals:0,currency:"code",compact:false,rounding:"round"}. Данные через {{...}} доступны только в text-слоях. Не вставляй готовые суммы. Название, процент, суммы и подписи обязательно делай самостоятельными text-слоями, даже если они расположены поверх рисунка.
Тип progress: progress:{shape:"bar"|"ring"|"arc"|"segments",direction:"right"|"left"|"up"|"down"|"center",track:"@track",thickness:12,segments:10,gap:4,startAngle:-90,sweep:360,overflow:"clamp"}, style:{fill:"@primary",fill2:"@secondary",gradient:true,radius:6}. Числовой процент — отдельный text-слой.
Тип shape: style:{fill:"#172136",radius:16,stroke:"transparent",strokeWidth:0}; градиент через fill/fill2/gradient/gradientAngle. Для эллипса radius:9999. Тень: style.shadowColor/shadowBlur/shadowX/shadowY. Тип group: group:{layout:"free"|"horizontal"|"vertical",gap:8,padding:0,align:"start"|"center"|"end"}.
Тип custom: custom:{html:"...",css:"...",js:"...",fields:[],values:{}}. Такой блок содержит ТОЛЬКО сложный рисунок, жидкость, волны или эффекты, которые не выразить штатными слоями. Его надписи выноси в text-слои поверх него. HTML работает в своём iframe размера width × height этого слоя; используй 100%, viewBox и window.innerWidth/innerHeight, не габариты всего документа. Оставь место под свечение внутри границ блока. Данные доступны через vdg:update, не {{...}} внутри HTML.
Для плавного изменения заполнения доступен готовый помощник: VDGMotion.value('fill',target,{initial:target,duration:1000,update:value=>{ /* дробное значение */ }}). Первый вызов сразу показывает initial, последующие плавно идут к новой цели. Одинаковая цель не перезапускает переход. Обрабатывается prefers-reduced-motion. Не округляй координаты и не умножай скорость на число кадров. Для декоративного движения используй CSS transform:translate3d(...) либо rAF с временем; не анимируй SVG-атрибуты координат, если можно двигать вложенную группу через CSS transform. Уровень жидкости и горизонтальные волны делай разными вложенными группами, чтобы их transform не конфликтовал. Не двигай большой слой с фильтром, если можно отдельно двигать содержимое внутри неподвижного свечения.
Цвета style могут быть конкретными или @primary/@secondary/@text/@surface/@track. Для палитры документа: palette:{primary:"#38bdf8",secondary:"#a78bfa",text:"#ffffff",surface:"#172136",track:"#343434"}. Не указывай несуществующие image.asset/fontAsset/maskAsset. При необходимости используй встроенный SVG в custom-блоке.
Минимальный пример структуры: ${JSON.stringify(example)}.
Если пользователь явно хочет цельный HTML, допускается прежний ответ {"format":"vdg-ai/1","html":"...","css":"...","js":"...","fields":[]}; он останется одним программным слоем. Не смешивай оба формата. Не теряй исходные слои и их id при доработке существующей композиции.`;
}
function prompt(repair=false){
 formState();const own=state.mode==='custom';
 return `Создай автономный донат-гол для локальной программы VicDonationGoal. ${own?'Создай редактируемые слои VicDonationGoal. Обычный текст, суммы и прогресс делай отдельными слоями; сложную графику оставляй в программных блоках.':'Напиши ТОЛЬКО CSS для предоставленной структуры. Не меняй HTML и не добавляй JavaScript.'}
Пожелания пользователя: ${state.idea||'Современное читаемое оформление с прозрачным фоном.'}
Размер поля: ${state.width} × ${state.height} пикселей. Оформи всю композицию внутри этих границ, включая свечение; не используй фон страницы трансляции.
Работа выполняется в sandbox iframe без доступа к родителю. Внешняя сеть, fetch, CDN, модули и внешние библиотеки недоступны. Используй обычный CSS, встроенный SVG, при необходимости data: изображения/шрифты. Не используй srcdoc, вложенные iframe, формы, ссылки для переходов и обращения к parent/top/opener. Не создавай бесконечные синхронные циклы. Не пытайся скачивать ресурсы.
Данные обновляются автоматически в элементах data-vdg-text="title|current|goal|remaining|percent|currency|lastName|lastAmount|lastMessage". title — название цели, current — собрано, goal — сумма цели, remaining — остаток не ниже 0, percent — число процентов (может быть больше 100, знак % добавь отдельно), currency — валюта цели. lastAmount — сумма последнего доната, её валюту не подменяй валютой цели. Обычная полоса data-vdg-progress получает ширину 0–100% автоматически. Не записывай тестовые суммы в качестве постоянных данных.
${own?`Для волн, SVG-масок и сложного заполнения слушай addEventListener('vdg:update',e=>{const {state,values}=e.detail; const widget=e.detail.document; /* обновление */}); state.current/goal/remaining/percent — числа; state.title/currency/lastName/lastMessage — строки. document содержит ширину и высоту, название, палитру. values — пользовательские настройки. При первом обновлении только покажи состояние; не имитируй новый донат. Для реакции сравни предыдущее и новое состояние. События с именем donation/goal в iframe не отправляются.
Вынеси полезные настройки в fields: список объектов {key,label,type,default}; type: text, number, color, boolean. Ключ латинскими буквами с цифрами/подчёркиванием, начинается с буквы. До 100 параметров. Для color используй конкретный CSS-цвет, не @primary. Для настройки оформления читай values из vdg:update; для вывода текста доступен data-vdg-field="key". Пример fields: [{"key":"glowColor","label":"Цвет свечения","type":"color","default":"#ff99cc"}].`:`Готовая структура, которую нельзя менять:\n${BASE_HTML}`}
Проверь длинное название, кириллицу, разные валюты, 0%, 100%, 150% и goal=0 (без деления на ноль). Сохрани читаемость на светлом и тёмном фоне. Шахматка предпросмотра не должна рисоваться самим виджетом. Анимации плавные, без тяжёлых фильтров на весь экран. Для JavaScript используй requestAnimationFrame и время кадра, а не фиксированный шаг на кадр. Не округляй координаты до целых пикселей. Не перезапускай переход, если его целевое значение не изменилось. Декоративные волны могут работать независимо от обновлений данных. Числа в data-vdg-text выводятся с максимум двумя знаками после запятой; в state остаются точные числа. Для своего вывода числа форматируй через Intl.NumberFormat или toLocaleString, не вставляй сырой процент в текст.
${own?layerContract():`Ответ верни ОДНИМ блоком JSON без пояснений: {"format":"vdg-ai/1","html":"","css":"код CSS","js":"","fields":[]}. Экранируй переносы и кавычки по правилам JSON. Можно вернуть один подписанный блок css.`}

${repair?`Исправь текущий вариант, сохрани задумку и полезные настройки. Ошибка проверки: ${lastError||'Пользователь хочет доработать оформление.'}\nТекущий код и параметры:\n${JSON.stringify(state.documentJSON?{format:'vdg-ai/1',document:JSON.parse(state.documentJSON)}:{html:state.html,css:state.css,js:state.js,fields:state.fields})}\nНеразобранный ответ (если есть):\n${state.answer}`:''}`;
}
function validateCustom(custom){
 const fields=parse(JSON.stringify({format:'vdg-ai/1',html:'<div></div>',fields:custom.fields}),'custom').fields;
 custom.values=Object.fromEntries(fields.map(f=>[f.key,custom.values[f.key]??f.default]));
 if(!custom.html.trim())throw Error('Заполни HTML — элементы виджета.');
 for(const key of ['html','css','js'])if(custom[key].length>200000)throw Error('Поле '+key+' превышает 200 000 символов.');
 for(const f of fields){const value=custom.values[f.key];if(f.type==='number'&&(typeof value!=='number'||!Number.isFinite(value)||Math.abs(value)>1e15)||f.type==='boolean'&&typeof value!=='boolean'||['text','color'].includes(f.type)&&(typeof value!=='string'||value.length>4000))throw Error('Проверь значение параметра «'+f.label+'».');if(f.type==='color'&&(!CSS.supports('color',value)||!/^(#[0-9a-f]{3,8}|[a-z]{1,30}|(?:rgb|rgba|hsl|hsla)\([0-9.,%+\- /]+\))$/i.test(value)))throw Error('Параметр «'+f.label+'» должен содержать конкретный цвет, например #ff99cc.');}
 if(custom.css.trim()){const sheet=new CSSStyleSheet();try{sheet.replaceSync(custom.css);}catch{throw Error('CSS не удалось прочитать. Проверь скобки и вставь только стили.');}if(!sheet.cssRules.length)throw Error('В поле CSS не найдены правила оформления. Вставь CSS без пояснений нейросети.');}
 const page=new DOMParser().parseFromString(custom.html,'text/html');
 if(page.querySelector('style,script'))throw Error('Перенеси содержимое style и script в отдельные CSS и JavaScript. Или вставь полный HTML через «Разобрать ответ».');
 if(page.querySelector('iframe,object,embed,base,meta,link,form'))throw Error('В HTML есть неподдерживаемые элементы (iframe, внешние подключения или форма). Скопируй запрос на исправление.');
 const external=[...page.querySelectorAll('[src],[href]')].some(n=>['src','href'].some(k=>{const v=n.getAttribute(k);return v&&!v.startsWith('data:')&&!v.startsWith('#');}));
 if(external||/@import\b|url\(\s*['"]?\s*(?:https?:|\/\/)/i.test(custom.css))throw Error('Внешние ресурсы недоступны. Используй встроенный SVG или data: ресурс; попроси нейросеть убрать внешние подключения.');
}
function syncLayerCode(){
 if(state.mode!=='custom'||!state.documentJSON)return;
 const document=JSON.parse(state.documentJSON);Object.assign(document,{name:state.name,width:state.width,height:state.height});const layer=document.elements.find(e=>e.id===state.editLayer&&e.type==='custom');
 if(layer){let fields;try{fields=JSON.parse(state.fields);}catch{return;}layer.custom={html:state.html,css:state.css,js:state.js,fields,values:{...state.values}};}
 state.documentJSON=JSON.stringify(document,null,2);const source=query('[data-ai-value="documentJSON"]');if(source)source.value=state.documentJSON;
}
function loadLayerCode(){
 if(!state.documentJSON)return;
 const document=JSON.parse(state.documentJSON),custom=document.elements.filter(e=>e.type==='custom');
 const layer=custom.find(e=>e.id===state.editLayer)||custom[0];state.editLayer=layer?.id||'';
 const code=layer?.custom||{html:'',css:'',js:'',fields:[],values:{}};
 Object.assign(state,{html:code.html,css:code.css,js:code.js,fields:JSON.stringify(code.fields,null,2),values:{...code.values}});
}
function makeDocument(){
 formState();const M=global.VDGWidgetModel;let doc;
 if(state.mode==='custom'&&state.documentJSON){
  doc=M.normalize(JSON.parse(state.documentJSON));doc.name=state.name||doc.name;doc.width=state.width;doc.height=state.height;
  for(const layer of doc.elements)if(layer.type==='custom')validateCustom(layer.custom);
 }else{
  doc=M.createDocument(state.name||'Мой виджет с ИИ');doc.width=state.width;doc.height=state.height;
  const layer=M.createElement('custom');layer.name='Оформление с ИИ';layer.width=doc.width;layer.height=doc.height;
  let fields;try{fields=JSON.parse(state.fields);}catch{throw Error('Параметры не удалось прочитать. Нужен JSON-массив; если параметров нет, оставь [].');}
  fields=parse(JSON.stringify({format:'vdg-ai/1',html:'<div></div>',fields}),'custom').fields;
  layer.custom={html:state.mode==='css'?BASE_HTML:state.html,css:state.css,js:state.mode==='css'?'':state.js,fields,values:Object.fromEntries(fields.map(f=>[f.key,state.values[f.key]??f.default]))};
  if(state.mode==='css'&&!state.css.trim())throw Error('Заполни CSS — оформление.');
  validateCustom(layer.custom);doc.elements=[layer];
 }
 const checked=M.validate(doc);if(!checked.ok)throw Error('Проверь размеры, параметры и код: '+checked.errors.join('; '));return doc;
}
function testState(){const goal=10000;return {title:query('[data-ai-test-title]').value||'Новый микрофон',goal,current:goal*percent/100,currency:query('[data-ai-currency]').value,lastName:'Тестовый зритель',lastAmount:500,lastMessage:'На новый микрофон'};}
function renderValues(doc){
 query('[data-ai-parameters]').innerHTML=doc.elements.filter(e=>e.type==='custom').map(layer=>layer.custom.fields.map(f=>`<label>${esc(f.label)}${f.type==='boolean'?`<input type="checkbox" data-ai-parameter="${esc(f.key)}" data-ai-layer="${esc(layer.id)}" ${layer.custom.values[f.key]?'checked':''}>`:`<input type="${f.type==='number'?'number':f.type==='color'&&/^#[0-9a-f]{6}$/i.test(String(f.default))?'color':'text'}" data-ai-parameter="${esc(f.key)}" data-ai-layer="${esc(layer.id)}" value="${esc(layer.custom.values[f.key])}">`}</label>`).join('')).join('');
}
function showPreview(){
 const doc=makeDocument();preview?.destroy();preview=null;previewDocument=doc;validated=JSON.stringify(doc);lastError='';
 const host=query('[data-ai-preview]');host.replaceChildren();
 preview=global.VDGWidgetRenderer.mount(host,doc,{editor:true,animate:true,onError:message=>{validated='';note('Ошибка кода: '+message,true);}});
 preview.update(testState());renderValues(doc);resizePreview();
 note('Предпросмотр готов. Проверь данные и внешний вид. OBS без изменений.');
 if(state.mode==='custom'&&!state.documentJSON&&!/data-vdg-(?:text|progress)|vdg:update/.test(state.html+state.js))note('Предпросмотр готов, но привязка к данным не найдена. Проверь: суммы и название могут оставаться статичными.');
}
function resizePreview(){if(!root||!previewDocument)return;const host=query('[data-ai-preview]'),el=host.firstElementChild;if(!el)return;const scale=Math.min(1,(host.clientWidth||760)/previewDocument.width);el.style.transformOrigin='0 0';el.style.transform=`scale(${scale})`;host.style.height=Math.max(180,previewDocument.height*scale)+'px';}
async function copy(text){query('[data-ai-prompt]').value=text;try{await navigator.clipboard.writeText(text);note('Запрос скопирован. Отправь его в выбранную нейросеть.');}catch{query('[data-ai-prompt]').focus();query('[data-ai-prompt]').select();note('Запрос готов ниже. Скопируй его вручную: Ctrl+C.');}}
function populate(){const layered=state.mode==='custom'&&!!state.documentJSON;query('[data-ai-layer-tools]').hidden=!layered;if(layered){const document=JSON.parse(state.documentJSON),custom=document.elements.filter(e=>e.type==='custom');query('[data-ai-layer-summary]').textContent=document.elements.length+' слоёв. Тексты, суммы и прогресс можно менять отдельно в редакторе. Ниже — код выбранного программного слоя.';query('[data-ai-code-layer]').innerHTML=custom.map(e=>`<option value="${esc(e.id)}" ${state.editLayer===e.id?'selected':''}>${esc(e.name)}</option>`).join('');query('[data-ai-code-layer]').disabled=!custom.length;}for(const field of root.querySelectorAll('[data-ai-value]'))field.value=state[field.dataset.aiValue]??'';const cssOnly=state.mode==='css';const noCode=layered&&!state.editLayer;query('[data-ai-value="html"]').readOnly=cssOnly||noCode;query('[data-ai-value="js"]').readOnly=cssOnly||noCode;query('[data-ai-value="css"]').readOnly=noCode;query('[data-ai-fields-wrap]').hidden=cssOnly;query('[data-ai-mode-note]').textContent=cssOnly?'Готовая структура уже подключена к данным. Нужен только CSS; HTML и JavaScript доступны в режиме собственного виджета.':'Отдельные редактируемые слои для текста и прогресса; сложная графика — в программных блоках. Цельный HTML тоже поддерживается.';}
function mount(container){
 if(root){container.append(root);resizePreview();return;}
 state=defaults();try{const saved=JSON.parse(localStorage.getItem(storageKey));if(saved&&['css','custom'].includes(saved.mode))state={...state,...saved};}catch{}
 root=document.createElement('section');root.className='ai-workspace';root.dataset.aiRoot='';
 root.innerHTML=`<p class="ai-intro">Опиши идею, отправь готовый запрос в любую нейросеть и вставь её ответ здесь.</p><div class="ai-columns"><section class="ai-request"><h2>Запрос для нейросети</h2><label>Режим создания<select data-ai-value="mode" aria-label="Режим создания"><option value="css">Оформить стандартный виджет — CSS</option><option value="custom">Создать собственный виджет — слои и код</option></select></label><p data-ai-mode-note class="hint"></p><label>Название оформления<input data-ai-value="name" maxlength="160"></label><div class="ai-sizes"><label>Ширина<input data-ai-value="width" type="number" min="16" max="8192"></label><label>Высота<input data-ai-value="height" type="number" min="16" max="8192"></label></div><label>Как должен выглядеть виджет?<textarea data-ai-value="idea" rows="5" maxlength="10000" placeholder="Например: цветок с розовой жидкостью, белым свечением и процентом внутри"></textarea></label><p class="hint">Референс приложи в самой нейросети. Чем точнее опишешь форму, расположение, цвета и движение, тем полезнее будет результат.</p><button data-ai-action="prompt">Скопировать запрос</button><details><summary>Посмотреть готовый запрос</summary><textarea data-ai-prompt rows="12" readonly aria-label="Готовый запрос"></textarea></details><p><a href="#guidebook/appearance/ai">Как создать и доработать виджет с ИИ</a></p></section><section class="ai-code"><h2>Ответ и код</h2><label>Ответ нейросети целиком<textarea data-ai-value="answer" rows="5" placeholder="Вставь JSON, подписанные блоки кода или полный HTML"></textarea></label><button class="secondary" data-ai-action="parse">Разобрать ответ</button><p class="hint">Разбор заменит поля ниже, только если ответ распознан однозначно. Если не получилось — скопируй код в нужные поля вручную.</p><section data-ai-layer-tools hidden><p data-ai-layer-summary role="status"></p><label>Программный слой<select data-ai-code-layer></select></label><details><summary>Слои оформления — JSON</summary><label>Слои оформления (JSON)<textarea data-ai-value="documentJSON" rows="8" readonly></textarea></label></details></section><details class="ai-code-details"><summary>Код и параметры оформления</summary><label>HTML — элементы виджета<textarea data-ai-value="html" rows="5" spellcheck="false"></textarea></label><label>CSS — оформление<textarea data-ai-value="css" rows="7" spellcheck="false"></textarea></label><label>JavaScript — поведение<textarea data-ai-value="js" rows="5" spellcheck="false" placeholder="Необязательно"></textarea></label><details data-ai-fields-wrap><summary>Параметры, созданные нейросетью</summary><label>Параметры оформления (JSON)<textarea data-ai-value="fields" rows="4" spellcheck="false"></textarea></label></details></details><div class="inline-actions"><button data-ai-action="preview">Проверить и показать</button><button class="secondary" data-ai-action="repair">Скопировать запрос на исправление</button><button class="secondary" data-ai-action="current">Доработать текущий черновик</button></div><p data-ai-status role="status" aria-live="polite"></p></section></div><section class="ai-result"><div class="section-heading"><h2>Предпросмотр</h2><span>Тестовые данные · OBS без изменений</span></div><div class="ai-test"><label>Название для проверки<input data-ai-test-title value="Новый микрофон"></label><label>Валюта<select data-ai-currency><option>RUB</option><option>USD</option><option>EUR</option></select></label>${[0,50,100,150].map(n=>`<button class="secondary" data-ai-percent="${n}">${n}%</button>`).join('')}<button class="secondary" data-ai-donation>Тестовый донат</button><button class="secondary" data-ai-stop>Остановить предпросмотр</button></div><div data-ai-preview class="ai-preview"><p>Нажми «Проверить и показать», чтобы увидеть результат.</p></div><div data-ai-parameters class="ai-parameters"></div><div class="inline-actions ai-save"><button class="secondary" data-ai-action="draft">Открыть в редакторе</button><button class="secondary" data-ai-action="save">Сохранить вариант</button><button data-ai-action="apply">Применить в OBS</button></div><p class="hint">Сначала проверь оформление. Сохранение варианта не меняет OBS. Перед заменой рабочего черновика его предыдущая версия сохраняется в библиотеке. Поля кода запоминаются в этом браузере; для переноса сохрани вариант и экспортируй ZIP в редакторе.</p></section>`;
 container.append(root);populate();
 root.addEventListener('input',event=>{if(event.target.matches('[data-ai-value]')){formState();if(!['answer','idea'].includes(event.target.dataset.aiValue)){validated='';for(const input of root.querySelectorAll('[data-ai-parameter]'))input.disabled=true;if(preview)note('Код или параметры изменены. Нажми «Проверить и показать» ещё раз.');}}if(event.target.matches('[data-ai-test-title],[data-ai-currency]'))preview?.update(testState());if(event.target.matches('[data-ai-parameter]')){if(!preview||!validated)return;const layer=previewDocument?.elements.find(e=>e.id===event.target.dataset.aiLayer),field=layer?.custom.fields.find(f=>f.key===event.target.dataset.aiParameter);if(!field)return;const value=field.type==='boolean'?event.target.checked:field.type==='number'?Number(event.target.value):event.target.value;layer.custom.values[field.key]=value;if(state.mode==='custom'&&state.documentJSON){const document=JSON.parse(state.documentJSON),saved=document.elements.find(e=>e.id===layer.id);saved.custom.values[field.key]=value;state.documentJSON=JSON.stringify(document,null,2);query('[data-ai-value="documentJSON"]').value=state.documentJSON;if(state.editLayer===layer.id)state.values[field.key]=value;}else state.values[field.key]=value;persist();preview.setDocument(previewDocument);preview.update(testState());validated=JSON.stringify(previewDocument);}});
 root.addEventListener('change',event=>{if(event.target.matches('[data-ai-code-layer]')){formState();state.editLayer=event.target.value;loadLayerCode();populate();persist();}if(event.target.matches('[data-ai-value="mode"]')){formState();validated='';populate();}if(event.target.matches('[data-ai-currency]'))preview?.update(testState());});
 root.addEventListener('click',async event=>{
  const percentage=event.target.closest('[data-ai-percent]');if(percentage){percent=Number(percentage.dataset.aiPercent);preview?.update(testState());return;}
  if(event.target.closest('[data-ai-donation]')){percent+=5;preview?.update(testState(),{event:'donation'});return;}
  if(event.target.closest('[data-ai-stop]')){preview?.destroy();preview=null;validated='';query('[data-ai-preview]').textContent='Предпросмотр остановлен.';query('[data-ai-parameters]').replaceChildren();return;}
  const button=event.target.closest('[data-ai-action]');if(!button)return;const action=button.dataset.aiAction;
  if(saving)return;button.disabled=true;
  try{
   if(action==='prompt'||action==='repair'){await copy(prompt(action==='repair'));return;}
   if(action==='parse'){formState();const result=parse(state.answer,state.mode);state.documentJSON=result.document?JSON.stringify(result.document,null,2):'';state.editLayer='';if(result.document){state.name=result.document.name;state.width=result.document.width;state.height=result.document.height;}state.html=state.mode==='css'?BASE_HTML:result.html;state.css=result.css;state.js=result.js;state.fields=JSON.stringify(result.fields,null,2);state.values={};if(result.document)loadLayerCode();validated='';persist();populate();note('Ответ разобран. Код ещё не запущен — нажми «Проверить и показать».');return;}
   if(action==='preview'){showPreview();return;}
   if(action==='current'){
    const current=global.VDGWidgetEditor.getDocument();if(!current)throw Error('Редактор пока загружается.');
    if(current.elements.length===1&&current.elements[0].type==='custom'){
     const c=current.elements[0].custom;state={...state,name:current.name,width:current.width,height:current.height,mode:'custom',documentJSON:'',editLayer:'',html:c.html,css:c.css,js:c.js,fields:JSON.stringify(c.fields,null,2),values:{...c.values}};
    }else{state={...state,name:current.name,width:current.width,height:current.height,mode:'custom',documentJSON:JSON.stringify(current,null,2),editLayer:''};loadLayerCode();}
    persist();populate();validated='';note('Код текущего черновика загружен. Опиши правки и скопируй запрос на исправление.');return;
   }
   const design=makeDocument();
   // A checked result is tied to this exact code, settings and dimensions.
   if(!validated||JSON.stringify({...design,id:previewDocument?.id,elements:design.elements.map((e,i)=>({...e,id:previewDocument?.elements[i]?.id}))})!==validated)throw Error('Сначала нажми «Проверить и показать» для текущего кода и настроек.');
   if(lastError)throw Error(lastError);
   saving=true;await global.VDGWidgetEditor.importAIDocument(previewDocument,{save:action==='save',apply:action==='apply'});
   note(action==='apply'?'Применено в OBS.':action==='save'?'Вариант сохранён. OBS без изменений.':'Черновик открыт в редакторе. OBS без изменений.');if(action==='draft')location.hash='widget/editor';
  }catch(error){note(error.message,true);}finally{saving=false;button.disabled=false;}
 });
 new ResizeObserver(resizePreview).observe(query('[data-ai-preview]'));
 global.addEventListener('hashchange',()=>{if(location.hash!=='#widget/ai'&&preview){preview.destroy();preview=null;validated='';query('[data-ai-preview]').textContent='Предпросмотр остановлен. Нажми «Проверить и показать», чтобы запустить снова.';query('[data-ai-parameters]').replaceChildren();}});
}
global.VDGWidgetAI={mount,parse};
})(window);
