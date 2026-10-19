const integrationState = {
  bootstrap: { integrations: [], onboarding: {} },
  selectedId: "",
  detail: null,
  refreshing: false,
  onboardingDraft: null
};

function integrationStatusLabel(item) {
  const state = item?.commonState || item?.state;
  const raw = String(item?.status?.status || "").toLowerCase();
  if (state === "degraded" && raw === "reconnecting") return "Переподключение";
  if (state === "error" && raw === "outage") return "Долгий обрыв";
  if (state === "error" && raw === "authorization_required") return "Нужна авторизация";
  const map = {
    connected: "Подключено", degraded: "Требует внимания", starting: "Подключение",
    unconfigured: "Не настроено", not_configured: "Не настроено", disabled: "Выключено",
    stopped: "Остановлено", error: "Ошибка"
  };
  return map[state] || state || "Неизвестно";
}
function integrationStatusClass(item) {
  const state = item?.commonState || item?.state;
  if (state === "connected") return "ok";
  if (state === "starting") return "running";
  if (state === "degraded") return "warn";
  if (state === "error" || state === "stopped") return "error";
  if (state === "disabled" || state === "unconfigured") return "off";
  return "unknown";
}
function integrationMarkdown(text) {
  let html = escapeHtml(String(text || ""));
  html = html.replace(/^### (.+)$/gm, "<h4>$1</h4>")
    .replace(/^## (.+)$/gm, "<h3>$1</h3>")
    .replace(/^# (.+)$/gm, "<h2>$1</h2>")
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/^\- (.+)$/gm, "<li>$1</li>")
    .replace(/(?:<li>.*<\/li>\n?)+/g, match => `<ul>${match}</ul>`)
    .replace(/\n{2,}/g, "</p><p>")
    .replace(/\n/g, "<br>");
  return `<p>${html}</p>`;
}
function integrationIsPanelActive() {
  return document.getElementById("integrationsPanel")?.classList.contains("active");
}
function integrationResult(message, ok = true, level = "") {
  const box = document.getElementById("integrationActionResult");
  box.hidden = false;
  box.className = `integration-result ${!ok ? "error" : level === "warning" ? "warn" : "ok"}`;
  box.textContent = message || (ok ? "Готово" : "Ошибка");
}
function integrationFormatTime(value) {
  if (!value) return "—";
  const parsed = typeof value === "number" ? new Date(value * 1000) : new Date(String(value).replace(" ", "T"));
  return Number.isNaN(parsed.getTime()) ? String(value) : parsed.toLocaleString("ru-RU");
}
function integrationSelectedSummary() {
  return integrationState.bootstrap.integrations.find(item => item.id === integrationState.selectedId);
}

async function refreshIntegrations(forceDetail = false) {
  if (integrationState.refreshing) return;
  integrationState.refreshing = true;
  try {
    integrationState.bootstrap = await getJson("/api/integrations");
    renderIntegrationBootstrap();
    if (!integrationState.selectedId && integrationState.bootstrap.integrations.length) {
      integrationState.selectedId = integrationState.bootstrap.integrations[0].id;
      forceDetail = true;
    }
    if (integrationState.selectedId && (forceDetail || !integrationState.detail || integrationState.detail.summary?.id !== integrationState.selectedId)) {
      await loadIntegrationDetail(integrationState.selectedId);
    } else if (integrationState.detail) {
      const summary = integrationSelectedSummary();
      if (summary) {
        integrationState.detail.summary = summary;
        renderIntegrationDetail();
      }
    }
  } catch (error) {
    document.getElementById("integrationCards").innerHTML = `<div class="empty-cell">Ошибка: ${escapeHtml(error.message)}</div>`;
  } finally {
    integrationState.refreshing = false;
  }
}

function renderIntegrationBootstrap() {
  const list = integrationState.bootstrap.integrations || [];
  document.getElementById("integrationTotalStat").textContent = list.length;
  document.getElementById("integrationEnabledStat").textContent = list.filter(item => item.enabled).length;
  document.getElementById("integrationConnectedStat").textContent = list.filter(item => item.connected).length;
  document.getElementById("integrationErrorStat").textContent = list.filter(item => ["error","degraded"].includes(item.commonState)).length;
  document.getElementById("integrationListCount").textContent = `${list.length} модулей`;

  document.getElementById("integrationCards").innerHTML = list.map(item => `
    <button type="button" class="integration-card ${item.id === integrationState.selectedId ? "active" : ""}" data-integration-id="${escapeHtml(item.id)}">
      <span class="integration-icon">${escapeHtml(item.icon)}</span>
      <span class="integration-card-main">
        <strong>${escapeHtml(item.name)}${item.stability && item.stability !== "stable" ? ` <span class="integration-maturity ${escapeHtml(item.stability)}">${escapeHtml(item.stability)}</span>` : ""}</strong>
        <small>${escapeHtml(item.description)}</small>
      </span>
      <span class="integration-badge ${integrationStatusClass(item)}">${escapeHtml(integrationStatusLabel(item))}</span>
    </button>
  `).join("") || `<div class="empty-cell">Интеграции не найдены.</div>`;

  const onboarding = integrationState.bootstrap.onboarding || {};
  const onboardingBox = document.getElementById("integrationOnboarding");
  onboardingBox.hidden = Boolean(onboarding.completed);
  if (!onboarding.completed) {
    // The status poll refreshes this panel every four seconds. Keep the user's
    // unfinished choices locally so a background refresh cannot reset them.
    if (!(integrationState.onboardingDraft instanceof Set)) {
      integrationState.onboardingDraft = new Set(onboarding.selected || []);
    }
    const selected = integrationState.onboardingDraft;
    document.getElementById("integrationOnboardingChoices").innerHTML = list.map(item => `
      <label class="integration-choice">
        <input type="checkbox" value="${escapeHtml(item.id)}" ${selected.has(item.id) ? "checked" : ""} />
        <span class="integration-icon">${escapeHtml(item.icon)}</span>
        <span><strong>${escapeHtml(item.name)}</strong><small>${escapeHtml(item.description)}</small></span>
      </label>
    `).join("");
  } else {
    integrationState.onboardingDraft = null;
  }
}

async function loadIntegrationDetail(id) {
  integrationState.selectedId = id;
  integrationState.detail = await getJson(`/api/integrations/detail?id=${encodeURIComponent(id)}`);
  renderIntegrationBootstrap();
  renderIntegrationDetail(true);
  await refreshIntegrationLogs();
}

function renderIntegrationDetail(fillFields = false) {
  const detail = integrationState.detail;
  document.getElementById("integrationEmptyDetail").hidden = Boolean(detail);
  document.getElementById("integrationDetail").hidden = !detail;
  if (!detail) return;
  const summary = detail.summary || {};
  const manifest = detail.manifest || {};
  const config = detail.config || {};
  document.getElementById("integrationDetailIcon").textContent = manifest.icon || "?";
  document.getElementById("integrationDetailName").textContent = manifest.name || summary.name || summary.id;
  document.getElementById("integrationDetailDescription").textContent = manifest.description || "";
  const badge = document.getElementById("integrationDetailBadge");
  badge.textContent = integrationStatusLabel(summary);
  badge.className = `integration-badge ${integrationStatusClass(summary)}`;
  document.getElementById("integrationEnabledInput").checked = Boolean(summary.enabled);
  document.getElementById("integrationStartButton").disabled = !summary.enabled || summary.running;
  document.getElementById("integrationStopButton").disabled = !summary.running;
  document.getElementById("integrationTestButton").textContent = summary.id === "tribute" ? "Проверить донат из Tribute" : "Проверить подключение";
  const authorizeButton = document.getElementById("integrationAuthorizeButton");
  authorizeButton.hidden = !manifest.capabilities?.oauth;
  authorizeButton.dataset.authorizeUrl = manifest.authStartPath || summary.status?.authorizeUrl || "";
  document.getElementById("integrationClearAuthButton").hidden = !manifest.capabilities?.clearAuth;
  document.getElementById("integrationTechnical").textContent = JSON.stringify(summary, null, 2);
  document.getElementById("integrationGuide").innerHTML = integrationMarkdown(detail.guide);
  const connectionSummary = document.getElementById("integrationConnectionSummary");
  if (summary.id === "donationalerts") {
    const status = summary.status || {};
    const api = status.lastApiSuccessAt
      ? "API отвечает"
      : status.authorized
        ? "Авторизованы · API ещё не проверен"
        : "Нужна авторизация";
    const live = status.connected
      ? "Подключён"
      : status.running
        ? "Переподключается"
        : status.lastError
          ? "Требуется действие"
          : "Остановлен";
    const catchUp = status.catchUp || {};
    const catchUpText = catchUp.status === "complete"
      ? `Готово · добавлено ${catchUp.added || 0}`
      : catchUp.status === "baseline_created" || catchUp.status === "baseline_reset"
        ? "Стартовая точка создана"
        : catchUp.status === "limited_window"
          ? `Проверено ограниченное окно · ${catchUp.added || 0}`
          : "Ещё не выполнялся";
    connectionSummary.hidden = false;
    connectionSummary.innerHTML = `
      <div><small>OAuth и API</small><strong>${escapeHtml(api)}</strong></div>
      <div><small>Новые донаты</small><strong>${escapeHtml(live)}</strong></div>
      <div><small>Последнее подключение</small><strong>${escapeHtml(integrationFormatTime(status.lastConnectedAt))}</strong></div>
      <div><small>Догон после обрыва</small><strong>${escapeHtml(catchUpText)}</strong></div>`;
  } else if (summary.id === "tribute") {
    const status = summary.status || {};
    const active = Number(status.testUntil || 0) > Date.now() / 1000;
    const lastTest = status.lastTest;
    connectionSummary.hidden = false;
    connectionSummary.innerHTML = `
      <div><small>Поток донатов</small><strong>${summary.connected && !status.stale ? "Подключён" : "Нет соединения"}</strong></div>
      <div><small>Режим проверки</small><strong>${active ? `До ${escapeHtml(integrationFormatTime(Number(status.testUntil)))}` : "Выключен · донаты учитываются"}</strong>
        ${active ? '<button type="button" id="tributeEndTestButton" class="secondary">Завершить проверку</button>' : ""}</div>
      <div><small>Последняя проверка</small><strong>${lastTest ? escapeHtml(`${lastTest.username} · ${lastTest.amount} ${lastTest.currency}`) : "Ещё не получена"}</strong>
        ${lastTest ? `<small>${lastTest.counted ? "Учёт включён" : "Не добавлено в историю и цель"} · ${escapeHtml(integrationFormatTime(lastTest.receivedAt))}</small>` : ""}</div>
      <div><small>Ожидают передачи в Core</small><strong>${Number(status.pendingCount || 0)}</strong></div>`;
    document.getElementById("tributeEndTestButton")?.addEventListener("click", () => integrationCommand("/api/integrations/test", {cancel:true}));
  } else {
    connectionSummary.hidden = true;
    connectionSummary.innerHTML = "";
  }

  if (fillFields || !document.getElementById("integrationConfigFields").children.length) {
    document.getElementById("integrationConfigFields").innerHTML = (manifest.fields || []).map(field => {
      const key = field.key;
      const value = config[key];
      const help = field.help ? `<small>${escapeHtml(field.help)}</small>` : "";
      if (field.type === "checkbox") {
        return `<label class="checkbox-line integration-config-field"><input type="checkbox" data-config-key="${escapeHtml(key)}" data-config-type="checkbox" ${value ? "checked" : ""} />${escapeHtml(field.label)}${help}</label>`;
      }
      if (field.type === "select") {
        const current = String(value ?? field.default ?? "");
        const options = (field.options || []).map(option => {
          const optionValue = typeof option === "object" ? String(option.value ?? "") : String(option);
          const optionLabel = typeof option === "object" ? String(option.label ?? optionValue) : optionValue;
          return `<option value="${escapeHtml(optionValue)}" ${optionValue === current ? "selected" : ""}>${escapeHtml(optionLabel)}</option>`;
        }).join("");
        return `<label class="integration-config-field">${escapeHtml(field.label)}<select data-config-key="${escapeHtml(key)}" data-config-type="select">${options}</select>${help}</label>`;
      }
      const savedSecret = field.type === "password" && value === "__SET__";
      const placeholder = savedSecret ? "Сохранено — оставьте пустым, чтобы не менять" : (field.placeholder || "");
      return `<label class="integration-config-field">${escapeHtml(field.label)}<input data-config-key="${escapeHtml(key)}" data-config-type="${escapeHtml(field.type || "text")}" type="${field.type === "password" ? "password" : field.type === "number" ? "number" : "text"}" value="${savedSecret ? "" : escapeHtml(value ?? field.default ?? "")}" placeholder="${escapeHtml(placeholder)}" />${help}</label>`;
    }).join("");
  }
}

function collectIntegrationConfig() {
  const config = {};
  document.querySelectorAll("#integrationConfigFields [data-config-key]").forEach(input => {
    const key = input.dataset.configKey;
    if (input.dataset.configType === "checkbox") config[key] = input.checked;
    else if (input.dataset.configType === "number") config[key] = input.value === "" ? null : Number(input.value);
    else config[key] = input.value;
  });
  return config;
}

async function integrationCommand(path, extra = {}) {
  try {
    const result = await postJson(path, { id: integrationState.selectedId, ...extra });
    integrationResult(result.message || "Готово", Boolean(result.ok ?? true), result.level || "");
    await refreshIntegrations(true);
    return result;
  } catch (error) {
    integrationResult(error.message, false);
    return null;
  }
}

async function refreshIntegrationLogs() {
  if (!integrationState.selectedId) return;
  try {
    const result = await getJson(`/api/integrations/logs?id=${encodeURIComponent(integrationState.selectedId)}&limit=300`);
    document.getElementById("integrationLogs").textContent = (result.lines || []).join("\n") || "Логи пока пусты.";
  } catch (error) {
    document.getElementById("integrationLogs").textContent = `Ошибка: ${error.message}`;
  }
}

document.getElementById("integrationCards")?.addEventListener("click", event => {
  const card = event.target.closest("[data-integration-id]");
  if (card) loadIntegrationDetail(card.dataset.integrationId);
});
document.getElementById("integrationOnboardingChoices")?.addEventListener("change", event => {
  const input = event.target.closest('input[type="checkbox"][value]');
  if (!input) return;
  if (!(integrationState.onboardingDraft instanceof Set)) integrationState.onboardingDraft = new Set();
  if (input.checked) integrationState.onboardingDraft.add(input.value);
  else integrationState.onboardingDraft.delete(input.value);
});
document.querySelector('[data-panel="integrationsPanel"]')?.addEventListener("click", () => refreshIntegrations(true));
document.getElementById("integrationRefreshButton")?.addEventListener("click", () => refreshIntegrations(true));
document.getElementById("integrationSaveButton")?.addEventListener("click", () => integrationCommand("/api/integrations/config", { config: collectIntegrationConfig() }));
document.getElementById("integrationEnabledInput")?.addEventListener("change", event => integrationCommand("/api/integrations/enable", { enabled: event.target.checked }));
document.getElementById("integrationStartButton")?.addEventListener("click", () => integrationCommand("/api/integrations/start"));
document.getElementById("integrationStopButton")?.addEventListener("click", () => integrationCommand("/api/integrations/stop"));
document.getElementById("integrationRestartButton")?.addEventListener("click", () => integrationCommand("/api/integrations/restart"));
document.getElementById("integrationTestButton")?.addEventListener("click", () => integrationCommand("/api/integrations/test"));
document.getElementById("integrationAuthorizeButton")?.addEventListener("click", event => {
  const target = event.currentTarget.dataset.authorizeUrl;
  if (!target) {
    integrationResult("Для этой интеграции не указан OAuth URL", false);
    return;
  }
  window.open(target, "_blank");
});
document.getElementById("integrationClearAuthButton")?.addEventListener("click", () => {
  if (confirm("Удалить локальные токены и остановить интеграцию?")) integrationCommand("/api/integrations/clear-auth");
});
document.getElementById("integrationFinishOnboarding")?.addEventListener("click", async () => {
  const selected = integrationState.onboardingDraft instanceof Set
    ? [...integrationState.onboardingDraft]
    : [...document.querySelectorAll("#integrationOnboardingChoices input:checked")].map(input => input.value);
  try {
    integrationState.bootstrap = await postJson("/api/integrations/onboarding", { completed: true, selected });
    integrationState.onboardingDraft = null;
    renderIntegrationBootstrap();
    refreshIntegrations(true);
  } catch (error) { integrationResult(error.message, false); }
});
document.querySelectorAll(".integration-detail-tab").forEach(button => button.addEventListener("click", () => {
  document.querySelectorAll(".integration-detail-tab").forEach(item => item.classList.toggle("active", item === button));
  document.querySelectorAll(".integration-detail-view").forEach(view => view.classList.remove("active"));
  document.getElementById(`integration${button.dataset.integrationView[0].toUpperCase()}${button.dataset.integrationView.slice(1)}View`)?.classList.add("active");
  if (button.dataset.integrationView === "logs") refreshIntegrationLogs();
}));

if (integrationIsPanelActive()) refreshIntegrations(true);
setInterval(() => {
  if (integrationIsPanelActive()) {
    refreshIntegrations(false);
    const logsView = document.getElementById("integrationLogsView");
    if (logsView?.classList.contains("active")) refreshIntegrationLogs();
  }
}, 4000);
