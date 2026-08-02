const integrationState = {
  bootstrap: { integrations: [], onboarding: {} },
  selectedId: "",
  detail: null,
  refreshing: false
};

function integrationStatusLabel(item) {
  const state = item?.commonState || item?.state;
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
function integrationResult(message, ok = true) {
  const box = document.getElementById("integrationActionResult");
  box.hidden = false;
  box.className = `integration-result ${ok ? "ok" : "error"}`;
  box.textContent = message || (ok ? "Готово" : "Ошибка");
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
  document.getElementById("integrationErrorStat").textContent = list.filter(item => ["error","degraded"].includes(item.commonState) || item.status?.lastError || item.status?.last_error).length;
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
    const selected = new Set(onboarding.selected || []);
    document.getElementById("integrationOnboardingChoices").innerHTML = list.map(item => `
      <label class="integration-choice">
        <input type="checkbox" value="${escapeHtml(item.id)}" ${selected.has(item.id) ? "checked" : ""} />
        <span class="integration-icon">${escapeHtml(item.icon)}</span>
        <span><strong>${escapeHtml(item.name)}</strong><small>${escapeHtml(item.description)}</small></span>
      </label>
    `).join("");
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
  const authorizeButton = document.getElementById("integrationAuthorizeButton");
  authorizeButton.hidden = !manifest.capabilities?.oauth;
  authorizeButton.dataset.authorizeUrl = manifest.authStartPath || summary.status?.authorizeUrl || "";
  document.getElementById("integrationClearAuthButton").hidden = !manifest.capabilities?.clearAuth;
  document.getElementById("integrationTechnical").textContent = JSON.stringify(summary, null, 2);
  document.getElementById("integrationGuide").innerHTML = integrationMarkdown(detail.guide);

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
    integrationResult(result.message || "Готово", Boolean(result.ok ?? true));
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
  const selected = [...document.querySelectorAll("#integrationOnboardingChoices input:checked")].map(input => input.value);
  try {
    integrationState.bootstrap = await postJson("/api/integrations/onboarding", { completed: true, selected });
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
