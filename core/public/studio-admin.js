/* Working Studio shell. Move existing controls instead of duplicating their handlers. */
(() => {
'use strict';
const by = id => document.getElementById(id);
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const sections = [
 ['home','Главная','home',[['dashboard','Главная']]],
 ['donations','Донаты','wallet',[['history','История'],['top','TopDonation'],['goal','Параметры цели'],['manual','Добавить вручную'],['rates','Курсы валют']]],
 ['widget','Виджет','layout',[['editor','Редактор'],['presets','Оформления'],['ai','Создать с ИИ'],['obs','Подключение к OBS']]],
 ['tts','Озвучка','audio',[['queue','Очередь'],['profiles','Голосовые профили'],['rules','Правила'],['providers','Настройки и провайдеры'],['history','История озвучки'],['logs','Логи']]],
 ['integrations','Интеграции','plug',[['services','Подключения'],['streamerbot','Streamer.bot']]],
 ['settings','Настройки','settings',[['appearance','Оформление'],['data','Данные и перенос'],['diagnostics','Диагностика']]],
 ['guidebook','Гайдбук','academic',[['appearance','Оформление']]]
];
const paths = {home:'M3 10 12 3l9 7v10H3Z M9 20v-7h6v7',wallet:'M3 6h17v14H3Z M3 6V4h15 M16 12h5v4h-5Z',layout:'M3 3h18v18H3Z M3 9h18 M9 9v12',audio:'M3 10h4l5-5v14l-5-5H3Z M16 8q6 4 0 8',plug:'M8 3v5 M16 3v5 M6 8h12v4a6 6 0 0 1-12 0Z M12 18v4',settings:'M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8 M12 2v3 M12 19v3 M2 12h3 M19 12h3 M5 5l2 2 M17 17l2 2 M5 19l2-2 M17 7l2-2'};
const icon = name => `<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="${paths[name]}"></path></svg>`;
paths.academic='M2 9 12 4l10 5-10 5Z M6 11v6q6 5 12 0v-6 M22 9v8';
let route = '', section = 'home', selected = null, status = null, statusAt = 0, latestSignature = '', homeTop = null, homeTopLoading = false;
const views = new Map();
const oldShell = document.querySelector('.admin-shell');
const parking = document.createElement('div');parking.id='studioParking';parking.hidden=true;document.body.append(parking);
const root = document.createElement('div');root.className='studio-shell';
root.innerHTML=`<aside class="sidebar studio-sidebar"><div class="brand"><strong>VicDonationGoal</strong><span>1.5</span></div><nav aria-label="Разделы">${sections.map(([id,label,ico,pages])=>`<div class="nav-group" data-menu="${id}"><a class="global-link studio-nav-link" href="#${id}/${pages[0][0]}">${icon(ico)}<span>${label}</span></a>${['home','guidebook'].includes(id)?'':`<button class="menu-toggle" aria-label="Подразделы: ${label}" aria-expanded="false" aria-controls="quick-${id}">⌄</button><div class="quick-menu" id="quick-${id}" inert>${pages.map(([p,title])=>`<a class="quick-link" href="#${id}/${p}">${title}</a>`).join('')}</div>`}</div>`).join('')}</nav><footer><span id="studioCore" class="state"><i class="dot off"></i><span>Проверка Core…</span></span><time id="studioClock" class="moscow-time"></time><a href="/docs/index.html" target="_blank" rel="noopener">Документация</a><div id="studioThemeMount"></div></footer></aside><div class="side-workspace"><nav class="side-subnav studio-subnav" aria-label="Подразделы" hidden></nav><main class="content studio-main" id="main-content"><header class="page-heading"><div id="studioHeading"></div><div class="heading-actions" id="studioActions"></div></header><div id="studioViews"></div></main></div><div id="toast" role="status" aria-live="polite"></div><dialog id="dialog"><div id="dialog-content"></div><form method="dialog"><button class="secondary">Закрыть</button></form></dialog><aside id="studioDonationDetail" class="studio-detail" hidden aria-label="Подробности доната"></aside>`;
document.body.insertBefore(root,oldShell);
document.body.dataset.variant='d';document.body.dataset.adminPanel='studio';
const title=by('pageSectionTitle');by('studioHeading').append(title);
by('studioHeading').insertAdjacentHTML('beforeend','<p id="studioDescription"></p>');
fetch('/api/health').then(r=>r.json()).then(health=>{if(health.preview){const note=document.createElement('p');note.className='studio-preview-note';note.textContent='Предпросмотр отдельной копии. Подключения, оповещения и озвучка отключены.';by('studioHeading').append(note);}}).catch(()=>{});
by('studioThemeMount').append(by('sidebarThemeSlot'));
function view(key){const el=document.createElement('section');el.className='studio-view';el.dataset.route=key;el.hidden=true;by('studioViews').append(el);views.set(key,el);return el;}
for(const [id,,,pages] of sections)for(const [p] of pages)view(`${id}/${p}`);
function move(key,node){if(node)views.get(key).append(node);}
const manual=by('usernameInput').closest('section.card');manual.classList.add('panel','manual-panel','studio-manual');
const goal=by('goalTitlePreview').closest('section.card');goal.classList.add('panel','goal-panel','compact','studio-goal');
goal.querySelector('.card-title h2').replaceWith(by('goalTitlePreview'));
goal.querySelector('.goal-preview').prepend(by('goalNumbersPreview'));
const goalNumbers=document.createElement('div');goalNumbers.className='studio-goal-numbers';goalNumbers.append(by('goalNumbersPreview'),by('progressText'));goal.querySelector('.goal-preview').prepend(goalNumbers);
goal.querySelector('.card-title').insertAdjacentHTML('beforeend','<a href="#donations/goal">Изменить</a>');
const goalFoot=document.createElement('div');goalFoot.className='goal-foot';goalFoot.append(by('leftPreview').closest('.stat'));goal.append(goalFoot);
goalFoot.insertAdjacentHTML('beforeend','<a class="studio-goal-widget-link" href="#widget/editor">Оформление виджета <span aria-hidden="true">↗</span></a>');
parking.append(manual,goal);
move('donations/goal',by('titleInput').closest('section.card'));
move('donations/goal',by('undoButton').closest('section.card'));
const summary=document.createElement('details');summary.className='card studio-goal-summary';summary.innerHTML='<summary>Сводка по сбору</summary>';const stats=goal.querySelector('.stats');stats.hidden=false;summary.append(stats);views.get('donations/goal').append(summary);
move('donations/history',document.querySelector('.history-filter-card'));
move('donations/history',by('historyDonationsView'));
move('donations/top',by('topDonorsView'));
move('donations/rates',by('rateUSDInput').closest('section.card'));
const dataView=by('donationSettingsView');
[...dataView.querySelectorAll('section.card')].forEach(node=>move('settings/data',node));
move('settings/diagnostics',by('donationStatusView'));
const ttsOverview=document.querySelector('.tts-overview-grid');move('tts/queue',ttsOverview);
for(const [page,id] of [['queue','ttsQueueView'],['profiles','ttsProfilesView'],['rules','ttsRulesView'],['providers','ttsSettingsView'],['history','ttsHistoryView'],['logs','ttsLogsView']])move(`tts/${page}`,by(id));
// Reparent the same provider cards; resizing never recreates inputs or resets drafts.
const providerSettings=by('ttsSettingsView');
const providerGrids=[...providerSettings.querySelectorAll(':scope > .grid')];
const providerCards=providerGrids.flatMap(grid=>[...grid.children]);
const providerColumns=[0,1].map(()=>{const column=document.createElement('div');column.className='tts-provider-column';providerSettings.append(column);return column;});
providerGrids.forEach(grid=>grid.remove());
providerSettings.classList.add('tts-provider-layout');
const providerNarrow=matchMedia('(max-width:960px)');
function layoutProviders(){providerColumns[1].hidden=providerNarrow.matches;providerCards.forEach((card,index)=>providerColumns[providerNarrow.matches?0:index%2].append(card));}
providerNarrow.addEventListener('change',layoutProviders);layoutProviders();
[...by('integrationsPanel').children].forEach(node=>move('integrations/services',node));
views.get('settings/appearance').innerHTML='<section class="card"><div id="studioAppearanceSettings"></div></section>';
views.get('widget/obs').innerHTML=`<section class="card studio-obs"><h2>Виджет в OBS</h2><p>Добавь в OBS источник «Браузер» и вставь адрес виджета.</p><label>Адрес виджета<input id="studioWidgetAddress" readonly></label><div class="inline-actions"><button id="studioCopyWidget">Скопировать адрес</button><a class="link-button secondary" href="/widget.html" target="_blank" rel="noopener">Открыть виджет</a></div><label class="studio-obs-backdrop-label">Подложка предпросмотра<select id="studioObsBackdrop"><option value="checker">Прозрачность</option><option value="dark">Тёмная</option><option value="light">Светлая</option></select></label><iframe data-backdrop="checker" title="Предпросмотр текущего виджета" src="/widget.html" loading="lazy"></iframe><p class="hint">Здесь показано применённое оформление. Изменить его можно в разделе «Редактор», выбрать готовую основу — в «Оформлениях».</p><details><summary>Восстановление оформления</summary><p class="hint">Вернуть виджет, применённый перед текущим. Это изменит OBS и рабочий черновик.</p><button id="studioRestoreWidget" class="secondary">Восстановить предыдущий виджет</button></details></section>`;
by('studioRestoreWidget').onclick=async()=>{const button=by('studioRestoreWidget');button.disabled=true;try{const response=await fetch('/api/widget/editor'),data=await response.json();if(!response.ok)throw Error(data.error||'Не удалось проверить оформление');if(!data.settings?.previousActive){toast('Предыдущего применённого виджета пока нет.');return;}if(!confirm('Восстановить предыдущий виджет в OBS? Рабочий черновик тоже будет заменён.'))return;window.VDGWidgetEditor.mount(views.get('widget/editor'));await window.VDGWidgetEditor.ready;await window.VDGWidgetEditor.restorePrevious();toast('Предыдущее оформление восстановлено.');}catch(error){toast(error.message);}finally{button.disabled=false;}};
by('studioObsBackdrop').onchange=()=>{views.get('widget/obs').querySelector('iframe').dataset.backdrop=by('studioObsBackdrop').value;};
by('studioWidgetAddress').value=new URL('/widget.html',location.href).href;
by('studioCopyWidget').onclick=()=>navigator.clipboard.writeText(by('studioWidgetAddress').value).then(()=>toast('Адрес скопирован.')).catch(()=>toast('Выдели адрес и скопируй вручную.'));
oldShell.hidden=true;
window.updateAdminPanelContext=panel=>{document.body.dataset.adminPanel='studio';if(panel==='integrationsPanel')location.hash='integrations/services';else if(panel==='ttsPanel')location.hash='tts/queue';};
const home=views.get('home/dashboard');
const live={manual,goal};
for(const id of ['connections','latest','speech','top','summary','ttsHistory','services']){live[id]=document.createElement('section');live[id].className=`panel studio-live-${id}`;}
live.rates=by('rateUSDInput').closest('section.card');
live.ttsQueue=by('ttsQueueBody').closest('section.card');
live.ttsTest=by('ttsTestText').closest('section.card');
const sharedHomes={rates:views.get('donations/rates'),ttsQueue:by('ttsQueueView'),ttsTest:ttsOverview};
for(const id of ['rates','ttsQueue','ttsTest'])live[id].classList.add('panel','studio-shared-module');
live.connections.classList.add('dashboard-connections');
live.latest.innerHTML='<div class="section-heading"><h2>Последние донаты</h2><a href="#donations/history">Вся история</a></div><div class="donation-feed" id="studioLatest"></div>';
live.speech.innerHTML='<div class="section-heading"><h2>Озвучка</h2><a href="#tts/queue">Очередь</a></div><div id="studioSpeech"></div><div class="inline-actions"><button class="secondary" data-studio-tts="ttsPauseButton">Пауза</button><button class="secondary" data-studio-tts="ttsResumeButton">Продолжить</button></div>';
live.top.innerHTML='<div class="section-heading"><h2>TopDonation</h2><a href="#donations/top">Все донатеры</a></div><div id="studioTop"></div>';
live.summary.innerHTML='<div class="section-heading"><h2>Сводка донатов</h2><a href="#donations/history">История</a></div><div id="studioDonationSummary" class="studio-summary-grid"></div>';
live.ttsHistory.innerHTML='<div class="section-heading"><h2>Последняя озвучка</h2><a href="#tts/history">Вся история</a></div><div id="studioRecentSpeech"></div>';
live.services.innerHTML='<div class="section-heading"><h2>Сервисы</h2><a href="#integrations/services">Настроить</a></div><div id="studioServiceDetails"></div>';
function park(){for(const [id,node] of Object.entries(live))(sharedHomes[id]||parking).append(node);}
park();
function homeNeedsSpeech(){return window.VDGDashboard.get().widgets.some(w=>w.id==='speech'||w.id.startsWith('tts'));}
function mountDashboard(){if(section!=='home')return;park();home.innerHTML=window.VDGDashboard.render();for(const slot of home.querySelectorAll('[data-live-slot]')){const node=live[slot.dataset.liveSlot];if(node)slot.append(node);}by('studioActions').innerHTML=window.VDGDashboard.actions();by('ttsPanel').classList.toggle('active',homeNeedsSpeech());updateLive();refreshHomeTop();}
let toastTimer;
function toast(text){by('toast').textContent=text;by('toast').classList.add('visible');clearTimeout(toastTimer);toastTimer=setTimeout(()=>by('toast').classList.remove('visible'),5500);}
function showDialog(html){by('dialog-content').innerHTML=html;if(!by('dialog').open)by('dialog').showModal();}
window.VDGDashboard.connect({render:mountDashboard,beforeRender:()=>{if(section==='home')park();},toast,showDialog,closeDialog:()=>by('dialog').close()});
function linksFor(sec){return sections.find(s=>s[0]===sec)[3];}
function navigate(){
 const aliases={donationsPanel:'home/dashboard',ttsPanel:'tts/queue',integrationsPanel:'integrations/services',donationMonitoringView:'home/dashboard',donationManagementView:'donations/manual',donationHistoryTopView:'donations/history',donationStatusView:'settings/diagnostics',donationSettingsView:'settings/data',ttsSettingsView:'tts/providers',ttsProfilesView:'tts/profiles',ttsRulesView:'tts/rules',ttsHistoryView:'tts/history',ttsLogsView:'tts/logs'};
 if(aliases[location.hash.slice(1)])history.replaceState(null,'','#'+aliases[location.hash.slice(1)]);
 const parts=location.hash.slice(1).split('/');section=sections.some(s=>s[0]===parts[0])?parts[0]:'home';
 const pages=linksFor(section);const page=pages.some(p=>p[0]===parts[1])?parts[1]:pages[0][0];const next=`${section}/${page}`;
 if(section==='guidebook')window.VDGGuidebook.mount(views.get(next),parts[2],parts[3]);
 if(next===route)return;route=next;park();if(section==='home')mountDashboard();else if(next==='donations/manual')views.get(next).prepend(manual);
 for(const [key,el] of views)el.hidden=key!==next;
 document.body.classList.toggle('widget-editing',section==='widget'&&page!=='obs');
 if(section==='widget'&&page!=='obs'){window.VDGWidgetEditor.mount(views.get('widget/editor'));if(page==='presets')window.VDGWidgetEditor.libraryPage(views.get(next)).catch(error=>toast(error.message));if(page==='ai')window.VDGWidgetAI.mount(views.get(next));}
 const bar=document.querySelector('.studio-subnav');bar.hidden=section==='home'||section==='guidebook';
 const sameSection=bar.dataset.section===section;
 if(!sameSection){bar.innerHTML='<span class="studio-subnav-indicator" aria-hidden="true"></span>'+pages.map(([p,label])=>`<a href="#${section}/${p}" class="local-link"><span class="subsection-label">${label}</span></a>`).join('');bar.dataset.section=section;}
 bar.querySelectorAll('.local-link').forEach(a=>{const active=a.hash===`#${section}/${page}`;a.classList.toggle('active',active);active?a.setAttribute('aria-current','page'):a.removeAttribute('aria-current');});
 updateSubnavIndicator(!sameSection);
 document.querySelectorAll('.global-link').forEach(a=>{const active=a.hash.startsWith(`#${section}/`);a.classList.toggle('active',active);active?a.setAttribute('aria-current','page'):a.removeAttribute('aria-current');});
 title.textContent=section==='guidebook'?'Гайдбук':pages.find(p=>p[0]===page)[1];
 by('studioDescription').textContent=section==='home'?'Твой рабочий экран: донаты, цель и нужные тебе инструменты.':'';
 by('studioActions').innerHTML=section==='home'?window.VDGDashboard.actions():'';
 by('ttsPanel').classList.toggle('active',section==='tts'||(section==='home'&&homeNeedsSpeech()));
 by('integrationsPanel').classList.toggle('active',section==='integrations');
 by('topDonorsView').classList.toggle('active',next==='donations/top');
 if(next==='donations/top')setDonationView('topDonorsView');
 if(next==='donations/history')setDonationView('historyDonationsView');
 if(section==='tts'){refreshTTSAll(false).catch(()=>{});if(page==='logs')refreshTTSLogs().catch(()=>{});}
 if(section==='integrations'&&['services','streamerbot'].includes(page)&&typeof refreshIntegrations==='function'){setIntegrationRoute(page);refreshIntegrations(true).catch(()=>{});}
 document.title=`${title.textContent} — VicDonationGoal 1.5`;
 closeMenus();window.scrollTo({top:0});
 if(!matchMedia('(prefers-reduced-motion: reduce)').matches)views.get(next).animate([{opacity:0,transform:'translateY(5px)'},{opacity:1,transform:'none'}],{duration:210,easing:'cubic-bezier(.16,1,.3,1)'});
}
function updateSubnavIndicator(instant=false){const bar=document.querySelector('.studio-subnav'),active=bar.querySelector('.local-link.active'),marker=bar.querySelector('.studio-subnav-indicator');if(!active||!marker||bar.hidden)return;marker.style.transition=instant?'none':'';marker.style.width=active.offsetWidth+'px';marker.style.height=active.offsetHeight+'px';marker.style.transform=`translate(${active.offsetLeft}px,${active.offsetTop}px)`;if(instant){marker.getBoundingClientRect();requestAnimationFrame(()=>{marker.style.transition='';});}}
addEventListener('hashchange',navigate);
addEventListener('resize',()=>updateSubnavIndicator(true));
function closeMenus(){document.querySelectorAll('.nav-group.open').forEach(el=>{el.classList.remove('open');el.querySelector('.quick-menu').inert=true;el.querySelector('.menu-toggle').setAttribute('aria-expanded','false');});}
document.querySelectorAll('.nav-group').forEach(group=>{const toggle=group.querySelector('.menu-toggle'),menu=group.querySelector('.quick-menu');if(!toggle)return;const open=()=>{closeMenus();group.classList.add('open');menu.inert=false;toggle.setAttribute('aria-expanded','true');};toggle.onclick=()=>group.classList.contains('open')?closeMenus():open();group.addEventListener('pointerenter',e=>{if(e.pointerType==='mouse')open();});group.addEventListener('pointerleave',()=>{if(!group.contains(document.activeElement))closeMenus();});group.addEventListener('focusout',()=>setTimeout(()=>{if(!group.contains(document.activeElement))closeMenus();},0));});
document.addEventListener('keydown',e=>{if(e.key==='Escape'){closeMenus();selected=null;renderDetail();}});
document.addEventListener('click',e=>{if(!e.target.closest('.nav-group'))closeMenus();const action=e.target.closest('[data-studio-tts]');if(action)by(action.dataset.studioTts)?.click();const service=e.target.closest('[data-studio-service]');if(service)loadIntegrationDetail(service.dataset.studioService).catch(error=>toast(error.message));const record=e.target.closest('[data-studio-record]');if(record){selected=selected===record.dataset.studioRecord?null:record.dataset.studioRecord;renderDetail();}if(e.target.closest('[data-close-detail]')){selected=null;renderDetail();}});
by('eventsTableBody').addEventListener('click',e=>{if(e.target.closest('button,input,label,a'))return;e.target.closest('.donation-entry')?.querySelector('[data-action="expand"]')?.click();});
by('studioDonationDetail').addEventListener('change',async event=>{if(!event.target.matches('[data-studio-top],[data-studio-goal]'))return;const input=event.target,key=selected;input.disabled=true;try{const result=await updateDonation(key,{[input.matches('[data-studio-goal]')?'includeInGoal':'includeInTop']:input.checked});if(!result?.ok)throw Error('Не удалось сохранить');homeTop=null;refreshHomeTop();renderDetail();}catch(error){input.checked=!input.checked;by('studioDonationDetail').querySelector('[data-studio-top-status]').textContent='Не удалось сохранить. Попробуй ещё раз.';}finally{input.disabled=false;}});
function renderDetail(){document.querySelectorAll('[data-studio-record]').forEach(el=>el.setAttribute('aria-expanded',String(el.dataset.studioRecord===selected)));const pane=by('studioDonationDetail');const d=cachedDonations.find(d=>String(d.uniqueKey)===selected);pane.hidden=!d;if(!d)return;pane.innerHTML=`<button class="secondary" data-close-detail aria-label="Закрыть подробности">Закрыть</button><h2>${esc(d.username||'Аноним')}</h2><p>${esc(money(d.amount,d.currency))}</p><span class="source-pill ${esc(d.source)}">${esc(sourceName(d.source))}</span><p class="studio-full-message">${esc(d.message||'Без сообщения')}</p><p class="muted">${esc(formatDate(d.receivedAt||d.createdAt))}</p><label class="compact-flag"><input type="checkbox" data-studio-goal ${d.includeInGoal?'checked':''}> Учитывать в сборе</label><label class="compact-flag"><input type="checkbox" data-studio-top ${d.includeInTop?'checked':''}> Учитывать в TopDonation</label><p data-studio-top-status role="status"></p><a href="#donations/history" data-close-detail>Открыть историю и действия</a>`;}
function safeTime(value){const date=new Date(value);return Number.isFinite(date.getTime())?new Intl.DateTimeFormat('ru-RU',{hour:'2-digit',minute:'2-digit'}).format(date):'—';}
function updateLive(){
 const rows=[...cachedDonations].slice(-8).reverse();const signature=JSON.stringify(rows);
 if(signature!==latestSignature||!by('studioLatest')?.children.length){latestSignature=signature;by('studioLatest').innerHTML=rows.length?rows.map(d=>`<button class="feed-row" data-studio-record="${esc(d.uniqueKey)}" aria-expanded="${selected===String(d.uniqueKey)}"><span class="feed-time">${esc(safeTime(d.receivedAt||d.createdAt))}</span><span class="feed-body"><span class="feed-top"><strong>${esc(d.username||'Аноним')}</strong><span class="source-pill ${esc(d.source)}">${esc(sourceName(d.source))}</span></span><span class="feed-message">${esc(d.message||'Без сообщения')}</span></span><strong class="feed-amount">${esc(money(d.amount,d.currency))}${d.currency!==cachedState?.currency?`<small>${esc(money(d.amountForGoal,cachedState?.currency||'RUB'))}</small>`:''}</strong></button>`).join(''):'<div class="empty-cell">Донатов пока нет. Здесь появятся новые поступления.</div>';}
 if(status){const integrations=(status.integrations?.integrations||[]).filter(i=>i.enabled&&i.category!=='tools');const sb=(status.systemModules||[]).find(i=>i.id==='streamerbot');const items=[...integrations,...(sb?[sb]:[])];live.connections.innerHTML=`<h2>Подключения</h2><div class="status-rows">${items.map(i=>`<a class="status-row" href="#integrations/${i.id==='streamerbot'?'streamerbot':'services'}"><span><i class="dot ${i.commonState==='connected'?'':i.commonState==='disabled'?'off':'warn'}"></i>${esc(i.shortName||i.name)}</span><small>${esc(statusStateLabel(i.commonState||i.state))}</small></a>`).join('')||'<span class="muted">Сервисы не включены</span>'}</div>`;}
 else live.connections.innerHTML='<h2>Подключения</h2><span class="muted">Ожидание состояния сервисов…</span>';
 const t=ttsBootstrap;by('studioSpeech').innerHTML=`<p>В очереди: ${esc(Array.isArray(t.queue)?t.queue.length:0)}</p><p class="muted">${esc(t.control?.paused?'Озвучка на паузе':t.status?.lastError||'Управление озвучкой доступно в разделе «Озвучка».')}</p>`;
 const homeRanking=homeTop||cachedTop;const top=homeRanking?.ranking||[];by('studioTop').innerHTML=top.slice(0,5).map((d,i)=>`<div class="studio-top-row"><span>${i+1}. ${esc(d.displayName||d.username||d.name||'Аноним')}</span><strong>${esc(money(d.totalAmount??d.total??0,homeRanking.currency||'RUB'))}</strong></div>`).join('')||'<div class="empty-cell">Нет донатеров для отображения</div>';
 const current=Number(cachedState?.current)||0, all=cachedDonations.reduce((sum,d)=>sum+(Number(d.amountForGoal)||0),0), excluded=cachedDonations.reduce((sum,d)=>sum+(d.includeInGoal?0:Number(d.amountForGoal)||0),0), currency=cachedState?.currency||'RUB';
 by('studioDonationSummary').innerHTML=[['В сборе',money(current,currency)],['Всего учтено',money(all,currency)],['Не в сборе',money(excluded,currency)],['Донатов',cachedDonations.length]].map(([label,value])=>`<div><span>${esc(label)}</span><strong>${esc(value)}</strong></div>`).join('');
 by('studioRecentSpeech').innerHTML=[...ttsHistory].slice(-5).reverse().map(job=>`<a class="studio-recent-speech" href="#tts/history"><span><strong>${esc(job.username||'Без имени')}</strong><small>${esc(statusLabel(job.status))}</small></span><p>${esc(job.cleanedText||job.originalText||'Без текста')}</p></a>`).join('')||'<div class="empty-cell">История озвучки пока пуста</div>';
 by('studioServiceDetails').innerHTML=(status?.integrations?.integrations||[]).filter(i=>i.enabled&&i.category!=='tools').map(i=>`<a class="studio-service-detail" href="#integrations/services" data-studio-service="${esc(i.id)}"><span><i class="dot ${i.commonState==='connected'?'':i.commonState==='disabled'?'off':'warn'}"></i><strong>${esc(i.shortName||i.name)}</strong><small>${esc(statusStateLabel(i.commonState||i.state))}</small></span><p>${esc(i.status?.lastError||i.status?.last_error||i.status?.lastEvent||i.description||'Настройки и состояние подключения')}</p></a>`).join('')||'<div class="empty-cell">Сервисы не включены. Подключи их в разделе «Интеграции».</div>';
 if(selected)renderDetail();
 const core=by('studioCore');const fresh=statusAt&&Date.now()-statusAt<13000;core.innerHTML=`<i class="dot ${fresh?'':'off'}"></i><span>${fresh?'Core работает':'Нет связи с Core'}</span>`;
}
addEventListener('vdg:data',updateLive);
addEventListener('vdg:status',e=>{status=e.detail;statusAt=Date.now();updateLive();});
function clock(){by('studioClock').textContent=new Intl.DateTimeFormat('ru-RU',{timeZone:'Europe/Moscow',hour:'2-digit',minute:'2-digit',second:'2-digit'}).format(new Date())+' МСК';by('studioClock').dateTime=new Date().toISOString();}
clock();setInterval(clock,1000);setInterval(updateLive,3000);
async function refreshHomeTop(){if(!homeTopLoading&&section==='home'&&window.VDGDashboard.get().widgets.some(w=>w.id==='top')){homeTopLoading=true;try{homeTop=await getJson('/api/donors/top');updateLive();}catch{}finally{homeTopLoading=false;}}}
setInterval(refreshHomeTop,5000);
window.VDGDashboard.ready.then(()=>{if(section==='home')mountDashboard();});
navigate();refreshTop(true).catch(()=>{});
})();
