(function () {
  "use strict";

  const schemaBadge = document.getElementById("portabilitySchemaBadge");
  const fileCount = document.getElementById("portabilityFileCount");
  const dataSize = document.getElementById("portabilityDataSize");
  const lastBackup = document.getElementById("portabilityLastBackup");
  const backupsList = document.getElementById("portabilityBackupsList");
  const refreshButton = document.getElementById("portabilityRefreshButton");
  const downloadButton = document.getElementById("downloadBackupButton");

  const backupInput = document.getElementById("backupRestoreInput");
  const folderInput = document.getElementById("oldVersionFolderInput");
  const donationsInput = document.getElementById("donationsImportInput");
  const donationAlertsInput = document.getElementById("donationAlertsImportInput");

  const previewPanel = document.getElementById("portabilityPreview");
  const previewSummary = document.getElementById("portabilityPreviewSummary");
  const previewKind = document.getElementById("portabilityPreviewKind");
  const previewWarnings = document.getElementById("portabilityPreviewWarnings");
  const previewItems = document.getElementById("portabilityPreviewItems");
  const includeGoalRow = document.getElementById("portabilityIncludeGoalRow");
  const includeGoal = document.getElementById("portabilityIncludeGoal");
  const applyButton = document.getElementById("portabilityApplyButton");
  const cancelButton = document.getElementById("portabilityCancelButton");

  if (!previewPanel) return;

  let stagedToken = "";
  let stagedKind = "";
  let stagedPreview = {};
  const selectedDaKeys = new Set();
  let busy = false;

  const kindNames = {
    backup: "Полный бэкап",
    folder: "Старая версия",
    donations: "donations.json",
    donationalerts: "DonationAlerts"
  };

  const categoryNames = {
    donation_history: "История донатов",
    topdonation: "TopDonation",
    goal_and_rates: "Цель и курсы",
    integrations: "Подключения и токены",
    integration_selection: "Выбор интеграций",
    streamerbot: "Streamer.bot",
    tts: "TTS Hub",
    other: "Прочее"
  };

  function escapePortabilityHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function formatBytes(value) {
    let size = Number(value) || 0;
    const units = ["Б", "КБ", "МБ", "ГБ"];
    let unit = 0;
    while (size >= 1024 && unit < units.length - 1) {
      size /= 1024;
      unit += 1;
    }
    return `${size.toLocaleString("ru-RU", { maximumFractionDigits: unit ? 1 : 0 })} ${units[unit]}`;
  }

  function formatMoney(value) {
    return `${(Number(value) || 0).toLocaleString("ru-RU", { maximumFractionDigits: 2 })} RUB`;
  }

  function formatPortableDate(value) {
    if (!value) return "—";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return String(value);
    return date.toLocaleString("ru-RU", {
      day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit"
    });
  }

  async function responseJson(response) {
    const payload = await response.json().catch(() => ({}));
    if (!response.ok || payload.ok === false) {
      throw new Error(payload.message || `HTTP ${response.status}`);
    }
    return payload;
  }

  function setBusy(value, message = "Проверка файла...") {
    busy = Boolean(value);
    updateApplyButton();
    cancelButton.disabled = busy;
    for (const input of [backupInput, folderInput, donationsInput, donationAlertsInput]) {
      if (input) input.disabled = busy;
    }
    if (busy) {
      previewPanel.hidden = false;
      previewSummary.textContent = message;
      previewKind.textContent = "Проверка";
      previewWarnings.innerHTML = "";
      previewItems.innerHTML = '<div class="empty-cell">Подождите, данные проверяются локально...</div>';
      previewPanel.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }

  function clearPreview() {
    stagedToken = "";
    stagedKind = "";
    stagedPreview = {};
    selectedDaKeys.clear();
    previewPanel.hidden = true;
    previewWarnings.innerHTML = "";
    previewItems.innerHTML = "";
    includeGoalRow.hidden = true;
    includeGoal.checked = false;
    applyButton.disabled = true;
    for (const input of [backupInput, folderInput, donationsInput, donationAlertsInput]) {
      if (input) input.value = "";
    }
  }

  function renderWarnings(warnings) {
    const rows = Array.isArray(warnings) ? warnings.filter(Boolean) : [];
    previewWarnings.innerHTML = rows.map(item =>
      `<div class="portability-warning">${escapePortabilityHtml(item)}</div>`
    ).join("");
  }

  function renderCategories(categories) {
    return Object.entries(categories || {}).map(([category, count]) => `
      <div class="portability-preview-row">
        <strong>${escapePortabilityHtml(categoryNames[category] || category)}</strong>
        <span>${escapePortabilityHtml(count)} файлов</span>
      </div>`).join("");
  }

  function renderDonationAlertsItems(items) {
    const rows = Array.isArray(items) ? items : [];
    if (!rows.length) return '<div class="empty-cell">В таблице нет подходящих строк.</div>';
    const header = `<div class="portability-preview-row portability-preview-header" aria-hidden="true">
      <b>Донатер</b><span>Выгрузка DA</span><span>События в программе</span><span>Ручные суммы</span><span>Будет добавлено</span>
    </div>`;
    return header + rows.map(item => {
      const change = Number(item.change) || 0;
      const changeClass = change > 0 ? "positive" : (change < 0 ? "negative" : "");
      const changeText = `${change > 0 ? "+" : ""}${formatMoney(change)}`;
      const key = String(item.importKey || "");
      const disabled = Math.abs(change) < 0.005;
      if (item.selectedByDefault && !disabled) selectedDaKeys.add(key);
      const name = item.profileName || item.username || "Аноним";
      return `<div class="portability-preview-row">
        <div class="portability-import-choice"><input type="checkbox" data-da-import-key="${escapePortabilityHtml(key)}" ${selectedDaKeys.has(key) ? "checked" : ""} ${disabled ? "disabled" : ""}><b class="portability-import-name" title="${escapePortabilityHtml(name)}">${escapePortabilityHtml(name)}${item.requiresReview ? " · проверить" : ""}</b></div>
        <span title="Итог в выгрузке DonationAlerts">Выгрузка: ${escapePortabilityHtml(formatMoney(item.exported))}</span>
        <span title="Уже есть отдельными донатами DonationAlerts">События: ${escapePortabilityHtml(formatMoney(item.recordedEvents))}</span>
        <span title="Ручные корректировки этого профиля">Вручную: ${escapePortabilityHtml(formatMoney(item.manualAdjustments))}</span>
        <span class="${changeClass}" title="Изменение TopDonation после импорта">${escapePortabilityHtml(changeText)}</span>
      </div>`;
    }).join("");
  }

  function selectedDaTopChange() {
    const items = Array.isArray(stagedPreview.items) ? stagedPreview.items : [];
    return items.reduce((sum, item) => selectedDaKeys.has(String(item.importKey || "")) ? sum + (Number(item.change) || 0) : sum, 0);
  }

  function updateDaSelectionSummary() {
    if (stagedKind !== "donationalerts") return;
    const change = selectedDaTopChange();
    const sign = change > 0 ? "+" : "";
    previewSummary.textContent = `${stagedPreview.rows || 0} имён · итог выгрузки ${formatMoney(stagedPreview.exportedTotal)} · выбрано ${selectedDaKeys.size} · изменение TopDonation ${sign}${formatMoney(change)}`;
    updateApplyButton();
  }

  function updateApplyButton() {
    const nothingSelected = stagedKind === "donationalerts" && selectedDaKeys.size === 0;
    applyButton.disabled = busy || !stagedToken || nothingSelected;
  }

  function renderPreview(preview) {
    stagedPreview = preview || {};
    stagedKind = String(preview.kind || "");
    selectedDaKeys.clear();
    previewPanel.hidden = false;
    previewKind.textContent = kindNames[stagedKind] || "Импорт";
    renderWarnings(preview.warnings);
    includeGoalRow.hidden = stagedKind !== "donations";
    includeGoal.checked = false;

    if (stagedKind === "backup" || stagedKind === "folder") {
      const source = preview.sourceVersion && preview.sourceVersion !== "unknown" ? `v${preview.sourceVersion}` : "неизвестная версия";
      previewSummary.textContent = `${source} · ${preview.fileCount || 0} файлов · ${formatBytes(preview.totalSize)}`;
      previewItems.innerHTML = renderCategories(preview.categories) || '<div class="empty-cell">Состав архива пуст.</div>';
    } else if (stagedKind === "donations") {
      previewSummary.textContent = `${preview.rows || 0} записей: ${preview.newCount || 0} новых, ${preview.duplicateCount || 0} дублей, ${preview.invalidCount || 0} некорректных`;
      const sourceRows = Object.entries(preview.sources || {}).map(([source, count]) => `
        <div class="portability-preview-row"><strong>${escapePortabilityHtml(source)}</strong><span>${escapePortabilityHtml(count)} новых записей</span></div>`).join("");
      previewItems.innerHTML = `
        <div class="portability-preview-row"><strong>Изменение TopDonation</strong><span class="positive">+${escapePortabilityHtml(formatMoney(preview.newTopAmount))}</span></div>
        ${sourceRows || '<div class="empty-cell">Новых записей нет — файл уже импортирован.</div>'}`;
    } else if (stagedKind === "donationalerts") {
      previewItems.innerHTML = renderDonationAlertsItems(preview.items);
      updateDaSelectionSummary();
    } else {
      previewSummary.textContent = "Данные проверены.";
      previewItems.innerHTML = "";
    }
    updateApplyButton();
    previewPanel.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  async function stageRawFile(kind, file) {
    if (!file || busy) return;
    stagedToken = "";
    setBusy(true, `Проверяю ${file.name}...`);
    try {
      const query = new URLSearchParams({ kind, filename: file.name });
      const response = await fetch(`/api/portability/stage?${query}`, {
        method: "POST",
        headers: { "Content-Type": "application/octet-stream" },
        body: file
      });
      const result = await responseJson(response);
      stagedToken = result.token;
      renderPreview(result.preview || {});
    } catch (error) {
      clearPreview();
      alert(`Импорт не подготовлен: ${error.message}`);
    } finally {
      setBusy(false);
    }
  }

  function normalizedRelativePath(file) {
    return String(file.webkitRelativePath || file.name || "").replaceAll("\\", "/").replace(/^\/+/, "");
  }

  function supportedFolderPath(path) {
    const parts = String(path).split("/").filter(Boolean);
    for (let offset = 0; offset < parts.length; offset += 1) {
      const candidate = parts.slice(offset);
      const joined = candidate.join("/");
      if (joined === "integrations/integrations_onboarding.json") return true;
      if (candidate.length === 3 && candidate[0] === "core" && candidate[1] === "data") {
        return ["state.json", "donations.json", "rates.json", "donor_profiles.json", "donor_adjustments.json"].includes(candidate[2]);
      }
      if (candidate.length >= 3 && candidate[0] === "integrations") {
        const name = candidate[candidate.length - 1];
        if (name.endsWith(".json") && !name.endsWith(".example.json") && name !== "manifest.json") return true;
        if (candidate.length >= 4 && candidate[1] === "tts" && ["voices", "voice_samples", "reference_audio", "custom_audio"].includes(candidate[2])) return true;
      }
    }
    return false;
  }

  function arrayBufferToBase64(buffer) {
    const bytes = new Uint8Array(buffer);
    const chunkSize = 0x8000;
    let binary = "";
    for (let index = 0; index < bytes.length; index += chunkSize) {
      binary += String.fromCharCode(...bytes.subarray(index, index + chunkSize));
    }
    return btoa(binary);
  }

  async function stageOldFolder(fileList) {
    const allFiles = [...(fileList || [])];
    if (!allFiles.length || busy) return;
    stagedToken = "";
    setBusy(true, "Читаю пользовательские данные старой версии...");
    try {
      let sourceVersion = "unknown";
      const versionFile = allFiles.find(file => /(^|\/)VERSION$/i.test(normalizedRelativePath(file)));
      if (versionFile) sourceVersion = (await versionFile.text()).trim() || "unknown";

      const selected = allFiles.filter(file => supportedFolderPath(normalizedRelativePath(file)));
      if (!selected.length) throw new Error("В выбранной папке не найдено данных VicDonationGoal");

      const files = [];
      for (let index = 0; index < selected.length; index += 1) {
        const file = selected[index];
        previewSummary.textContent = `Читаю файл ${index + 1} из ${selected.length}: ${file.name}`;
        files.push({
          path: normalizedRelativePath(file),
          content: arrayBufferToBase64(await file.arrayBuffer())
        });
      }

      previewSummary.textContent = "Проверяю структуру выбранной версии...";
      const response = await fetch("/api/portability/stage-folder", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ sourceVersion, files })
      });
      const result = await responseJson(response);
      stagedToken = result.token;
      renderPreview(result.preview || {});
    } catch (error) {
      clearPreview();
      alert(`Старая версия не подготовлена к переносу: ${error.message}`);
    } finally {
      setBusy(false);
    }
  }

  function renderBackups(backups) {
    const rows = Array.isArray(backups) ? backups : [];
    if (!rows.length) {
      backupsList.innerHTML = '<div class="empty-cell">Локальных резервных копий пока нет.</div>';
      return;
    }
    backupsList.innerHTML = rows.map(item => `
      <div class="portability-backup-row">
        <div><strong>${escapePortabilityHtml(item.name)}</strong><br><small>${item.group === "automatic" ? "Автоматическая" : "Ручная"}</small></div>
        <small>${escapePortabilityHtml(formatPortableDate(item.modifiedAt))}</small>
        <small>${escapePortabilityHtml(formatBytes(item.size))}</small>
        <button type="button" class="secondary" data-backup-id="${escapePortabilityHtml(item.id)}">Проверить</button>
      </div>`).join("");
  }

  async function refreshStatus() {
    try {
      const response = await fetch(`/api/portability/status?t=${Date.now()}`, { cache: "no-store" });
      const result = await responseJson(response);
      schemaBadge.textContent = `Схема ${result.backupSchemaVersion}`;
      fileCount.textContent = result.userFileCount ?? "—";
      dataSize.textContent = formatBytes(result.userDataSize);
      const backups = Array.isArray(result.backups) ? result.backups : [];
      lastBackup.textContent = backups.length ? formatPortableDate(backups[0].modifiedAt) : "Ещё не создавался";
      renderBackups(backups);
    } catch (error) {
      backupsList.innerHTML = `<div class="empty-cell">Не удалось загрузить список: ${escapePortabilityHtml(error.message)}</div>`;
    }
  }

  async function stageLocalBackup(id) {
    if (!id || busy) return;
    stagedToken = "";
    setBusy(true, "Проверяю локальную резервную копию...");
    try {
      const response = await fetch("/api/portability/stage-local-backup", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id })
      });
      const result = await responseJson(response);
      stagedToken = result.token;
      renderPreview(result.preview || {});
    } catch (error) {
      clearPreview();
      alert(`Не удалось проверить бэкап: ${error.message}`);
    } finally {
      setBusy(false);
    }
  }

  async function applyImport() {
    if (!stagedToken || busy) return;
    const action = stagedKind === "donationalerts" ? "обновить TopDonation" : "применить выбранные данные";
    if (!confirm(`Создать автоматический бэкап и ${action}?`)) return;
    setBusy(true, "Создаю автоматический бэкап и применяю данные...");
    try {
      const response = await fetch("/api/portability/apply", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          token: stagedToken,
          options: {
            includeInGoal: includeGoal.checked,
            selectedKeys: stagedKind === "donationalerts" ? [...selectedDaKeys] : undefined
          }
        })
      });
      const result = await responseJson(response);
      const backupName = result.automaticBackup ? `\nРезервная копия: ${result.automaticBackup}` : "";
      const restartText = result.restartRequired ? "\nПерезапусти VicDonationGoal, чтобы все перенесённые подключения и модули перечитали настройки." : "";
      alert(`Готово. Данные применены.${backupName}${restartText}`);
      clearPreview();
      await refreshStatus();
      if (typeof refreshAll === "function") await refreshAll();
      if (typeof refreshTop === "function") await refreshTop(true);
      if (typeof refreshStatuses === "function") await refreshStatuses();
    } catch (error) {
      alert(`Импорт не выполнен: ${error.message}`);
    } finally {
      setBusy(false);
    }
  }

  backupInput?.addEventListener("change", () => stageRawFile("backup", backupInput.files?.[0]));
  donationsInput?.addEventListener("change", () => stageRawFile("donations", donationsInput.files?.[0]));
  donationAlertsInput?.addEventListener("change", () => stageRawFile("donationalerts", donationAlertsInput.files?.[0]));
  folderInput?.addEventListener("change", () => stageOldFolder(folderInput.files));
  applyButton?.addEventListener("click", applyImport);
  cancelButton?.addEventListener("click", clearPreview);
  refreshButton?.addEventListener("click", refreshStatus);
  downloadButton?.addEventListener("click", () => setTimeout(refreshStatus, 1200));
  backupsList?.addEventListener("click", event => {
    const button = event.target.closest("button[data-backup-id]");
    if (button) stageLocalBackup(button.dataset.backupId);
  });
  previewItems?.addEventListener("change", event => {
    const input = event.target.closest("input[data-da-import-key]");
    if (!input) return;
    if (input.checked) selectedDaKeys.add(input.dataset.daImportKey);
    else selectedDaKeys.delete(input.dataset.daImportKey);
    updateDaSelectionSummary();
  });

  applyButton.disabled = true;
  refreshStatus();
})();
