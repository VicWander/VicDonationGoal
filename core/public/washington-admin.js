(() => {
  const parent = document.getElementById('integrationsPanel');
  if (!parent) return;
  const card = document.createElement('section');
  card.className = 'card';
  card.innerHTML = `<div class="card-title"><h2>Washington</h2><span id="washState" class="badge-soft">Загрузка…</span></div>
    <p>Короткие реакции кота на новые донаты в Twitch. Обычный алерт и TTS работают независимо.</p>
    <form id="washForm">
      <label class="checkbox-line"><input name="enabled" type="checkbox">Включить реакции</label>
      <label>Адрес Washington Service<input name="url" type="url" required></label>
      <div class="form-row"><label>Минимальная сумма в валюте цели<input name="minimumAmount" type="number" min="0" step="0.01" required></label>
      <label>Вероятность, %<input name="chance" type="number" min="0" max="100" required></label></div>
      <div class="form-row"><label>Пауза между реакциями, сек.<input name="cooldownSeconds" type="number" min="0" max="3600" required></label>
      <label>Крупный донат от (0 — отключить)<input name="largeAmount" type="number" min="0" step="0.01" required></label>
      <label>Вероятность для крупного, %<input name="largeChance" type="number" min="0" max="100" required></label></div>
      <label>Источники</label><div id="washSources" class="form-row"></div>
      <label class="checkbox-line"><input name="manual" type="checkbox">Реагировать на ручные донаты</label>
      <details><summary>Время реакции</summary><label>Ожидать передачу алерта в Streamer.bot, сек. (0 — не ждать)<input name="afterAlertWaitSeconds" type="number" min="0" max="120" required></label>
      <label>Дополнительная задержка, сек.<input name="delaySeconds" type="number" min="0" max="60" required></label>
      <p>Если алерт не передан за указанное время, реакция пропускается. Передача не означает окончание анимации.</p></details>
      <div class="form-row"><button type="submit">Сохранить</button><button type="button" class="secondary" id="washCheck">Проверить связь</button>
      <button type="button" class="secondary" id="washTest">Тест → сообщение в Twitch</button></div>
      <p>Тест использует сохранённые настройки, обходит шанс и паузу. Донат в историю не добавляется.</p>
    </form><div id="washResult" role="status"></div>`;
  parent.append(card);
  const form = card.querySelector('form');
  let saved;
  const result = card.querySelector('#washResult');
  async function request(path, body) {
    const response = await fetch('/api/washington' + path, body === undefined ? {} : {
      method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)
    });
    const data = await response.json();
    if (!response.ok || data.ok === false) throw Error(data.message || 'Ошибка запроса');
    return data;
  }
  function status(s) {
    card.querySelector('#washState').textContent = ({connected:'Подключено',offline:'Нет связи',disabled:'Выключено',not_ready:'Washington доступен, отправка не настроена'})[s.state] || s.state;
    result.textContent = [s.lastEvent, s.lastError, s.washington?.lastResult].filter(Boolean).join(' · ');
  }
  request('').then(data => {
    saved = data.config;
    for (const [key,value] of Object.entries(saved)) {
      const field = form.elements.namedItem(key);
      if (field) field.type === 'checkbox' ? field.checked = value : field.value = value;
    }
    const sources = new Set([...(data.sources || []).filter(s=>s.automatic).map(s=>s.id),...saved.sources]);
    for (const source of sources) {
      const label = document.createElement('label'); label.className='checkbox-line';
      const input=document.createElement('input'); input.type='checkbox';input.value=source;input.checked=saved.sources.includes(source);input.name='source';
      label.append(input,document.createTextNode(source));card.querySelector('#washSources').append(label);
    }
    status(data.status);
  }).catch(e => result.textContent=e.message);
  form.addEventListener('submit', async event => {
    event.preventDefault(); if (!saved) return;
    const config={...saved};
    for (const key of Object.keys(saved)) {
      const field=form.elements.namedItem(key);if (!field) continue;
      config[key]=field.type==='checkbox' ? field.checked : field.type==='number' ? Number(field.value) : field.value;
    }
    config.sources=[...form.querySelectorAll('[name=source]:checked')].map(x=>x.value);
    try {saved=(await request('/config',config)).config;result.textContent='Сохранено';}
    catch(e){result.textContent=e.message;}
  });
  for(const [id,path] of [['washCheck','/check'],['washTest','/test']]) {
    card.querySelector('#'+id).addEventListener('click',async event=>{
      event.target.disabled=true;
      try {const data=await request(path,{});if(data.status)status(data.status);else result.textContent=data.message;}
      catch(e){result.textContent=e.message;}finally{event.target.disabled=false;}
    });
  }
})();
