const goalTitlePreview = document.getElementById("goalTitlePreview");
const goalNumbersPreview = document.getElementById("goalNumbersPreview");
const progressText = document.getElementById("progressText");
const progressFill = document.getElementById("progressFill");
const currentPreview = document.getElementById("currentPreview");
const totalAllPreview = document.getElementById("totalAllPreview");
const notIncludedPreview = document.getElementById("notIncludedPreview");
const goalPreview = document.getElementById("goalPreview");
const leftPreview = document.getElementById("leftPreview");
const countPreview = document.getElementById("countPreview");

const titleInput = document.getElementById("titleInput");
const baseAmountInput = document.getElementById("baseAmountInput");
const goalInput = document.getElementById("goalInput");
const currencyInput = document.getElementById("currencyInput");

const usernameInput = document.getElementById("usernameInput");
const amountInput = document.getElementById("amountInput");
const donationCurrencyInput = document.getElementById("donationCurrencyInput");
const messageInput = document.getElementById("messageInput");
const includeInput = document.getElementById("includeInput");
const notifyInput = document.getElementById("notifyInput");
const eventInput = document.getElementById("eventInput");
const speakInput = document.getElementById("speakInput");
const includeTopInput = document.getElementById("includeTopInput");

const saveGoalButton = document.getElementById("saveGoalButton");
const addDonationButton = document.getElementById("addDonationButton");
const undoButton = document.getElementById("undoButton");
const resetButton = document.getElementById("resetButton");

const searchInput = document.getElementById("searchInput");
const sourceFilter = document.getElementById("sourceFilter");
const goalFilter = document.getElementById("goalFilter");
const eventsTableBody = document.getElementById("eventsTableBody");
const eventsCount = document.getElementById("eventsCount");

const bulkFlagControls = {
  includeInGoal: document.getElementById("bulkGoalToggle"),
  notifyStreamerBot: document.getElementById("bulkNotifyToggle"),
  triggerDonationEvents: document.getElementById("bulkEventToggle"),
  speakTTS: document.getElementById("bulkTtsToggle"),
  includeInTop: document.getElementById("bulkTopToggle")
};

const donationSubtabs = [...document.querySelectorAll(".donation-subtab")];
const donationViews = [...document.querySelectorAll(".donation-view")];
const topDonorsSearch = document.getElementById("topDonorsSearch");
const showExcludedDonors = document.getElementById("showExcludedDonors");
const topDonorsCount = document.getElementById("topDonorsCount");
const topGrandTotal = document.getElementById("topGrandTotal");
const topPinnedCount = document.getElementById("topPinnedCount");
const topRankingCount = document.getElementById("topRankingCount");
const pinnedDonorsSection = document.getElementById("pinnedDonorsSection");
const pinnedDonorsList = document.getElementById("pinnedDonorsList");
const topDonorsList = document.getElementById("topDonorsList");
const excludedDonorsSection = document.getElementById("excludedDonorsSection");
const excludedDonorsList = document.getElementById("excludedDonorsList");

const statusSummary = document.getElementById("statusSummary");
const systemStatusGrid = document.getElementById("systemStatusGrid");
const serviceStatusGrid = document.getElementById("serviceStatusGrid");
const servicesStatusSummary = document.getElementById("servicesStatusSummary");
const statusDisabledList = document.getElementById("statusDisabledList");
const toggleStatusDetailsButton = document.getElementById("toggleStatusDetailsButton");
const createDiagnosticButton = document.getElementById("createDiagnosticButton");
const refreshStatusButton = document.getElementById("refreshStatusButton");
const rateUSDInput = document.getElementById("rateUSDInput");
const rateEURInput = document.getElementById("rateEURInput");
const rateKZTInput = document.getElementById("rateKZTInput");
const extraRatesInput = document.getElementById("extraRatesInput");
const saveRatesButton = document.getElementById("saveRatesButton");

let inputsFilledOnce = false;
let cachedState = null;
let cachedDonations = [];
let cachedRates = null;
let cachedTop = { pinned: [], ranking: [], excluded: [], counts: {}, grandTotal: 0, currency: "RUB" };
let topRefreshTimer = null;
let statusDetailsExpanded = localStorage.getItem("vic-status-details") === "1";
let sourceRegistryCache = {
  donationalerts: { shortName: "DA", name: "DonationAlerts" }, donatty: { shortName: "Donatty", name: "Donatty" },
  manual: { shortName: "Manual", name: "Ручной донат" }, streamelements: { shortName: "SE", name: "StreamElements" },
  streamlabs: { shortName: "Streamlabs", name: "Streamlabs" }, donatepay: { shortName: "DonatePay", name: "DonatePay" },
  donatestream: { shortName: "D.Stream", name: "Donate.Stream" }, donatex: { shortName: "DonateX", name: "DonateX" },
  tribute: { shortName: "Tribute", name: "Tribute" }
};
let openDonationMenuKey = "";
let openDonorMenuId = "";
const expandedDonationRows = new Set();
const expandedDonors = new Set();
const expandedDonorMessages = new Set();
const donorDetailCache = new Map();

function niceNumber(value) {
  const number = Number(value) || 0;
  return number.toLocaleString("ru-RU", { maximumFractionDigits: Number.isInteger(number) ? 0 : 2 });
}
function money(value, currency = "RUB") { return `${niceNumber(value)} ${currency}`; }
function normalizeCurrency(value) { return String(value || "RUB").trim().toUpperCase(); }
function normalizeText(value) { return String(value || "").trim().toLocaleLowerCase("ru-RU"); }
function percentOf(current, goal) { return Math.min(((Number(current) || 0) / (Number(goal) || 1)) * 100, 100); }
function escapeHtml(text) {
  return String(text ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}
async function getJson(url) {
  const response = await fetch(url + (url.includes("?") ? "&" : "?") + "t=" + Date.now(), { cache: "no-store" });
  const result = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(result.message || `HTTP ${response.status}`);
  return result;
}
async function postJson(url, data = {}) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data)
  });
  const result = await response.json().catch(() => ({}));
  if (!response.ok) alert(result.message || `HTTP ${response.status}`);
  return result;
}
function sourceName(source) {
  const id = String(source || "").toLowerCase();
  return sourceRegistryCache[id]?.shortName || source || "Unknown";
}
function pluralRu(value, one, few, many) {
  const number = Math.abs(Number(value) || 0);
  const mod100 = number % 100;
  const mod10 = number % 10;
  if (mod100 >= 11 && mod100 <= 14) return many;
  if (mod10 === 1) return one;
  if (mod10 >= 2 && mod10 <= 4) return few;
  return many;
}
function formatDate(value) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("ru-RU", {
    day: "2-digit", month: "2-digit", year: "2-digit",
    hour: "2-digit", minute: "2-digit", second: "2-digit"
  });
}
function shortText(value, limit = 110) {
  const text = String(value || "").replace(/\s+/g, " ").trim();
  return text.length > limit ? `${text.slice(0, limit - 1)}…` : text || "—";
}

function renderState(state, donations) {
  const current = Number(state.current) || 0;
  const goal = Number(state.goal) || 1;
  const currency = state.currency || "RUB";
  const baseAmount = Number(state.baseAmount) || 0;
  const percent = percentOf(current, goal);
  const left = Math.max(goal - current, 0);
  const totalAll = donations.reduce((sum, d) => sum + (Number(d.amountForGoal) || 0), 0);
  const includedOnly = donations.reduce((sum, d) => sum + (d.includeInGoal ? (Number(d.amountForGoal) || 0) : 0), 0);
  const notIncluded = Math.max(totalAll - includedOnly, 0);

  goalTitlePreview.textContent = state.title || "Сбор на цель";
  goalNumbersPreview.textContent = `${money(current, currency)} / ${money(goal, currency)}`;
  progressText.textContent = `${Math.floor(percent)}%`;
  progressFill.style.width = `${percent}%`;
  currentPreview.textContent = money(current, currency);
  totalAllPreview.textContent = money(totalAll, currency);
  notIncludedPreview.textContent = money(notIncluded, currency);
  goalPreview.textContent = money(goal, currency);
  leftPreview.textContent = money(left, currency);
  countPreview.textContent = donations.length;

  if (!inputsFilledOnce) {
    titleInput.value = state.title || "Сбор на цель";
    baseAmountInput.value = baseAmount;
    goalInput.value = state.goal || 10000;
    currencyInput.value = currency;
    donationCurrencyInput.value = currency;
    inputsFilledOnce = true;
  }
}

function getFilteredDonations() {
  const q = searchInput.value.trim().toLowerCase();
  const src = sourceFilter.value;
  const goal = goalFilter.value;
  return cachedDonations.filter((d) => {
    if (src !== "all" && d.source !== src) return false;
    if (goal === "included" && !d.includeInGoal) return false;
    if (goal === "excluded" && d.includeInGoal) return false;
    if (!q) return true;
    return [d.username, d.message, d.amount, d.currency, d.source, d.receivedAt, d.createdAt]
      .map(v => String(v ?? "").toLowerCase()).join(" ").includes(q);
  });
}
function amountCellHtml(d) {
  const originalCurrency = normalizeCurrency(d.currency);
  const goalCurrency = normalizeCurrency(cachedState?.currency);
  const main = escapeHtml(money(d.amount, d.currency || "RUB"));
  return goalCurrency && originalCurrency !== goalCurrency
    ? `${main}<small class="amount-converted">→ ${escapeHtml(money(d.amountForGoal, goalCurrency))}</small>`
    : main;
}
function flagHtml(label, title, action, checked) {
  return `<label class="compact-flag" title="${escapeHtml(title)}"><span>${escapeHtml(label)}</span><input type="checkbox" data-action="${action}" ${checked ? "checked" : ""}></label>`;
}
function renderTable() {
  const list = [...getFilteredDonations()].reverse();
  eventsCount.textContent = `${list.length} из ${cachedDonations.length} событий`;
  if (!list.length) {
    eventsTableBody.innerHTML = `<div class="empty-cell">Ничего не найдено</div>`;
    updateBulkFlagControls();
    return;
  }

  eventsTableBody.innerHTML = list.map((d) => {
    const rawKey = String(d.uniqueKey || "");
    const key = escapeHtml(rawKey);
    const message = String(d.message || "");
    const canExpand = message.replace(/\s+/g, " ").trim().length > 90;
    const expanded = expandedDonationRows.has(rawKey);
    const menuOpen = openDonationMenuKey === rawKey;
    return `<article class="donation-entry${expanded ? " expanded" : ""}" data-key="${key}">
      <div class="donation-compact-row">
        <div class="donation-date">${escapeHtml(formatDate(d.receivedAt || d.createdAt))}</div>
        <div><span class="source-pill ${escapeHtml(d.source || "unknown")}">${escapeHtml(sourceName(d.source))}</span></div>
        <div class="donation-user" title="${escapeHtml(d.username || "Аноним")}">${escapeHtml(d.username || "Аноним")}</div>
        <div class="donation-amount">${amountCellHtml(d)}</div>
        <div class="donation-flags">
          ${flagHtml("С", "Учитывать в текущем сборе", "toggle", d.includeInGoal)}
          ${flagHtml("О", "Обычное оповещение Streamer.bot", "toggle-notify", d.notifyStreamerBot)}
          ${flagHtml("И", "Донат-ивенты", "toggle-event", d.triggerDonationEvents)}
          ${flagHtml("T", "Озвучка TTS", "toggle-tts", d.speakTTS)}
          ${flagHtml("Топ", "Учитывать в TopDonation", "toggle-top", d.includeInTop)}
        </div>
        <div class="donation-message-preview" title="${escapeHtml(message)}">${escapeHtml(shortText(message, 125))}</div>
        <button type="button" class="message-chevron${canExpand ? "" : " hidden-control"}" data-action="expand" title="${expanded ? "Свернуть текст" : "Развернуть полный текст"}">${expanded ? "⌃" : "⌄"}</button>
        <div class="action-menu-wrap">
          <button type="button" class="more-button" data-action="menu" title="Действия">•••</button>
          <div class="action-menu${menuOpen ? " open" : ""}">
            <button type="button" data-action="replay">Повторить оповещение</button>
            <button type="button" data-action="copy-message">Скопировать сообщение</button>
            <button type="button" data-action="edit">Изменить донат</button>
            <button type="button" class="danger-text" data-action="delete">Удалить донат</button>
          </div>
        </div>
      </div>
      <div class="donation-expanded-message" ${expanded ? "" : "hidden"}>${escapeHtml(message || "Сообщение отсутствует")}</div>
    </article>`;
  }).join("");
  updateBulkFlagControls();
}

function updateBulkFlagControls() {
  const rows = cachedDonations;
  Object.entries(bulkFlagControls).forEach(([field, input]) => {
    if (!input) return;
    input.disabled = !rows.length;
    if (!rows.length) { input.checked = false; input.indeterminate = false; return; }
    const count = rows.filter(item => Boolean(item[field])).length;
    input.checked = count === rows.length;
    input.indeterminate = count > 0 && count < rows.length;
  });
}
async function applyBulkFlag(field, value) {
  if (!cachedDonations.length) return;
  if (field === "includeInGoal" && !value && !confirm("Убрать все донаты из текущего сбора? История сохранится.")) {
    updateBulkFlagControls();
    return;
  }
  const result = await postJson("/api/donations/bulk-update", { field, value });
  if (result.ok) await refreshAll();
}

function setDonationView(viewId) {
  donationSubtabs.forEach(button => button.classList.toggle("active", button.dataset.donationView === viewId));
  donationViews.forEach(view => view.classList.toggle("active", view.id === viewId));
  localStorage.setItem("vic-donation-view", viewId);
  if (viewId === "topDonorsView") refreshTop(true);
}
donationSubtabs.forEach(button => button.addEventListener("click", () => setDonationView(button.dataset.donationView)));

async function refreshTop(force = false) {
  if (!topDonorsList) return;
  const q = topDonorsSearch?.value.trim() || "";
  try {
    cachedTop = await getJson(`/api/donors/top?q=${encodeURIComponent(q)}`);
    renderTop();
    if (force) {
      const detailsToRefresh = [...expandedDonors];
      await Promise.all(detailsToRefresh.map(id => loadDonorDetail(id, true)));
      renderTop();
    }
  } catch (error) {
    topDonorsList.innerHTML = `<div class="empty-cell">Не удалось загрузить TopDonation: ${escapeHtml(error.message)}</div>`;
  }
}
function allTopProfiles() {
  return [...(cachedTop.pinned || []), ...(cachedTop.ranking || []), ...(cachedTop.excluded || [])];
}
function donorCardHtml(item, pinned = false, excluded = false) {
  const id = String(item.id || "");
  const expanded = expandedDonors.has(id);
  const menuOpen = openDonorMenuId === id;
  const detail = donorDetailCache.get(id);
  const rank = pinned ? "★" : excluded ? "—" : `#${item.rank || "?"}`;
  const aliases = (item.aliases || []).map(alias => `${sourceName(alias.source)}: ${alias.username}`).join(", ");
  return `<article class="donor-card${expanded ? " expanded" : ""}${excluded ? " excluded" : ""}" data-donor-id="${escapeHtml(id)}">
    <div class="donor-summary-row">
      <div class="donor-rank">${rank}</div>
      <div class="donor-main"><strong>${escapeHtml(item.displayName)}</strong><small>${escapeHtml(aliases || "Без алиасов")}</small></div>
      <div class="donor-total"><strong>${escapeHtml(money(item.total, item.currency || "RUB"))}</strong><small>${item.donationCount} ${pluralRu(item.donationCount, "донат", "доната", "донатов")}${item.adjustmentCount ? ` + ${item.adjustmentCount} коррект.` : ""}</small></div>
      <div class="donor-last"><span>Последний</span><strong>${escapeHtml(formatDate(item.lastDonationAt))}</strong></div>
      <button type="button" class="message-chevron" data-donor-action="expand" title="${expanded ? "Свернуть" : "Развернуть"}">${expanded ? "⌃" : "⌄"}</button>
      <div class="action-menu-wrap">
        <button type="button" class="more-button" data-donor-action="menu" title="Действия">•••</button>
        <div class="action-menu donor-menu${menuOpen ? " open" : ""}">
          <button type="button" data-donor-action="adjust">Добавить сумму</button>
          <button type="button" data-donor-action="edit-profile">Имя и заметка</button>
          <button type="button" data-donor-action="pin">${item.pinned ? "Открепить" : "Закрепить"}</button>
          <button type="button" data-donor-action="export">Экспорт CSV</button>
          <button type="button" data-donor-action="merge">Объединить с другим</button>
          <button type="button" data-donor-action="exclude">${item.excludedFromTop ? "Вернуть в топ" : "Исключить из топа"}</button>
          <button type="button" class="danger-text" data-donor-action="delete-all">Удалить все донаты</button>
        </div>
      </div>
    </div>
    <div class="donor-detail" ${expanded ? "" : "hidden"}>${renderDonorDetail(detail, item)}</div>
  </article>`;
}
function renderDonorDetail(detail, fallbackSummary) {
  if (!detail) return `<div class="donor-detail-loading">Загрузка истории...</div>`;
  const profile = detail.profile || {};
  const summary = detail.summary || fallbackSummary || {};
  const note = profile.note ? `<div class="donor-note"><b>Заметка:</b> ${escapeHtml(profile.note)}</div>` : "";
  const timeline = detail.timeline || [];
  const rows = timeline.length ? timeline.map(item => {
    const messageId = `${profile.id}:${item.id}`;
    const expanded = expandedDonorMessages.has(messageId);
    const message = String(item.message || "");
    const long = message.replace(/\s+/g, " ").length > 115;
    if (item.type === "adjustment") {
      return `<div class="donor-timeline-item adjustment" data-adjustment-id="${escapeHtml(item.id)}">
        <div class="timeline-date">${escapeHtml(formatDate(item.date))}</div>
        <div class="timeline-source">Корректировка</div>
        <div class="timeline-amount positive">${item.amountForTop >= 0 ? "+" : ""}${escapeHtml(money(item.amountForTop, item.topCurrency || "RUB"))}</div>
        <div class="timeline-message">${escapeHtml(message || "Без комментария")}</div>
        <button class="mini-danger" type="button" data-donor-action="delete-adjustment" data-adjustment-id="${escapeHtml(item.id)}">Удалить</button>
      </div>`;
    }
    return `<div class="donor-timeline-item" data-donation-key="${escapeHtml(item.uniqueKey)}">
      <div class="timeline-date">${escapeHtml(formatDate(item.date))}</div>
      <div class="timeline-source"><span class="source-pill ${escapeHtml(item.source)}">${escapeHtml(sourceName(item.source))}</span></div>
      <div class="timeline-amount">${escapeHtml(money(item.amountForTop, item.topCurrency || "RUB"))}<small>${escapeHtml(money(item.amount, item.currency))}</small></div>
      <div class="timeline-message${expanded ? " expanded" : ""}">${escapeHtml(expanded ? (message || "—") : shortText(message, 135))}</div>
      <label class="compact-flag timeline-top-flag" title="Учитывать этот донат в TopDonation"><span>Топ</span><input type="checkbox" data-donor-action="toggle-donation-top" ${item.includeInTop ? "checked" : ""}></label>
      <button type="button" class="message-chevron mini${long ? "" : " hidden-control"}" data-donor-action="expand-message" data-message-id="${escapeHtml(messageId)}">${expanded ? "⌃" : "⌄"}</button>
    </div>`;
  }).join("") : `<div class="empty-cell">У донатера пока нет записей</div>`;
  return `<div class="donor-detail-summary">
      <div><span>Донаты</span><strong>${escapeHtml(money(summary.donationTotal, summary.currency || "RUB"))}</strong></div>
      <div><span>Корректировки</span><strong>${escapeHtml(money(summary.adjustmentTotal, summary.currency || "RUB"))}</strong></div>
      <div><span>Итого</span><strong>${escapeHtml(money(summary.total, summary.currency || "RUB"))}</strong></div>
      <div><span>Первый донат</span><strong>${escapeHtml(formatDate(summary.firstDonationAt))}</strong></div>
    </div>${note}<div class="donor-timeline">${rows}</div>`;
}
function renderTop() {
  const pinned = cachedTop.pinned || [];
  const ranking = cachedTop.ranking || [];
  const excluded = cachedTop.excluded || [];
  { const count = cachedTop.counts?.totalProfiles || 0; topDonorsCount.textContent = `${count} ${pluralRu(count, "донатер", "донатера", "донатеров")}`; }
  topGrandTotal.textContent = money(cachedTop.grandTotal || 0, cachedTop.currency || "RUB");
  topPinnedCount.textContent = pinned.length;
  topRankingCount.textContent = ranking.length;

  pinnedDonorsSection.hidden = !pinned.length;
  pinnedDonorsList.innerHTML = pinned.map(item => donorCardHtml(item, true, false)).join("");
  topDonorsList.innerHTML = ranking.length ? ranking.map(item => donorCardHtml(item, false, false)).join("") : `<div class="empty-cell">В рейтинге пока никого нет</div>`;
  const showExcluded = Boolean(showExcludedDonors?.checked);
  excludedDonorsSection.hidden = !showExcluded || !excluded.length;
  excludedDonorsList.innerHTML = excluded.map(item => donorCardHtml(item, false, true)).join("");
}
async function loadDonorDetail(id, force = false) {
  if (!force && donorDetailCache.has(id)) return donorDetailCache.get(id);
  const result = await getJson(`/api/donors/detail?id=${encodeURIComponent(id)}`);
  if (result.detail) donorDetailCache.set(id, result.detail);
  return result.detail;
}
function profileFromTop(id) { return allTopProfiles().find(item => String(item.id) === String(id)); }
async function updateDonorProfile(id, patch) {
  const result = await postJson("/api/donors/update", { id, ...patch });
  if (result.ok) { donorDetailCache.delete(id); await refreshTop(); }
}
async function performDonorAction(button, card) {
  const id = card.dataset.donorId;
  const item = profileFromTop(id);
  if (!item) return;
  const action = button.dataset.donorAction;

  if (action === "expand") {
    if (expandedDonors.has(id)) expandedDonors.delete(id); else expandedDonors.add(id);
    if (expandedDonors.has(id)) await loadDonorDetail(id);
    renderTop();
    return;
  }
  if (action === "menu") {
    openDonorMenuId = openDonorMenuId === id ? "" : id;
    renderTop();
    return;
  }
  openDonorMenuId = "";
  if (action === "adjust") {
    const amountRaw = prompt("Сумма корректировки. Можно отрицательное число:", "100");
    if (amountRaw === null) return;
    const amount = Number(String(amountRaw).replace(",", "."));
    if (!Number.isFinite(amount) || amount === 0) return alert("Нужна ненулевая сумма");
    const currency = prompt("Валюта:", "RUB");
    if (currency === null) return;
    const note = prompt("Комментарий к корректировке:", "Перевод напрямую / старый донат");
    if (note === null) return;
    const result = await postJson("/api/donors/adjustment/add", { id, amount, currency, note });
    if (result.ok) { donorDetailCache.delete(id); await refreshTop(true); }
    return;
  }
  if (action === "edit-profile") {
    const displayName = prompt("Отображаемое имя в топе:", item.displayName || "");
    if (displayName === null) return;
    const note = prompt("Личная заметка о донатере:", item.note || "");
    if (note === null) return;
    await updateDonorProfile(id, { displayName, note });
    return;
  }
  if (action === "pin") { await updateDonorProfile(id, { pinned: !item.pinned }); return; }
  if (action === "exclude") { await updateDonorProfile(id, { excludedFromTop: !item.excludedFromTop }); return; }
  if (action === "export") { window.open(`/api/donors/export.csv?id=${encodeURIComponent(id)}`, "_blank"); return; }
  if (action === "merge") {
    const candidates = allTopProfiles().filter(profile => profile.id !== id);
    if (!candidates.length) return alert("Нет другого донатера для объединения");
    const list = candidates.slice(0, 40).map(profile => `${profile.displayName} — ${profile.id}`).join("\n");
    const target = prompt(`С кем объединить «${item.displayName}»?\nВведите имя или ID целевого профиля. Текущий профиль будет присоединён к выбранному.\n\n${list}`, "");
    if (!target) return;
    const targetNorm = normalizeText(target);
    const targetProfile = candidates.find(profile => normalizeText(profile.id) === targetNorm || normalizeText(profile.displayName) === targetNorm);
    if (!targetProfile) return alert("Целевой профиль не найден. Введи точное имя или ID.");
    if (!confirm(`Объединить «${item.displayName}» с «${targetProfile.displayName}»? Исходные донаты сохранятся.`)) return;
    const result = await postJson("/api/donors/merge", { sourceId: id, targetId: targetProfile.id });
    if (result.ok) {
      expandedDonors.delete(id); donorDetailCache.clear(); await refreshAll(); await refreshTop(true);
    }
    return;
  }
  if (action === "delete-all") {
    if (!confirm(`Удалить ВСЕ донаты пользователя «${item.displayName}» из истории и донат-гола? Это действие нельзя отменить.`)) return;
    const check = prompt(`Для подтверждения введи имя донатера: ${item.displayName}`, "");
    if (check !== item.displayName) return alert("Имя не совпало. Удаление отменено.");
    const result = await postJson("/api/donors/delete-all", { id });
    if (result.ok) { donorDetailCache.clear(); await refreshAll(); await refreshTop(true); }
  }
}

function statusMode(commonState) {
  const state = String(commonState || "unknown").toLowerCase();
  if (state === "connected") return "ok";
  if (state === "starting") return "starting";
  if (state === "degraded") return "warn";
  if (state === "error" || state === "stopped") return "error";
  if (state === "disabled" || state === "unconfigured") return "off";
  return "unknown";
}
function statusStateLabel(commonState) {
  const labels = { connected:"Работает", starting:"Подключается", degraded:"Требует внимания", error:"Ошибка", stopped:"Остановлено", disabled:"Выключено", unconfigured:"Не настроено", unknown:"Неизвестно" };
  return labels[String(commonState || "unknown").toLowerCase()] || commonState || "Неизвестно";
}
function statusItem(item, options = {}) {
  const mode = statusMode(item.commonState);
  const detail = options.details ? (item.detail || item.status?.lastError || item.status?.last_error || item.status?.lastEvent || "") : "";
  const stability = item.stability && item.stability !== "stable" ? `<span class="status-maturity ${escapeHtml(item.stability)}">${escapeHtml(item.stability)}</span>` : "";
  const openButton = options.openIntegration ? `<button type="button" class="status-open-button" data-open-integration="${escapeHtml(item.id)}">Открыть</button>` : "";
  return `<div class="status-item ${mode}" data-status-id="${escapeHtml(item.id || "")}">
    <span class="status-dot ${mode}" aria-hidden="true"></span>
    <div class="status-item-main">
      <div class="status-item-title"><b>${escapeHtml(item.name || item.id || "Статус")}</b>${stability}</div>
      <p>${escapeHtml(item.text || statusStateLabel(item.commonState))}</p>
      ${detail ? `<small>${escapeHtml(detail)}</small>` : ""}
    </div>${openButton}
  </div>`;
}
function integrationStatusText(item) {
  const status = item.status || {};
  const state = item.commonState || item.state;
  if (state === "connected") {
    if (String(status.status || "").includes("polling")) return `polling${status.pollIntervalSeconds ? `, ${status.pollIntervalSeconds} сек.` : ""}`;
    return status.status && !["running","connected","subscribed","ready"].includes(String(status.status)) ? status.status : "подключён";
  }
  if (state === "degraded") return status.lastError || status.last_error || status.status || "временная ошибка";
  if (state === "starting") return status.status || "подключается";
  if (state === "error") return status.lastError || status.last_error || "не работает";
  if (state === "unconfigured") return "не настроен";
  if (state === "disabled") return "выключен";
  return status.status || statusStateLabel(state);
}
function renderStatuses(status) {
  for (const source of status.sourceRegistry || []) sourceRegistryCache[source.id] = source;
  const systemModules = status.systemModules || [];
  const integrations = status.integrations?.integrations || [];
  const enabled = integrations.filter(item => item.enabled);
  const connected = enabled.filter(item => item.commonState === "connected");
  const attention = enabled.filter(item => ["degraded","error","stopped","unconfigured"].includes(item.commonState));
  statusSummary.textContent = attention.length ? `${connected.length} работают, ${attention.length} требуют внимания` : `${connected.length} включённых сервисов работают штатно`;
  systemStatusGrid.innerHTML = systemModules.map(item => statusItem(item, { details: statusDetailsExpanded })).join("");

  const severity = { error:0, stopped:1, degraded:2, starting:3, connected:4, disabled:5, unconfigured:6 };
  const visible = integrations.filter(item => item.dashboardVisible !== false && (item.enabled || item.configured));
  visible.sort((a,b) => (severity[a.commonState] ?? 9) - (severity[b.commonState] ?? 9) || (a.order || 999) - (b.order || 999));
  serviceStatusGrid.innerHTML = visible.map(item => statusItem({
    ...item,
    text: integrationStatusText(item),
    detail: item.status?.lastEvent || item.status?.lastError || item.status?.last_error || (item.connected ? "Свежий heartbeat" : "")
  }, { details: statusDetailsExpanded, openIntegration: statusDetailsExpanded })).join("") || `<div class="empty-cell">Подключённые сервисы не найдены.</div>`;

  const disabled = integrations.filter(item => !item.enabled && !visible.includes(item));
  statusDisabledList.hidden = !disabled.length;
  statusDisabledList.innerHTML = disabled.length ? `<span>Выключено или не настроено:</span> ${disabled.map(item => escapeHtml(item.shortName || item.name)).join(", ")}` : "";
  servicesStatusSummary.textContent = `${connected.length} из ${enabled.length} включённых подключены`;
  toggleStatusDetailsButton.textContent = statusDetailsExpanded ? "Скрыть подробности" : "Показать подробности";
  document.body.classList.toggle("status-details-expanded", statusDetailsExpanded);
  populateSourceFilter();
}
async function refreshStatuses() {
  if (!systemStatusGrid || !serviceStatusGrid) return;
  try { renderStatuses(await getJson("/api/status")); }
  catch (error) {
    systemStatusGrid.innerHTML = statusItem({ id:"status-error", name:"Статусы", commonState:"error", text:"не удалось получить", detail:String(error) }, { details:true });
    serviceStatusGrid.innerHTML = "";
  }
}
function populateSourceFilter() {
  if (!sourceFilter) return;
  const current = sourceFilter.value;
  const sources = Object.entries(sourceRegistryCache).sort((a,b) => (a[1].order || 999) - (b[1].order || 999));
  sourceFilter.innerHTML = `<option value="all">Все</option>` + sources.map(([id, meta]) => `<option value="${escapeHtml(id)}">${escapeHtml(meta.name || meta.shortName || id)}</option>`).join("");
  sourceFilter.value = [...sourceFilter.options].some(option => option.value === current) ? current : "all";
}
async function createDiagnosticReport() {
  if (!createDiagnosticButton) return;
  const original = createDiagnosticButton.textContent;
  createDiagnosticButton.disabled = true;
  createDiagnosticButton.textContent = "Создание...";
  try {
    const result = await postJson("/api/diagnostics/create", {});
    if (result.ok) alert(`Диагностический отчёт создан:\n${result.path}`);
  } finally {
    createDiagnosticButton.disabled = false;
    createDiagnosticButton.textContent = original;
  }
}

function renderRates(rates) {
  cachedRates = rates;
  const table = rates?.ratesToRUB || {};
  rateUSDInput.value = table.USD ?? 90;
  rateEURInput.value = table.EUR ?? 100;
  rateKZTInput.value = table.KZT ?? 0.18;
  const extra = {};
  for (const [currency, value] of Object.entries(table)) if (!["RUB", "USD", "EUR", "KZT"].includes(currency)) extra[currency] = value;
  extraRatesInput.value = Object.keys(extra).length ? JSON.stringify(extra) : "";
}
async function refreshRates() {
  try { renderRates(await getJson("/api/rates")); }
  catch (error) { console.error("Не удалось загрузить курсы", error); }
}
async function saveRates() {
  let extra = {};
  const extraText = extraRatesInput.value.trim();
  if (extraText) {
    try { extra = JSON.parse(extraText); }
    catch { return alert('Доп. курсы должны быть валидным JSON, например: {"UAH":2.2}'); }
  }
  await postJson("/api/rates", { baseCurrency: "RUB", ratesToRUB: {
    RUB: 1, USD: Number(rateUSDInput.value), EUR: Number(rateEURInput.value), KZT: Number(rateKZTInput.value), ...extra
  }});
  inputsFilledOnce = false;
  donorDetailCache.clear();
  await refreshRates(); await refreshAll(); await refreshTop(true);
}
async function refreshAll() {
  try {
    const [state, donations] = await Promise.all([getJson("/api/state"), getJson("/api/donations")]);
    cachedState = state;
    cachedDonations = Array.isArray(donations) ? donations : [];
    renderState(state, cachedDonations);
    renderTable();
  } catch (error) { console.error("Не удалось обновить админку", error); }
}
async function updateDonation(uniqueKey, patch) {
  const result = await postJson("/api/donation/update", { uniqueKey, ...patch });
  if (result.ok) { donorDetailCache.clear(); await refreshAll(); if (document.getElementById("topDonorsView")?.classList.contains("active")) await refreshTop(); }
}
async function deleteDonation(uniqueKey) {
  const result = await postJson("/api/donation/delete", { uniqueKey });
  if (result.ok) { donorDetailCache.clear(); await refreshAll(); await refreshTop(); }
}
async function replayDonation(uniqueKey) {
  await postJson("/api/donation/replay", { uniqueKey });
  await refreshAll(); await refreshStatuses();
}

saveGoalButton.addEventListener("click", async () => {
  await postJson("/api/set-goal", { title: titleInput.value, baseAmount: Number(baseAmountInput.value), goal: Number(goalInput.value), currency: currencyInput.value });
  inputsFilledOnce = false; await refreshAll();
});
addDonationButton.addEventListener("click", async () => {
  await postJson("/api/donation", {
    source: "manual", externalId: crypto.randomUUID(), username: usernameInput.value,
    amount: Number(amountInput.value), currency: donationCurrencyInput.value, message: messageInput.value,
    includeInGoal: includeInput.checked, notifyStreamerBot: notifyInput.checked,
    triggerDonationEvents: eventInput.checked, speakTTS: speakInput.checked, includeInTop: includeTopInput.checked
  });
  donorDetailCache.clear(); await refreshAll(); await refreshTop();
});
undoButton.addEventListener("click", async () => {
  if (!confirm("Удалить последний донат из истории?")) return;
  await postJson("/api/undo-last"); donorDetailCache.clear(); await refreshAll(); await refreshTop();
});
resetButton.addEventListener("click", async () => {
  if (!confirm("Сбросить текущий сбор? История и TopDonation сохранятся, но старые донаты перестанут учитываться в текущей цели.")) return;
  await postJson("/api/reset"); inputsFilledOnce = false; await refreshAll();
});
saveRatesButton.addEventListener("click", saveRates);
refreshStatusButton.addEventListener("click", refreshStatuses);
toggleStatusDetailsButton?.addEventListener("click", () => {
  statusDetailsExpanded = !statusDetailsExpanded;
  localStorage.setItem("vic-status-details", statusDetailsExpanded ? "1" : "0");
  refreshStatuses();
});
createDiagnosticButton?.addEventListener("click", createDiagnosticReport);
serviceStatusGrid?.addEventListener("click", async event => {
  const button = event.target.closest("[data-open-integration]");
  if (!button) return;
  const id = button.dataset.openIntegration;
  if (typeof ttsSetPanel === "function") ttsSetPanel("integrationsPanel");
  if (typeof loadIntegrationDetail === "function") await loadIntegrationDetail(id);
});
for (const el of [searchInput, sourceFilter, goalFilter]) {
  el.addEventListener("input", renderTable); el.addEventListener("change", renderTable);
}
Object.entries(bulkFlagControls).forEach(([field, input]) => input?.addEventListener("change", () => applyBulkFlag(field, input.checked)));

let topSearchDebounce = null;
topDonorsSearch?.addEventListener("input", () => {
  clearTimeout(topSearchDebounce);
  topSearchDebounce = setTimeout(() => refreshTop(), 250);
});
showExcludedDonors?.addEventListener("change", renderTop);

eventsTableBody.addEventListener("change", async (event) => {
  const target = event.target;
  const row = target.closest("[data-key]");
  if (!row) return;
  const map = {
    "toggle": "includeInGoal", "toggle-notify": "notifyStreamerBot", "toggle-event": "triggerDonationEvents",
    "toggle-tts": "speakTTS", "toggle-top": "includeInTop"
  };
  const field = map[target.dataset.action];
  if (field) await updateDonation(row.dataset.key, { [field]: target.checked });
});
eventsTableBody.addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-action]");
  if (!button) return;
  const row = button.closest("[data-key]");
  if (!row) return;
  const uniqueKey = row.dataset.key;
  const donation = cachedDonations.find(d => d.uniqueKey === uniqueKey);
  if (!donation) return;
  const action = button.dataset.action;
  if (action === "expand") {
    if (expandedDonationRows.has(uniqueKey)) expandedDonationRows.delete(uniqueKey); else expandedDonationRows.add(uniqueKey);
    renderTable(); return;
  }
  if (action === "menu") { openDonationMenuKey = openDonationMenuKey === uniqueKey ? "" : uniqueKey; renderTable(); return; }
  openDonationMenuKey = "";
  if (action === "replay") {
    if (confirm("Повторить оповещение этого доната в Streamer.bot?")) await replayDonation(uniqueKey);
    return;
  }
  if (action === "copy-message") {
    await navigator.clipboard.writeText(donation.message || "").catch(() => {}); renderTable(); return;
  }
  if (action === "delete") {
    if (confirm("Удалить этот донат из истории?")) { expandedDonationRows.delete(uniqueKey); await deleteDonation(uniqueKey); }
    return;
  }
  if (action === "edit") {
    const username = prompt("Имя", donation.username || "Аноним"); if (username === null) return;
    const amount = prompt("Сумма", donation.amount); if (amount === null) return;
    const currency = prompt("Валюта", donation.currency || "RUB"); if (currency === null) return;
    const message = prompt("Сообщение", donation.message || ""); if (message === null) return;
    await updateDonation(uniqueKey, { username, amount: Number(String(amount).replace(",", ".")), currency, message });
  }
});

for (const container of [pinnedDonorsList, topDonorsList, excludedDonorsList]) {
  container?.addEventListener("click", async event => {
    const button = event.target.closest("button[data-donor-action]");
    const card = event.target.closest("[data-donor-id]");
    if (button && card) await performDonorAction(button, card);
  });
  container?.addEventListener("change", async event => {
    const input = event.target.closest('input[data-donor-action="toggle-donation-top"]');
    const timeline = event.target.closest("[data-donation-key]");
    if (input && timeline) {
      await updateDonation(timeline.dataset.donationKey, { includeInTop: input.checked });
      donorDetailCache.clear(); await refreshTop(true);
    }
  });
}
for (const container of [pinnedDonorsList, topDonorsList, excludedDonorsList]) {
  container?.addEventListener("click", async event => {
    const button = event.target.closest('button[data-donor-action="expand-message"], button[data-donor-action="delete-adjustment"]');
    if (!button) return;
    const card = button.closest("[data-donor-id]");
    if (!card) return;
    const donorId = card.dataset.donorId;
    if (button.dataset.donorAction === "expand-message") {
      const id = button.dataset.messageId;
      if (expandedDonorMessages.has(id)) expandedDonorMessages.delete(id); else expandedDonorMessages.add(id);
      renderTop();
    } else if (button.dataset.donorAction === "delete-adjustment") {
      if (!confirm("Удалить эту корректировку суммы?")) return;
      const result = await postJson("/api/donors/adjustment/delete", { id: button.dataset.adjustmentId });
      if (result.ok) { donorDetailCache.delete(donorId); await refreshTop(true); }
    }
  });
}

document.addEventListener("click", event => {
  if (!event.target.closest(".action-menu-wrap")) {
    if (openDonationMenuKey || openDonorMenuId) {
      openDonationMenuKey = ""; openDonorMenuId = "";
      renderTable(); renderTop();
    }
  }
});

function restoreDonationView() {
  const stored = localStorage.getItem("vic-donation-view");
  if (stored && document.getElementById(stored)) setDonationView(stored);
}

refreshRates();
refreshStatuses();
refreshAll();
refreshTop();
restoreDonationView();
setInterval(refreshAll, 1500);
setInterval(refreshStatuses, 4000);
setInterval(() => {
  if (document.getElementById("topDonorsView")?.classList.contains("active") && !openDonorMenuId) refreshTop();
}, 5000);
