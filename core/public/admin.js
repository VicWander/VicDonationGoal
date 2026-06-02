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

const saveGoalButton = document.getElementById("saveGoalButton");
const addDonationButton = document.getElementById("addDonationButton");
const undoButton = document.getElementById("undoButton");
const resetButton = document.getElementById("resetButton");

const searchInput = document.getElementById("searchInput");
const sourceFilter = document.getElementById("sourceFilter");
const goalFilter = document.getElementById("goalFilter");
const eventsTableBody = document.getElementById("eventsTableBody");
const eventsCount = document.getElementById("eventsCount");

const statusList = document.getElementById("statusList");
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

function niceNumber(value) {
  const number = Number(value) || 0;
  return number.toLocaleString("ru-RU", {
    maximumFractionDigits: Number.isInteger(number) ? 0 : 2
  });
}

function money(value, currency = "RUB") {
  return `${niceNumber(value)} ${currency}`;
}

function normalizeCurrency(value) {
  return String(value || "RUB").trim().toUpperCase();
}

function percentOf(current, goal) {
  const c = Number(current) || 0;
  const g = Number(goal) || 1;
  return Math.min((c / g) * 100, 100);
}

function escapeHtml(text) {
  return String(text ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

async function getJson(url) {
  const response = await fetch(url + "?t=" + Date.now());
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return await response.json();
}

async function postJson(url, data = {}) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data)
  });
  const result = await response.json();
  if (!response.ok) alert(result.message || "Ошибка");
  return result;
}

function sourceName(source) {
  if (source === "donationalerts") return "DA";
  if (source === "donatty") return "Donatty";
  if (source === "manual") return "Manual";
  return source || "Unknown";
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
    const haystack = [d.username, d.message, d.amount, d.currency, d.source, d.receivedAt, d.createdAt]
      .map(v => String(v ?? "").toLowerCase())
      .join(" ");
    return haystack.includes(q);
  });
}

function amountCellHtml(d) {
  const originalCurrency = normalizeCurrency(d.currency);
  const goalCurrency = normalizeCurrency(cachedState?.currency);
  const main = escapeHtml(money(d.amount, d.currency || "RUB"));

  if (goalCurrency && originalCurrency !== goalCurrency) {
    return `${main}<div class="amount-converted">→ ${escapeHtml(money(d.amountForGoal, goalCurrency))}</div>`;
  }

  return main;
}

function renderTable() {
  const list = [...getFilteredDonations()].reverse();
  eventsCount.textContent = `${list.length} из ${cachedDonations.length} событий`;

  if (list.length === 0) {
    eventsTableBody.innerHTML = `<tr><td colspan="8" class="empty-cell">Ничего не найдено</td></tr>`;
    return;
  }

  eventsTableBody.innerHTML = list.map((d) => {
    const key = escapeHtml(d.uniqueKey);
    const source = escapeHtml(d.source || "unknown");
    const username = escapeHtml(d.username || "Аноним");
    const message = escapeHtml(d.message || "");
    const date = escapeHtml(formatDate(d.receivedAt || d.createdAt));
    const checked = d.includeInGoal ? "checked" : "";
    const notifyChecked = d.notifyStreamerBot ? "checked" : "";

    return `
      <tr data-key="${key}">
        <td class="date-cell">${date}</td>
        <td><span class="source-pill ${source}">${sourceName(d.source)}</span></td>
        <td>${username}</td>
        <td class="amount-cell">${amountCellHtml(d)}</td>
        <td><label class="goal-toggle"><input type="checkbox" data-action="toggle" ${checked}></label></td>
        <td><label class="goal-toggle notify-toggle"><input type="checkbox" data-action="toggle-notify" ${notifyChecked}></label></td>
        <td class="message-cell" title="${message}">${message || "—"}</td>
        <td>
          <div class="actions">
            <button class="icon-button secondary" data-action="replay">Повт.</button>
            <button class="icon-button secondary" data-action="edit">Изм.</button>
            <button class="icon-button danger" data-action="delete">Удал.</button>
          </div>
        </td>
      </tr>
    `;
  }).join("");
}

function statusItem(title, mode, text, detail = "") {
  return `
    <div class="status-item ${mode}">
      <span class="status-dot ${mode}"></span>
      <div>
        <b>${escapeHtml(title)}</b>
        <p>${escapeHtml(text)}</p>
        ${detail ? `<small>${escapeHtml(detail)}</small>` : ""}
      </div>
    </div>
  `;
}

function renderStatuses(status) {
  const da = status.donationAlerts || {};
  const donatty = status.donatty || {};
  const sb = status.streamerbot || {};

  const daMode = da.connected ? "ok" : (da.configured || da.authorized ? "warn" : "off");
  const daText = da.connected
    ? "подключен"
    : da.authorized
      ? "авторизован, но не подключен"
      : da.configured
        ? "нужна авторизация"
        : "не настроен";

  const donattyMode = donatty.connected && !donatty.stale ? "ok" : (donatty.running && !donatty.stale ? "warn" : "off");
  const donattyText = donatty.connected && !donatty.stale
    ? "слушает SSE"
    : donatty.stale
      ? "нет свежего heartbeat"
      : donatty.lastError || donatty.status || "не запущен";

  const sbMode = sb.running && !sb.stale ? "ok" : (sb.lastError ? "warn" : "off");
  const sbText = sb.running && !sb.stale
    ? "bridge работает"
    : sb.stale
      ? "bridge не отвечает"
      : sb.lastError || sb.status || "не запущен";

  statusList.innerHTML = [
    statusItem("Локальный сервер", "ok", "работает", status.server?.time || ""),
    statusItem("DonationAlerts", daMode, daText, da.last_error || da.channel || ""),
    statusItem("Donatty", donattyMode, donattyText, donatty.lastError || donatty.lastEvent || ""),
    statusItem("Streamer.bot", sbMode, sbText, sb.lastError || sb.lastEvent || "")
  ].join("");
}

async function refreshStatuses() {
  if (!statusList) return;
  try {
    const status = await getJson("/api/status");
    renderStatuses(status);
  } catch (error) {
    statusList.innerHTML = statusItem("Статусы", "off", "не удалось получить", String(error));
  }
}

function renderRates(rates) {
  cachedRates = rates;
  const table = rates?.ratesToRUB || {};

  rateUSDInput.value = table.USD ?? 90;
  rateEURInput.value = table.EUR ?? 100;
  rateKZTInput.value = table.KZT ?? 0.18;

  const extra = {};
  for (const [currency, value] of Object.entries(table)) {
    if (!["RUB", "USD", "EUR", "KZT"].includes(currency)) {
      extra[currency] = value;
    }
  }

  extraRatesInput.value = Object.keys(extra).length ? JSON.stringify(extra) : "";
}

async function refreshRates() {
  try {
    const rates = await getJson("/api/rates");
    renderRates(rates);
  } catch (error) {
    console.error("Не удалось загрузить курсы", error);
  }
}

async function saveRates() {
  let extra = {};
  const extraText = extraRatesInput.value.trim();

  if (extraText) {
    try {
      extra = JSON.parse(extraText);
    } catch (error) {
      alert("Доп. курсы должны быть валидным JSON, например: {\"UAH\":2.2}");
      return;
    }
  }

  const ratesToRUB = {
    RUB: 1,
    USD: Number(rateUSDInput.value),
    EUR: Number(rateEURInput.value),
    KZT: Number(rateKZTInput.value),
    ...extra
  };

  await postJson("/api/rates", {
    baseCurrency: "RUB",
    ratesToRUB
  });

  inputsFilledOnce = false;
  await refreshRates();
  await refreshAll();
}

async function refreshAll() {
  try {
    const [state, donations] = await Promise.all([
      getJson("/api/state"),
      getJson("/api/donations")
    ]);
    cachedState = state;
    cachedDonations = Array.isArray(donations) ? donations : [];
    renderState(state, cachedDonations);
    renderTable();
  } catch (error) {
    console.error("Не удалось обновить админку", error);
  }
}

async function updateDonation(uniqueKey, patch) {
  await postJson("/api/donation/update", { uniqueKey, ...patch });
  await refreshAll();
}

async function deleteDonation(uniqueKey) {
  await postJson("/api/donation/delete", { uniqueKey });
  await refreshAll();
}

async function replayDonation(uniqueKey) {
  await postJson("/api/donation/replay", { uniqueKey });
  await refreshAll();
  await refreshStatuses();
}

saveGoalButton.addEventListener("click", async () => {
  await postJson("/api/set-goal", {
    title: titleInput.value,
    baseAmount: Number(baseAmountInput.value),
    goal: Number(goalInput.value),
    currency: currencyInput.value
  });
  inputsFilledOnce = false;
  await refreshAll();
});

addDonationButton.addEventListener("click", async () => {
  await postJson("/api/donation", {
    source: "manual",
    externalId: crypto.randomUUID(),
    username: usernameInput.value,
    amount: Number(amountInput.value),
    currency: donationCurrencyInput.value,
    message: messageInput.value,
    includeInGoal: includeInput.checked,
    notifyStreamerBot: notifyInput.checked
  });
  await refreshAll();
});

undoButton.addEventListener("click", async () => {
  if (!confirm("Удалить последний донат из истории?")) return;
  await postJson("/api/undo-last");
  await refreshAll();
});

resetButton.addEventListener("click", async () => {
  if (!confirm("Сбросить текущий сбор? История останется, но все старые донаты станут 'не в сборе'.")) return;
  await postJson("/api/reset");
  inputsFilledOnce = false;
  await refreshAll();
});

saveRatesButton.addEventListener("click", saveRates);
refreshStatusButton.addEventListener("click", refreshStatuses);

for (const el of [searchInput, sourceFilter, goalFilter]) {
  el.addEventListener("input", renderTable);
  el.addEventListener("change", renderTable);
}

eventsTableBody.addEventListener("change", async (event) => {
  const target = event.target;
  const row = target.closest("tr[data-key]");
  if (!row) return;

  if (target.dataset.action === "toggle") {
    await updateDonation(row.dataset.key, { includeInGoal: target.checked });
    return;
  }

  if (target.dataset.action === "toggle-notify") {
    await updateDonation(row.dataset.key, { notifyStreamerBot: target.checked });
    return;
  }
});

eventsTableBody.addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-action]");
  if (!button) return;
  const row = button.closest("tr[data-key]");
  if (!row) return;

  const uniqueKey = row.dataset.key;
  const donation = cachedDonations.find(d => d.uniqueKey === uniqueKey);
  if (!donation) return;

  if (button.dataset.action === "replay") {
    if (!confirm("Повторить оповещение этого доната в Streamer.bot?")) return;
    await replayDonation(uniqueKey);
    return;
  }

  if (button.dataset.action === "delete") {
    if (!confirm("Удалить этот донат из истории?")) return;
    await deleteDonation(uniqueKey);
    return;
  }

  if (button.dataset.action === "edit") {
    const username = prompt("Имя", donation.username || "Аноним");
    if (username === null) return;
    const amount = prompt("Сумма", donation.amount);
    if (amount === null) return;
    const currency = prompt("Валюта", donation.currency || "RUB");
    if (currency === null) return;
    const message = prompt("Сообщение", donation.message || "");
    if (message === null) return;

    await updateDonation(uniqueKey, {
      username,
      amount: Number(String(amount).replace(",", ".")),
      currency,
      message
    });
  }
});

refreshRates();
refreshStatuses();
refreshAll();
setInterval(refreshAll, 1500);
setInterval(refreshStatuses, 4000);
