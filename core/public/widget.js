(function () {
  'use strict';
  const goalTitle=document.getElementById('goalTitle'),goalPercent=document.getElementById('goalPercent');
  const goalFill=document.getElementById('goalFill'),currentAmount=document.getElementById('currentAmount');
  const goalAmount=document.getElementById('goalAmount'),lastDonation=document.getElementById('lastDonation');
  const legacy=document.getElementById('legacyWidget'),designed=document.getElementById('designedWidget');
  let renderer=null, revision=null, activeFingerprint=null, lastState=null, connected=false, busy=false;
  function renderLegacy(state) {
    const current=Number(state.current)||0,goal=Number(state.goal)||1,currency=state.currency||'RUB';
    const percent=Math.min(current/goal*100,100);
    const nice=value=>Math.floor(value).toLocaleString('ru-RU');
    goalTitle.textContent=state.title||'Сбор на цель';goalPercent.textContent='';goalFill.style.width=percent+'%';
    currentAmount.textContent=`${nice(current)} / ${nice(goal)} ${currency} (${Math.floor(percent)}%)`;
    goalAmount.textContent='';lastDonation.textContent='';
  }
  async function get(url){const response=await fetch(url+'?t='+Date.now(),{cache:'no-store'});if(!response.ok)throw new Error('HTTP '+response.status);return response.json();}
  function donationKey(state){const d=state&&state.lastDonation;return d?String(d.uniqueKey||d.id||d.externalId||JSON.stringify(d)):'';}
  async function update() {
    if(busy)return;busy=true;
    try {
      const [stateResult,activeResult]=await Promise.allSettled([get('/api/state'),get('/api/widget/active')]);
      let changed=false;
      if(activeResult.status==='fulfilled') {
        const active=activeResult.value;
        if(active.ok!==false&&active.revision!==revision) {
          const fingerprint=JSON.stringify(active.document);
          if(fingerprint!==activeFingerprint&&active.document) {
            if(renderer)renderer.setDocument(active.document);
            else renderer=window.VDGWidgetRenderer.mount(designed,active.document,{animate:true});
            legacy.hidden=true;designed.hidden=false;
          } else if(fingerprint!==activeFingerprint) {if(renderer)renderer.destroy();renderer=null;legacy.hidden=false;designed.hidden=true;}
          changed=fingerprint!==activeFingerprint;activeFingerprint=fingerprint;revision=active.revision;
        }
      }
      if(stateResult.status==='fulfilled') {
        const state=stateResult.value;
        const event=connected&&!changed&&lastState&&donationKey(state)&&donationKey(state)!==donationKey(lastState)?'donation':undefined;
        if(renderer)renderer.update(state,{event:connected&&!changed?(event||'state'):undefined});else renderLegacy(state);
        lastState=state;connected=true;
      } else {connected=false;console.error('Не удалось получить состояние цели',stateResult.reason);}
      if(activeResult.status==='rejected')connected=false;
    } catch(error){connected=false;console.error('Не удалось обновить виджет',error);}
    finally {busy=false;}
  }
  update();const timer=setInterval(update,700);
  window.addEventListener('pagehide',()=>{clearInterval(timer);if(renderer)renderer.destroy();},{once:true});
})();
