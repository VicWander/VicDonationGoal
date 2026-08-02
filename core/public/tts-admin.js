const adminTabs = [...document.querySelectorAll(".admin-tab")];
const adminPanels = [...document.querySelectorAll(".admin-panel")];
const ttsSubtabs = [...document.querySelectorAll(".tts-subtab")];
const ttsViews = [...document.querySelectorAll(".tts-view")];

const PROVIDERS = [
  ["speakerbot", "Speaker.bot"],
  ["edge", "Microsoft Edge"],
  ["yandex", "Yandex SpeechKit"],
  ["xtts", "XTTS Local"],
  ["http", "Custom HTTP"]
];

let ttsBootstrap = { config: {}, profiles: [], rules: [], queue: [], control: {}, status: {} };
let ttsHistory = [];
const expandedTTSQueueRows = new Set();
const expandedTTSHistoryRows = new Set();
let selectedProfileId = "";
let selectedRuleId = "";
let ttsSettingsFilled = false;

function byId(id) { return document.getElementById(id); }
function csvList(value) {
  if (Array.isArray(value)) return value.map(String).map(v => v.trim()).filter(Boolean);
  return String(value || "").split(",").map(v => v.trim()).filter(Boolean);
}
function maybeNumber(value) {
  const text = String(value ?? "").trim();
  if (!text) return null;
  const number = Number(text.replace(",", "."));
  return Number.isFinite(number) ? number : null;
}
function parseJsonField(id, fallback) {
  const text = byId(id).value.trim();
  if (!text) return fallback;
  try { return JSON.parse(text); }
  catch { throw new Error(`Поле «${byId(id).closest("label")?.firstChild?.textContent?.trim() || id}» должно содержать корректный JSON`); }
}
function statusLabel(status) {
  const map = { pending:"Ожидает", retry:"Повтор", processing:"Обработка", ready:"Готово", playing:"Проигрывается", played:"Проиграно", sent:"Отправлено", skipped:"Пропущено", error:"Ошибка", cancelled:"Отменено" };
  return map[status] || status || "—";
}
function statusClass(status) {
  if (["played","sent","ready"].includes(status)) return "ok";
  if (["error","cancelled"].includes(status)) return "off";
  if (["skipped","retry"].includes(status)) return "warn";
  return "unknown";
}
function providerLabel(value) {
  return PROVIDERS.find(([id]) => id === value)?.[1] || value || "—";
}
function profileById(id) { return (ttsBootstrap.profiles || []).find(p => p.id === id); }
function shortText(value, limit = 90) {
  const text = String(value || "").replace(/\s+/g, " ").trim();
  return text.length > limit ? `${text.slice(0, limit - 1)}…` : text || "—";
}
function safeJson(value) { return JSON.stringify(value ?? {}, null, 2); }

function ttsSetPanel(panelId) {
  adminTabs.forEach(button => button.classList.toggle("active", button.dataset.panel === panelId));
  adminPanels.forEach(panel => panel.classList.toggle("active", panel.id === panelId));
  localStorage.setItem("vic-admin-panel", panelId);
  if (panelId === "ttsPanel") refreshTTSAll(true);
}
adminTabs.forEach(button => button.addEventListener("click", () => ttsSetPanel(button.dataset.panel)));
ttsSubtabs.forEach(button => button.addEventListener("click", () => {
  ttsSubtabs.forEach(item => item.classList.toggle("active", item === button));
  ttsViews.forEach(view => view.classList.toggle("active", view.id === button.dataset.ttsView));
  localStorage.setItem("vic-tts-view", button.dataset.ttsView);
  if (button.dataset.ttsView === "ttsLogsView") refreshTTSLogs();
}));
function restoreAdminTabs() {
  const panel = localStorage.getItem("vic-admin-panel");
  if (panel && byId(panel)) ttsSetPanel(panel);
  const viewId = localStorage.getItem("vic-tts-view");
  const button = ttsSubtabs.find(item => item.dataset.ttsView === viewId);
  if (button && byId(viewId)) button.click();
}

function fillProviderSelects(config) {
  document.querySelectorAll(".provider-select").forEach(select => {
    const current = select.value;
    const none = select.classList.contains("allow-none") ? `<option value="">Нет</option>` : "";
    select.innerHTML = none + PROVIDERS.map(([id, name]) => `<option value="${id}">${name}</option>`).join("");
    select.value = [...select.options].some(o => o.value === current) ? current : (select.classList.contains("allow-none") ? "" : "speakerbot");
  });

  const defaultSelect = byId("ttsDefaultProfileInput");
  const current = defaultSelect.value || config.defaultProfileId || "default";
  defaultSelect.innerHTML = (ttsBootstrap.profiles || []).map(p => `<option value="${escapeHtml(p.id)}">${escapeHtml(p.name || p.id)}</option>`).join("");
  if ([...defaultSelect.options].some(o => o.value === current)) defaultSelect.value = current;
}

function fillTTSSettings(config) {
  if (ttsSettingsFilled) return;
  const donations = config.donations || {};
  const processing = config.textProcessing || {};
  const providers = config.providers || {};
  const speaker = providers.speakerbot || {};
  const edge = providers.edge || {};
  const yandex = providers.yandex || {};
  const xtts = providers.xtts || {};
  const http = providers.http || {};

  fillProviderSelects(config);
  byId("ttsEnabledInput").checked = Boolean(config.enabled);
  byId("ttsActiveProviderInput").value = config.activeProvider || "speakerbot";
  byId("ttsFallbackProviderInput").value = config.fallbackProvider || "";
  byId("ttsDefaultProfileInput").value = config.defaultProfileId || "default";
  byId("ttsMinAmountInput").value = donations.minAmount ?? 100;
  byId("ttsMaxLengthInput").value = processing.maxLength ?? 500;
  byId("ttsRemoveLinksInput").checked = processing.removeLinks !== false;
  byId("ttsStripHtmlInput").checked = processing.stripHtml !== false;
  byId("ttsSkipEmptyInput").checked = processing.skipEmpty !== false;
  byId("ttsExternalDefaultInput").checked = donations.externalDefaultSpeak !== false;

  byId("speakerEnabledInput").checked = speaker.enabled !== false;
  byId("speakerUrlInput").value = speaker.websocketUrl || "ws://127.0.0.1:7580/";
  byId("speakerAliasInput").value = speaker.defaultVoiceAlias || "Donations";
  byId("speakerBadWordsInput").checked = Boolean(speaker.badWordFilter);

  byId("edgeEnabledInput").checked = edge.enabled !== false;
  byId("edgeVoiceInput").value = edge.voice || "ru-RU-SvetlanaNeural";
  byId("edgeRateInput").value = edge.rate || "+0%";
  byId("edgePitchInput").value = edge.pitch || "+0Hz";
  byId("edgeVolumeInput").value = edge.volume || "+0%";

  byId("yandexEnabledInput").checked = Boolean(yandex.enabled);
  byId("yandexEndpointInput").value = yandex.endpoint || "https://tts.api.cloud.yandex.net/speech/v1/tts:synthesize";
  byId("yandexAuthModeInput").value = yandex.authMode || "api_key";
  byId("yandexApiKeyInput").value = yandex.apiKey || "";
  byId("yandexIamTokenInput").value = yandex.iamToken || "";
  byId("yandexFolderInput").value = yandex.folderId || "";
  byId("yandexVoiceInput").value = yandex.voice || "marina";
  byId("yandexEmotionInput").value = yandex.emotion || "friendly";
  byId("yandexSpeedInput").value = yandex.speed || "1.0";
  byId("yandexFormatInput").value = yandex.format || "mp3";

  byId("xttsEnabledInput").checked = Boolean(xtts.enabled);
  byId("xttsEndpointInput").value = xtts.endpoint || "http://127.0.0.1:8020/tts_to_audio/";
  byId("xttsLanguageInput").value = xtts.language || "ru";
  byId("xttsFormatInput").value = xtts.output_format || "wav";
  byId("xttsSpeakerInput").value = xtts.speakerWav || xtts.speaker_wav || "";
  byId("xttsResponseTypeInput").value = xtts.responseType || "audio";

  byId("httpEnabledInput").checked = Boolean(http.enabled);
  byId("httpMethodInput").value = http.method || "POST";
  byId("httpBodyTypeInput").value = http.bodyType || http.body_type || "json";
  byId("httpUrlInput").value = http.url || "";
  byId("httpHeadersInput").value = safeJson(http.headers || {});
  byId("httpBodyInput").value = safeJson(http.body || { text:"{text}", voice:"{voice}", language:"{language}" });
  byId("httpVoiceInput").value = http.voice || "";
  byId("httpLanguageInput").value = http.language || "ru";
  byId("httpResponseTypeInput").value = http.responseType || http.response_type || "audio";
  byId("httpAudioUrlFieldInput").value = http.audioUrlField || "audioUrl";
  byId("httpAudioBase64FieldInput").value = http.audioBase64Field || "audio";
  ttsSettingsFilled = true;
}

function renderTTSOverview() {
  const config = ttsBootstrap.config || {};
  const status = ttsBootstrap.status || {};
  const runtime = status.runtime || {};
  const control = ttsBootstrap.control || {};
  const player = status.player || {};
  const speakerConnected = runtime.connected && !runtime.stale;

  const badge = byId("ttsStateBadge");
  const stateText = !config.enabled ? "Выключен" : control.paused ? "Пауза" : runtime.stale ? "Hub не отвечает" : runtime.status || "Работает";
  badge.textContent = stateText;
  badge.className = `tts-state-badge ${!config.enabled ? "off" : control.paused ? "warn" : runtime.stale ? "off" : "ok"}`;

  byId("ttsProviderStat").textContent = providerLabel(config.activeProvider);
  byId("ttsSpeakerStat").textContent = speakerConnected ? "подключён" : "не подтверждён";
  byId("ttsPlayerStat").textContent = player.connected ? "подключён" : player.updatedAt ? `нет heartbeat ${player.ageSeconds}s` : "не открыт";
  byId("ttsQueueStat").textContent = status.queueLength ?? (ttsBootstrap.queue || []).length;
  byId("ttsHistoryStat").textContent = status.historyCount ?? ttsHistory.length;
  byId("ttsCurrentStat").textContent = runtime.currentJob ? `${runtime.currentJob.username || "—"}: ${shortText(runtime.currentJob.text, 45)}` : "—";
  byId("ttsErrorStat").textContent = runtime.lastError || "—";

  byId("speakerProviderBadge").textContent = config.activeProvider === "speakerbot" ? "основной" : config.fallbackProvider === "speakerbot" ? "fallback" : "доступен";
  byId("edgeProviderBadge").textContent = config.activeProvider === "edge" ? "основной" : config.fallbackProvider === "edge" ? "fallback" : "доступен";
  byId("speakerStatusText").textContent = speakerConnected ? "WebSocket Speaker.bot отвечает." : runtime.lastError?.startsWith("Speaker.bot") ? runtime.lastError : "Подключение не подтверждено. Запусти Speaker.bot и WebSocket Server.";
  byId("edgeStatusText").innerHTML = player.connected ? `OBS/браузерный плеер подключён, heartbeat ${escapeHtml(player.ageSeconds ?? 0)} сек.` : `Edge сможет создать MP3, но для звука открой <code>/tts.html</code> в OBS Browser Source.`;

  const profiles = ttsBootstrap.profiles || [];
  const testSelect = byId("ttsTestProfile");
  const selected = testSelect.value;
  testSelect.innerHTML = [`<option value="">Автоматически по правилам</option>`, ...profiles.map(p => `<option value="${escapeHtml(p.id)}">${escapeHtml(p.name || p.id)}</option>`)].join("");
  if ([...testSelect.options].some(o => o.value === selected)) testSelect.value = selected;
}

function profileVoiceLabel(profile) {
  const provider = profile.provider || "auto";
  if (provider === "speakerbot") return profile.voiceAlias || "без alias";
  if (provider === "edge") return profile.edgeVoice || "без голоса";
  if (provider === "yandex") return profile.yandexVoice || "без голоса";
  if (provider === "xtts") return profile.xttsSpeakerWav || "без reference WAV";
  if (provider === "http") return profile.httpVoice || "настройки провайдера";
  return "по общим настройкам";
}
function renderProfilesList() {
  const list = byId("ttsProfilesList");
  const profiles = ttsBootstrap.profiles || [];
  if (!profiles.length) { list.innerHTML = `<div class="empty-cell">Профилей пока нет</div>`; return; }
  list.innerHTML = profiles.map(profile => `<button type="button" class="select-list-item ${profile.id === selectedProfileId ? "active" : ""}" data-profile-id="${escapeHtml(profile.id)}"><b>${escapeHtml(profile.name || profile.id)}</b><span>${escapeHtml(providerLabel(profile.provider === "auto" ? ttsBootstrap.config.activeProvider : profile.provider))} · ${escapeHtml(profileVoiceLabel(profile))}${profile.enabled === false ? " · выключен" : ""}</span></button>`).join("");
  list.querySelectorAll("[data-profile-id]").forEach(button => button.addEventListener("click", () => selectProfile(button.dataset.profileId)));
}
function selectProfile(id) {
  selectedProfileId = id || "";
  const p = profileById(selectedProfileId) || {};
  byId("ttsProfileOriginalId").value = p.id || "";
  byId("ttsProfileIdInput").value = p.id || "";
  byId("ttsProfileNameInput").value = p.name || "";
  byId("ttsProfileProviderInput").value = p.provider || "auto";
  byId("ttsProfileAliasInput").value = p.voiceAlias || "";
  byId("ttsProfileEdgeVoiceInput").value = p.edgeVoice || "ru-RU-SvetlanaNeural";
  byId("ttsProfileYandexVoiceInput").value = p.yandexVoice || "marina";
  byId("ttsProfileYandexEmotionInput").value = p.yandexEmotion || "friendly";
  byId("ttsProfileYandexSpeedInput").value = p.yandexSpeed || "1.0";
  byId("ttsProfileXttsSpeakerInput").value = p.xttsSpeakerWav || "";
  byId("ttsProfileXttsLanguageInput").value = p.xttsLanguage || "ru";
  byId("ttsProfileHttpVoiceInput").value = p.httpVoice || "";
  byId("ttsProfileHttpLanguageInput").value = p.httpLanguage || "ru";
  byId("ttsProfileRateInput").value = p.rate || "+0%";
  byId("ttsProfilePitchInput").value = p.pitch || "+0Hz";
  byId("ttsProfileVolumeInput").value = p.volume || "+0%";
  byId("ttsProfileBadWordsInput").checked = Boolean(p.badWordFilter);
  byId("ttsProfileEnabledInput").checked = p.enabled !== false;
  renderProfilesList();
}
function profileFromEditor() {
  const id = byId("ttsProfileIdInput").value.trim();
  if (!id) throw new Error("У профиля должен быть ID");
  return {
    id, name: byId("ttsProfileNameInput").value.trim() || id,
    enabled: byId("ttsProfileEnabledInput").checked,
    provider: byId("ttsProfileProviderInput").value,
    voiceAlias: byId("ttsProfileAliasInput").value.trim(),
    edgeVoice: byId("ttsProfileEdgeVoiceInput").value.trim(),
    yandexVoice: byId("ttsProfileYandexVoiceInput").value.trim(),
    yandexEmotion: byId("ttsProfileYandexEmotionInput").value.trim(),
    yandexSpeed: byId("ttsProfileYandexSpeedInput").value.trim() || "1.0",
    xttsSpeakerWav: byId("ttsProfileXttsSpeakerInput").value.trim(),
    xttsLanguage: byId("ttsProfileXttsLanguageInput").value.trim() || "ru",
    httpVoice: byId("ttsProfileHttpVoiceInput").value.trim(),
    httpLanguage: byId("ttsProfileHttpLanguageInput").value.trim() || "ru",
    rate: byId("ttsProfileRateInput").value.trim() || "+0%",
    volume: byId("ttsProfileVolumeInput").value.trim() || "+0%",
    pitch: byId("ttsProfilePitchInput").value.trim() || "+0Hz",
    badWordFilter: byId("ttsProfileBadWordsInput").checked
  };
}

function fillRuleProfileOptions() {
  const select = byId("ttsRuleProfileInput");
  const selected = select.value;
  select.innerHTML = (ttsBootstrap.profiles || []).map(p => `<option value="${escapeHtml(p.id)}">${escapeHtml(p.name || p.id)}</option>`).join("");
  if ([...select.options].some(o => o.value === selected)) select.value = selected;
}
function renderRulesList() {
  const list = byId("ttsRulesList");
  const rules = [...(ttsBootstrap.rules || [])].sort((a,b) => Number(a.priority)-Number(b.priority));
  if (!rules.length) { list.innerHTML = `<div class="empty-cell">Правил пока нет</div>`; return; }
  list.innerHTML = rules.map(rule => `<button type="button" class="select-list-item ${rule.id === selectedRuleId ? "active" : ""}" data-rule-id="${escapeHtml(rule.id)}"><b>${escapeHtml(rule.name || rule.id)}</b><span>проверка №${escapeHtml(rule.priority)} → ${escapeHtml(rule.profileId)}${rule.enabled === false ? " · выключено" : ""}</span></button>`).join("");
  list.querySelectorAll("[data-rule-id]").forEach(button => button.addEventListener("click", () => selectRule(button.dataset.ruleId)));
}
function selectRule(id) {
  selectedRuleId = id || "";
  const rule = (ttsBootstrap.rules || []).find(item => item.id === selectedRuleId) || {};
  fillRuleProfileOptions();
  const c = rule.conditions || {};
  byId("ttsRuleOriginalId").value = rule.id || "";
  byId("ttsRuleIdInput").value = rule.id || "";
  byId("ttsRuleNameInput").value = rule.name || "";
  byId("ttsRuleProfileInput").value = rule.profileId || (ttsBootstrap.profiles[0]?.id || "");
  byId("ttsRulePriorityInput").value = rule.priority ?? 100;
  byId("ttsRuleEventTypesInput").value = (c.eventTypes || []).join(", ");
  byId("ttsRuleSourcesInput").value = (c.sources || []).join(", ");
  byId("ttsRuleUserIdsInput").value = (c.userIds || []).join(", ");
  byId("ttsRuleUsernamesInput").value = (c.usernames || []).join(", ");
  byId("ttsRuleRolesInput").value = (c.roles || []).join(", ");
  byId("ttsRuleRewardIdsInput").value = (c.rewardIds || []).join(", ");
  byId("ttsRuleMinAmountInput").value = c.minAmount ?? "";
  byId("ttsRuleMaxAmountInput").value = c.maxAmount ?? "";
  byId("ttsRuleEnabledInput").checked = rule.enabled !== false;
  renderRulesList();
}
function ruleFromEditor() {
  const id = byId("ttsRuleIdInput").value.trim();
  if (!id) throw new Error("У правила должен быть ID");
  return { id, name: byId("ttsRuleNameInput").value.trim() || id, enabled: byId("ttsRuleEnabledInput").checked, priority: Number(byId("ttsRulePriorityInput").value) || 100, profileId: byId("ttsRuleProfileInput").value, conditions: { eventTypes: csvList(byId("ttsRuleEventTypesInput").value), sources: csvList(byId("ttsRuleSourcesInput").value), userIds: csvList(byId("ttsRuleUserIdsInput").value), usernames: csvList(byId("ttsRuleUsernamesInput").value), roles: csvList(byId("ttsRuleRolesInput").value), rewardIds: csvList(byId("ttsRuleRewardIdsInput").value), minAmount: maybeNumber(byId("ttsRuleMinAmountInput").value), maxAmount: maybeNumber(byId("ttsRuleMaxAmountInput").value) } };
}

function detailsBlock(rows) {
  return `<div class="details-grid">${rows.map(([label,value]) => `<div class="detail-item"><b>${escapeHtml(label)}</b><div>${escapeHtml(String(value ?? "—"))}</div></div>`).join("")}</div>`;
}
function renderQueue() {
  const body = byId("ttsQueueBody");
  const queue = ttsBootstrap.queue || [];
  byId("ttsQueueCount").textContent = `${queue.length} задач`;
  if (!queue.length) { body.innerHTML = `<tr><td colspan="6" class="empty-cell">Очередь пуста</td></tr>`; return; }
  body.innerHTML = queue.map(job => {
    const text = job.cleanedText || job.originalText || "—";
    const jobId = String(job.id || "");
    const isExpanded = expandedTTSQueueRows.has(jobId);
    const detailHidden = isExpanded ? "" : " hidden";
    const expandLabel = isExpanded ? "Свернуть" : "Развернуть";
    return `<tr class="summary-row tts-queue-summary-row" data-job-id="${escapeHtml(jobId)}">
      <td class="history-cell cell-date"><span class="cell-label">Время</span><div class="date-cell">${escapeHtml(formatDate(job.createdAt))}</div></td>
      <td class="history-cell cell-status"><span class="cell-label">Статус</span><div><span class="source-pill ${statusClass(job.status)}">${escapeHtml(statusLabel(job.status))}</span></div></td>
      <td class="history-cell cell-event"><span class="cell-label">Событие</span><div class="cell-value">${escapeHtml(job.eventType || "—")}</div></td>
      <td class="history-cell cell-user"><span class="cell-label">Пользователь</span><div class="cell-value strong-value">${escapeHtml(job.username || "—")}</div></td>
      <td class="history-cell cell-message"><span class="cell-label">Текст</span><div class="message-preview">${escapeHtml(shortText(text, 180))}</div></td>
      <td class="history-cell cell-actions"><span class="cell-label">Действия</span><div class="row-buttons"><button type="button" class="icon-button secondary" data-queue-action="expand">${expandLabel}</button><button type="button" class="icon-button danger" data-queue-action="delete">Удал.</button></div></td>
    </tr><tr class="details-row" data-detail-for="${escapeHtml(jobId)}"${detailHidden}><td colspan="6">${detailsBlock([["Полный текст",text],["Профиль",job.profileId || "авто"],["Провайдер",job.provider || "ещё не выбран"],["Попытки",job.attempts || 0],["Ошибка",job.error || "—"],["ID",job.id]])}</td></tr>`;
  }).join("");
}

function historySearchRows() {
  const query = byId("ttsHistorySearch").value.trim().toLowerCase();
  const status = byId("ttsHistoryStatusFilter").value;
  const provider = byId("ttsHistoryProviderFilter").value;
  return ttsHistory.filter(job => {
    if (status && job.status !== status) return false;
    if (provider && job.provider !== provider) return false;
    if (!query) return true;
    return [job.id,job.username,job.eventType,job.source,job.originalText,job.cleanedText,job.provider,job.voice,job.status,job.error,...(job.removedParts||[])].join(" ").toLowerCase().includes(query);
  });
}
function renderHistory() {
  const body = byId("ttsHistoryBody");
  const rows = [...historySearchRows()].reverse();
  byId("ttsHistoryCount").textContent = `${rows.length} из ${ttsHistory.length} записей`;
  if (!rows.length) { body.innerHTML = `<tr><td colspan="7" class="empty-cell">История пуста</td></tr>`; return; }
  body.innerHTML = rows.map(job => {
    const details = (job.removedParts || []).join("\n") || "—";
    const voice = [providerLabel(job.provider), job.voice].filter(Boolean).join(" / ") || "—";
    const jobId = String(job.id || "");
    const isExpanded = expandedTTSHistoryRows.has(jobId);
    const detailHidden = isExpanded ? "" : " hidden";
    const expandLabel = isExpanded ? "Свернуть" : "Развернуть";
    return `<tr class="summary-row tts-history-summary-row" data-history-id="${escapeHtml(jobId)}">
      <td class="history-cell cell-date"><span class="cell-label">Время</span><div class="date-cell">${escapeHtml(formatDate(job.completedAt || job.updatedAt || job.createdAt))}</div></td>
      <td class="history-cell cell-status"><span class="cell-label">Статус</span><div><span class="source-pill ${statusClass(job.status)}">${escapeHtml(statusLabel(job.status))}</span></div></td>
      <td class="history-cell cell-event"><span class="cell-label">Событие</span><div class="cell-value">${escapeHtml(job.eventType || "—")}</div></td>
      <td class="history-cell cell-user"><span class="cell-label">Пользователь</span><div class="cell-value strong-value">${escapeHtml(job.username || "—")}</div></td>
      <td class="history-cell cell-voice"><span class="cell-label">Голос</span><div class="cell-value">${escapeHtml(voice)}</div></td>
      <td class="history-cell cell-message"><span class="cell-label">Текст после очистки</span><div class="message-preview">${escapeHtml(shortText(job.cleanedText || job.originalText, 180))}</div></td>
      <td class="history-cell cell-actions"><span class="cell-label">Действия</span><div class="row-buttons"><button type="button" class="icon-button secondary" data-history-action="expand">${expandLabel}</button><button type="button" class="icon-button secondary" data-history-action="retry">Повт.</button><button type="button" class="icon-button danger" data-history-action="delete">Удал.</button></div></td>
    </tr><tr class="details-row" data-history-detail="${escapeHtml(jobId)}"${detailHidden}><td colspan="7">${detailsBlock([["Оригинал",job.originalText || "—"],["После очистки",job.cleanedText || "—"],["Удалено",details],["Профиль",job.profileId || "—"],["Правило",job.matchedRuleId || "по умолчанию / напрямую"],["Провайдер",providerLabel(job.provider)],["Запрошенный провайдер",job.requestedProvider || "—"],["Fallback",job.fallbackUsed ? "использован" : "нет"],["Ошибка",job.error || "—"],["Источник",job.source || "—"],["User ID",job.userId || "—"],["Reward ID",job.rewardId || "—"],["ID задачи",job.id]])}</td></tr>`;
  }).join("");
}


async function refreshTTSLogs() {
  try {
    const logs = await getJson("/api/tts/logs?limit=300");
    byId("ttsLogsOutput").textContent = (logs || []).map(row => `[${row.time || "—"}] ${String(row.level || "info").toUpperCase()} ${row.message || ""}${row.details ? ` ${JSON.stringify(row.details)}` : ""}`).join("\n") || "Логов пока нет.";
  } catch (error) { byId("ttsLogsOutput").textContent = `Не удалось загрузить логи: ${error}`; }
}
async function refreshTTSAll(forceSettings = false) {
  try {
    const [bootstrap, history] = await Promise.all([getJson("/api/tts/bootstrap"), getJson("/api/tts/history?limit=1000")]);
    ttsBootstrap = bootstrap || ttsBootstrap;
    ttsHistory = Array.isArray(history) ? history : [];
    if (forceSettings) ttsSettingsFilled = false;
    fillTTSSettings(ttsBootstrap.config || {});
    fillProviderSelects(ttsBootstrap.config || {});
    renderTTSOverview(); fillRuleProfileOptions(); renderProfilesList(); renderRulesList(); renderQueue(); renderHistory();
    if (!selectedProfileId && ttsBootstrap.profiles?.length) selectProfile(ttsBootstrap.profiles[0].id);
    if (!selectedRuleId && ttsBootstrap.rules?.length) selectRule(ttsBootstrap.rules[0].id);
  } catch (error) {
    const badge = byId("ttsStateBadge"); if (badge) { badge.textContent = "Ошибка API"; badge.className = "tts-state-badge off"; }
    console.error("Не удалось обновить TTS Hub", error);
  }
}

function buildConfigPatch() {
  return {
    enabled: byId("ttsEnabledInput").checked,
    activeProvider: byId("ttsActiveProviderInput").value,
    fallbackProvider: byId("ttsFallbackProviderInput").value || null,
    defaultProfileId: byId("ttsDefaultProfileInput").value,
    donations: { minAmount: Number(byId("ttsMinAmountInput").value) || 0, externalDefaultSpeak: byId("ttsExternalDefaultInput").checked, manualRequiresSpeakFlag: true, manualBypassMinAmount: true },
    textProcessing: { maxLength: Number(byId("ttsMaxLengthInput").value) || 500, removeLinks: byId("ttsRemoveLinksInput").checked, stripHtml: byId("ttsStripHtmlInput").checked, skipEmpty: byId("ttsSkipEmptyInput").checked },
    providers: {
      speakerbot: { enabled: byId("speakerEnabledInput").checked, websocketUrl: byId("speakerUrlInput").value.trim(), defaultVoiceAlias: byId("speakerAliasInput").value.trim(), badWordFilter: byId("speakerBadWordsInput").checked },
      edge: { enabled: byId("edgeEnabledInput").checked, voice: byId("edgeVoiceInput").value.trim(), rate: byId("edgeRateInput").value.trim(), pitch: byId("edgePitchInput").value.trim(), volume: byId("edgeVolumeInput").value.trim() },
      yandex: { enabled: byId("yandexEnabledInput").checked, endpoint: byId("yandexEndpointInput").value.trim(), authMode: byId("yandexAuthModeInput").value, apiKey: byId("yandexApiKeyInput").value.trim(), iamToken: byId("yandexIamTokenInput").value.trim(), folderId: byId("yandexFolderInput").value.trim(), voice: byId("yandexVoiceInput").value.trim(), emotion: byId("yandexEmotionInput").value.trim(), speed: byId("yandexSpeedInput").value.trim(), format: byId("yandexFormatInput").value },
      xtts: { enabled: byId("xttsEnabledInput").checked, endpoint: byId("xttsEndpointInput").value.trim(), language: byId("xttsLanguageInput").value.trim(), speakerWav: byId("xttsSpeakerInput").value.trim(), output_format: byId("xttsFormatInput").value.trim(), responseType: byId("xttsResponseTypeInput").value },
      http: { enabled: byId("httpEnabledInput").checked, method: byId("httpMethodInput").value, bodyType: byId("httpBodyTypeInput").value, url: byId("httpUrlInput").value.trim(), headers: parseJsonField("httpHeadersInput", {}), body: parseJsonField("httpBodyInput", {text:"{text}"}), voice: byId("httpVoiceInput").value.trim(), language: byId("httpLanguageInput").value.trim(), responseType: byId("httpResponseTypeInput").value, audioUrlField: byId("httpAudioUrlFieldInput").value.trim(), audioBase64Field: byId("httpAudioBase64FieldInput").value.trim() }
    }
  };
}
byId("ttsSaveGeneralButton").addEventListener("click", async () => { try { await postJson("/api/tts/config", buildConfigPatch()); ttsSettingsFilled = false; await refreshTTSAll(true); } catch (error) { alert(error.message || error); } });

async function sendTest(profileId = byId("ttsTestProfile").value, provider = byId("ttsTestProvider").value) {
  await postJson("/api/tts/test", { text: byId("ttsTestText").value, profileId, provider });
  await refreshTTSAll(true);
}
byId("ttsTestButton").addEventListener("click", () => sendTest());
byId("ttsSendTestButton").addEventListener("click", () => sendTest());
document.querySelectorAll("[data-provider-test]").forEach(button => button.addEventListener("click", async () => {
  try { await postJson("/api/tts/config", buildConfigPatch()); await sendTest("", button.dataset.providerTest); }
  catch (error) { alert(error.message || error); }
}));
for (const [id, action] of [["ttsPauseButton","pause"],["ttsResumeButton","resume"],["ttsStopButton","stop"],["ttsClearButton","clear"]]) byId(id).addEventListener("click", async () => { if (action === "clear" && !confirm("Очистить локальную и Speaker.bot очередь?")) return; await postJson("/api/tts/control", {action}); await refreshTTSAll(true); });

byId("ttsNewProfileButton").addEventListener("click", () => selectProfile(""));
byId("ttsSaveProfileButton").addEventListener("click", async () => {
  try {
    const profile = profileFromEditor(); const originalId = byId("ttsProfileOriginalId").value; const profiles = [...(ttsBootstrap.profiles || [])];
    if (profile.id !== originalId && profiles.some(p => p.id === profile.id)) throw new Error(`Профиль с ID ${profile.id} уже существует`);
    const index = profiles.findIndex(p => p.id === originalId); if (index >= 0) profiles[index] = profile; else profiles.push(profile);
    await postJson("/api/tts/profiles", {profiles}); selectedProfileId = profile.id; ttsSettingsFilled = false; await refreshTTSAll(true);
  } catch (error) { alert(error.message || error); }
});
byId("ttsTestProfileButton").addEventListener("click", async () => { const profile = profileFromEditor(); await sendTest(profile.id, ""); });
byId("ttsDeleteProfileButton").addEventListener("click", async () => { const id = byId("ttsProfileOriginalId").value; if (!id || !confirm(`Удалить профиль ${id}?`)) return; try { await postJson("/api/tts/profiles", {profiles:(ttsBootstrap.profiles||[]).filter(p=>p.id!==id)}); selectedProfileId=""; ttsSettingsFilled=false; await refreshTTSAll(true); } catch(error){ alert(error.message||error); } });

byId("ttsNewRuleButton").addEventListener("click", () => selectRule(""));
byId("ttsSaveRuleButton").addEventListener("click", async () => {
  try { const rule=ruleFromEditor(); const originalId=byId("ttsRuleOriginalId").value; const rules=[...(ttsBootstrap.rules||[])]; if(rule.id!==originalId&&rules.some(r=>r.id===rule.id)) throw new Error(`Правило с ID ${rule.id} уже существует`); const index=rules.findIndex(r=>r.id===originalId); if(index>=0) rules[index]=rule; else rules.push(rule); await postJson("/api/tts/rules",{rules}); selectedRuleId=rule.id; await refreshTTSAll(true); }
  catch(error){ alert(error.message||error); }
});
byId("ttsDeleteRuleButton").addEventListener("click", async () => { const id=byId("ttsRuleOriginalId").value; if(!id||!confirm(`Удалить правило ${id}?`))return; await postJson("/api/tts/rules",{rules:(ttsBootstrap.rules||[]).filter(r=>r.id!==id)}); selectedRuleId=""; await refreshTTSAll(true); });
byId("ttsTestRuleButton").addEventListener("click", async () => {
  try {
    const result=await postJson("/api/tts/rules/test",{eventType:byId("ttsRouteEventTypeInput").value.trim(),source:byId("ttsRouteSourceInput").value.trim(),username:byId("ttsRouteUsernameInput").value.trim(),userId:byId("ttsRouteUserIdInput").value.trim(),roles:csvList(byId("ttsRouteRolesInput").value),rewardId:byId("ttsRouteRewardInput").value.trim(),amount:Number(byId("ttsRouteAmountInput").value)||0,amountForGoal:Number(byId("ttsRouteAmountInput").value)||0,text:byId("ttsRouteTextInput").value});
    byId("ttsRuleTestResult").textContent = `Причина: ${result.reason}\nПравило: ${result.matchedRule?.name || "нет — профиль по умолчанию/напрямую"}\nПрофиль: ${result.profile?.name} (${result.profile?.id})\nПровайдер: ${providerLabel(result.provider)}\nГолос: ${result.voice || "не задан"}\nFallback: ${providerLabel(result.fallbackProvider)}`;
  } catch(error){ byId("ttsRuleTestResult").textContent=`Ошибка: ${error.message||error}`; }
});

document.addEventListener("click", async event => {
  const queueButton = event.target.closest("[data-queue-action]");
  if (queueButton) {
    const row = queueButton.closest("tr[data-job-id]");
    const id = String(row?.dataset.jobId || "");
    const detail = document.querySelector(`[data-detail-for="${CSS.escape(id)}"]`);
    if (queueButton.dataset.queueAction === "expand" && detail) {
      const shouldExpand = detail.hidden;
      detail.hidden = !shouldExpand;
      if (shouldExpand) expandedTTSQueueRows.add(id);
      else expandedTTSQueueRows.delete(id);
      queueButton.textContent = shouldExpand ? "Свернуть" : "Развернуть";
    } else if (queueButton.dataset.queueAction === "delete" && confirm("Удалить задачу из очереди?")) {
      expandedTTSQueueRows.delete(id);
      await postJson("/api/tts/job/delete", { id });
      await refreshTTSAll(true);
    }
    return;
  }

  const historyButton = event.target.closest("[data-history-action]");
  if (historyButton) {
    const row = historyButton.closest("tr[data-history-id]");
    const id = String(row?.dataset.historyId || "");
    const detail = document.querySelector(`[data-history-detail="${CSS.escape(id)}"]`);
    const action = historyButton.dataset.historyAction;
    if (action === "expand" && detail) {
      const shouldExpand = detail.hidden;
      detail.hidden = !shouldExpand;
      if (shouldExpand) expandedTTSHistoryRows.add(id);
      else expandedTTSHistoryRows.delete(id);
      historyButton.textContent = shouldExpand ? "Свернуть" : "Развернуть";
    } else if (action === "retry") {
      await postJson("/api/tts/job/retry", { id });
      await refreshTTSAll(true);
    } else if (action === "delete" && confirm("Удалить запись из истории TTS?")) {
      expandedTTSHistoryRows.delete(id);
      await postJson("/api/tts/history/delete", { id });
      await refreshTTSAll(true);
    }
  }
});

for (const id of ["ttsHistorySearch","ttsHistoryStatusFilter","ttsHistoryProviderFilter"]) { byId(id).addEventListener(id==="ttsHistorySearch"?"input":"change",renderHistory); }
byId("ttsClearHistoryButton").addEventListener("click",async()=>{if(!confirm("Очистить всю историю TTS?"))return;await postJson("/api/tts/history/clear",{});await refreshTTSAll(true);});
byId("ttsRefreshLogsButton").addEventListener("click",refreshTTSLogs);

restoreAdminTabs();
refreshTTSAll(true);
setInterval(()=>{if(byId("ttsPanel").classList.contains("active"))refreshTTSAll(false);},2500);
