const state = {
  settings: null,
  status: null,
  accountStatuses: [],
  recentSnapshots: [],
  hasCaptureHistory: false,
  currentPreview: null,
  selectedVideoIdsByAccount: new Map(),
  selectedVideoId: "",
  windowRows: [],
  isCapturing: false,
  hasInitializedChartWindow: false,
  dashboardRefreshTimer: null,
  settingsSaveTimer: null,
  accountDialog: null,
};

const metricLabels = {
  playCount: "播放量",
  likeCount: "点赞量",
  commentCount: "评论量",
  shareCount: "分享量",
  followCount: "关注量",
};

const chartMetrics = ["playCount", "likeCount", "commentCount", "shareCount", "followCount"];

const el = {
  refreshAllButton: document.getElementById("refresh-all-button"),
  exportButton: document.getElementById("export-button"),
  lastError: document.getElementById("last-error"),
  recentSnapshots: document.getElementById("recent-snapshots"),
  settingsForm: document.getElementById("settings-form"),
  pollInterval: document.getElementById("poll-interval"),
  compareWindow: document.getElementById("compare-window"),
  retentionDays: document.getElementById("retention-days"),
  targetUrl: document.getElementById("target-url"),
  accountsList: document.getElementById("accounts-list"),
  addAccountButton: document.getElementById("add-account-button"),
  requestTimeout: document.getElementById("request-timeout"),
  saveStatus: document.getElementById("save-status"),
  selectionBackdrop: document.getElementById("selection-backdrop"),
  selectionPanel: document.getElementById("selection-panel"),
  selectionAccount: document.getElementById("selection-account"),
  selectionStatus: document.getElementById("selection-status"),
  selectionSummary: document.getElementById("selection-summary"),
  videoSelectionList: document.getElementById("video-selection-list"),
  selectAllVideos: document.getElementById("select-all-videos"),
  confirmSelection: document.getElementById("confirm-selection"),
  cancelSelection: document.getElementById("cancel-selection"),
  selectionClose: document.getElementById("selection-close"),
  windowMinutes: document.getElementById("window-minutes"),
  videoSelect: document.getElementById("video-select"),
  chartTitle: document.getElementById("chart-title"),
  chartMeta: document.getElementById("chart-meta"),
  summaryMeta: document.getElementById("summary-meta"),
  summaryBody: document.getElementById("summary-body"),
  chartList: document.getElementById("chart-list"),
  accountBackdrop: document.getElementById("account-backdrop"),
  accountPanel: document.getElementById("account-panel"),
  accountPanelTitle: document.getElementById("account-panel-title"),
  accountPanelStatus: document.getElementById("account-panel-status"),
  accountCookie: document.getElementById("account-cookie"),
  accountName: document.getElementById("account-name"),
  accountId: document.getElementById("account-id"),
  resolveAccount: document.getElementById("resolve-account"),
  saveAccount: document.getElementById("save-account"),
  cancelAccount: document.getElementById("cancel-account"),
};

function formatTimestamp(value) {
  if (!value) {
    return "未记录";
  }
  if (typeof value === "string" && /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/.test(value)) {
    return value;
  }
  const parsed = parseDateTime(value);
  if (parsed === null) {
    return String(value);
  }
  return formatDateParts(new Date(parsed));
}

function parseDateTime(value) {
  if (!value && value !== 0) {
    return null;
  }
  if (typeof value === "number") {
    return Number.isFinite(value) ? value : null;
  }
  if (typeof value !== "string") {
    return null;
  }
  const text = value.trim();
  if (!text) {
    return null;
  }
  if (/^\d+$/.test(text)) {
    return Number(text);
  }
  const match = text.match(/^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2}):(\d{2})$/);
  if (match) {
    const [, year, month, day, hour, minute, second] = match;
    return new Date(
      Number(year),
      Number(month) - 1,
      Number(day),
      Number(hour),
      Number(minute),
      Number(second),
    ).getTime();
  }
  const parsed = Date.parse(text);
  return Number.isNaN(parsed) ? null : parsed;
}

function formatDateParts(date) {
  const pad = (value) => String(value).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(
    date.getMinutes(),
  )}:${pad(date.getSeconds())}`;
}

function formatClock(value) {
  const parsed = parseDateTime(value);
  if (parsed === null) {
    return "";
  }
  const date = new Date(parsed);
  const pad = (part) => String(part).padStart(2, "0");
  return `${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function cleanVideoTitle(...candidates) {
  for (const candidate of candidates) {
    const rawText = String(candidate ?? "");
    const text = rawText.trim();
    if (!text) {
      continue;
    }
    const plain = text.split("#", 1)[0].trim();
    return plain || rawText;
  }
  return "";
}

function formatNumber(value) {
  return Number.isInteger(value) ? value.toLocaleString() : Number(value || 0).toFixed(2);
}

function formatDelta(value) {
  const sign = value > 0 ? "+" : "";
  return `${sign}${formatNumber(value)}`;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function setLastError(message = "") {
  const text = String(message || "").trim();
  el.lastError.textContent = text;
  el.lastError.hidden = !text;
}

async function apiGet(path) {
  const response = await fetch(path);
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.error || "请求失败");
  }
  return payload;
}

async function apiPost(path, data = {}) {
  const response = await fetch(path, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(data),
  });
  const payload = await response.json();
  if (!response.ok || payload.ok === false) {
    throw new Error(payload.error || payload.message || "请求失败");
  }
  return payload;
}

function createAccountKey() {
  return `account-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

function getSettingsAccounts(settings) {
  const accounts = settings?.accounts || [];
  if (accounts.length) {
    return accounts;
  }
  if (settings?.sessionCookie || settings?.accountLabelHint || settings?.selectedVideoIds?.length) {
    return [
      {
        key: "default",
        accountId: settings.selectedAccountId || "",
        accountLabel: settings.selectedAccountLabel || "",
        sessionCookie: settings.sessionCookie || "",
        accountLabelHint: settings.accountLabelHint || "",
        selectedVideoIds: settings.selectedVideoIds || [],
        captureEnabled: true,
      },
    ];
  }
  return [];
}

function getAccountStatus(account) {
  return (state.accountStatuses || []).find((item) => item.accountKey === account.key) || null;
}

function getSavedAccount(accountKey) {
  return (state.settings?.accounts || []).find((item) => item.key === accountKey) || null;
}

function getAccountSelectedCount(account, status) {
  return Number(status?.selectedVideoCount ?? account.selectedVideoIds?.length ?? 0);
}

function getAccountStatusText(account, status) {
  if (status?.statusText) {
    return status.statusText;
  }
  const selectedCount = getAccountSelectedCount(account, status);
  if (!selectedCount) {
    return "未选择视频";
  }
  return account.captureEnabled === false ? "已暂停" : "后台采集中";
}

function getAccountActionLabel(account, status) {
  const selectedCount = getAccountSelectedCount(account, status);
  if (!selectedCount) {
    return "选择视频";
  }
  return account.captureEnabled === false ? "恢复采集" : "暂停采集";
}

function getAccountDisplayName(account, status, index) {
  return status?.accountLabel || account.accountLabel || account.accountLabelHint || `账号 ${index + 1}`;
}

function createAccountEditor(account = {}, index = 0) {
  const wrapper = document.createElement("div");
  wrapper.className = "account-editor";
  wrapper.dataset.accountKey = account.key || createAccountKey();
  const status = getAccountStatus(account);
  const selectedCount = getAccountSelectedCount(account, status);
  const statusText = getAccountStatusText(account, status);
  const actionLabel = getAccountActionLabel(account, status);
  const lastCapturedAt = status?.lastCapturedAt || "未记录";
  const captureEnabled = account.captureEnabled !== false;
  const disabled = state.isCapturing ? "disabled" : "";
  const displayName = getAccountDisplayName(account, status, index);
  wrapper.innerHTML = `
    <div class="account-editor-head">
      <div class="account-editor-identity">
        <div class="account-editor-title" title="${escapeHtml(displayName)}">${escapeHtml(displayName)}</div>
        <div class="account-status-pill">${escapeHtml(statusText)}</div>
      </div>
      <div class="account-status-grid">
        <div><span>已选视频</span><strong>${selectedCount} 条</strong></div>
        <div><span>最近采集</span><strong>${escapeHtml(lastCapturedAt)}</strong></div>
        <div><span>运行状态</span><strong>${escapeHtml(statusText)}</strong></div>
      </div>
      <div class="account-actions">
        <button type="button" class="${selectedCount && captureEnabled ? "secondary" : "primary"} account-capture-action" ${disabled}>${escapeHtml(actionLabel)}</button>
        ${selectedCount ? `<button type="button" class="ghost account-select-videos" ${disabled}>重新选择</button>` : ""}
        <button type="button" class="ghost account-edit" ${disabled}>编辑</button>
        <button type="button" class="ghost account-remove" ${disabled}>删除</button>
      </div>
    </div>
  `;
  wrapper.querySelector(".account-edit").addEventListener("click", () => {
    openAccountPanel(account);
  });
  wrapper.querySelector(".account-remove").addEventListener("click", async () => {
    const accountKey = wrapper.dataset.accountKey;
    if (!getSavedAccount(accountKey)) {
      wrapper.remove();
      renumberAccountEditors();
      return;
    }
    if (state.isCapturing) {
      return;
    }
    const removeButton = wrapper.querySelector(".account-remove");
    removeButton.disabled = true;
    try {
      await apiPost("/api/accounts/delete", { accountKey });
      el.saveStatus.textContent = "账号已删除。";
      setLastError();
      await refreshAll();
    } catch (error) {
      removeButton.disabled = false;
      setLastError(error.message);
    }
  });
  wrapper.querySelector(".account-capture-action").addEventListener("click", async () => {
    await handleAccountCaptureAction(wrapper.dataset.accountKey, account, status);
  });
  wrapper.querySelector(".account-select-videos")?.addEventListener("click", async () => {
    await beginCaptureSetup(wrapper.dataset.accountKey);
  });
  return wrapper;
}

function renumberAccountEditors() {
  el.accountsList.querySelectorAll(".account-editor").forEach((editor, index) => {
    const title = editor.querySelector(".account-editor-title");
    const existingAccount = (state.settings?.accounts || []).find((item) => item.key === editor.dataset.accountKey);
    if (title) {
      const displayName = getAccountDisplayName(existingAccount || {}, getAccountStatus(existingAccount || {}), index);
      title.textContent = displayName;
      title.title = displayName;
    }
  });
}

function renderAccountEditors(accounts) {
  el.accountsList.innerHTML = "";
  if (!accounts.length) {
    el.accountsList.innerHTML = '<div class="empty">暂无账号</div>';
    return;
  }
  accounts.forEach((account, index) => {
    el.accountsList.appendChild(createAccountEditor(account, index));
  });
}

function setModalOpen() {
  const hasOpenModal = !el.selectionPanel.hidden || !el.accountPanel.hidden;
  document.body.classList.toggle("modal-open", hasOpenModal);
}

function getBasicSettingsPayload() {
  return {
    pollIntervalMinutes: Number(el.pollInterval.value || 1),
    defaultCompareWindowMinutes: Number(el.compareWindow.value || 5),
    retentionDays: Number(el.retentionDays.value || 30),
    targetUrl: el.targetUrl.value,
    requestTimeoutSeconds: Number(el.requestTimeout.value || 20),
  };
}

async function saveBasicSettings({ quiet = false } = {}) {
  const response = await apiPost("/api/settings/basic", getBasicSettingsPayload());
  state.settings = response.settings;
  if (!quiet) {
    el.saveStatus.textContent = `采集设置已保存：${new Date().toLocaleString()}`;
  }
  return response;
}

function scheduleSettingsSave() {
  if (state.settingsSaveTimer) {
    clearTimeout(state.settingsSaveTimer);
  }
  el.saveStatus.textContent = "采集设置待保存...";
  state.settingsSaveTimer = setTimeout(() => {
    state.settingsSaveTimer = null;
    saveBasicSettings().catch((error) => {
      el.saveStatus.textContent = error.message;
    });
  }, 600);
}

function openAccountPanel(account = null) {
  state.accountDialog = {
    key: account?.key || createAccountKey(),
    selectedVideoIds: account?.selectedVideoIds || [],
    captureEnabled: account?.captureEnabled ?? true,
  };
  el.accountPanelTitle.textContent = account ? "编辑账号" : "添加账号";
  el.accountPanelStatus.textContent = "填写 Cookie 后读取账号名。";
  el.accountCookie.value = account?.sessionCookie || "";
  el.accountName.value = account?.accountLabelHint || account?.accountLabel || "";
  el.accountId.value = account?.accountId || "";
  el.accountBackdrop.hidden = false;
  el.accountPanel.hidden = false;
  setModalOpen();
  setTimeout(() => el.accountCookie.focus(), 0);
}

function closeAccountPanel() {
  state.accountDialog = null;
  el.accountBackdrop.hidden = true;
  el.accountPanel.hidden = true;
  el.accountCookie.value = "";
  el.accountName.value = "";
  el.accountId.value = "";
  el.accountPanelStatus.textContent = "";
  setModalOpen();
}

function readAccountPanelAccount() {
  const existing = getSavedAccount(state.accountDialog?.key);
  return {
    key: state.accountDialog?.key || createAccountKey(),
    accountId: el.accountId.value.trim(),
    accountLabel: el.accountName.value.trim(),
    accountLabelHint: el.accountName.value.trim(),
    sessionCookie: el.accountCookie.value.trim(),
    selectedVideoIds: state.accountDialog?.selectedVideoIds || existing?.selectedVideoIds || [],
    captureEnabled: state.accountDialog?.captureEnabled ?? existing?.captureEnabled ?? true,
  };
}

function setAccountPanelBusy(isBusy) {
  el.resolveAccount.disabled = isBusy;
  el.saveAccount.disabled = isBusy;
  el.cancelAccount.disabled = isBusy;
}

async function resolveAccountFromPanel() {
  const account = readAccountPanelAccount();
  if (!account.sessionCookie) {
    el.accountPanelStatus.textContent = "请先填写账号 Cookie。";
    el.accountCookie.focus();
    return null;
  }
  setAccountPanelBusy(true);
  el.accountPanelStatus.textContent = "正在获取账号名...";
  try {
    const response = await apiPost("/api/accounts/resolve", { account });
    const resolvedAccount = response.account || {};
    if (resolvedAccount.accountLabel) {
      el.accountName.value = resolvedAccount.accountLabel;
    }
    if (resolvedAccount.accountId) {
      el.accountId.value = resolvedAccount.accountId;
    }
    el.accountPanelStatus.textContent = response.message || "账号名已同步。";
    if (!response.resolved) {
      el.accountName.focus();
    }
    return response;
  } catch (error) {
    el.accountPanelStatus.textContent = error.message;
    el.accountName.focus();
    return null;
  } finally {
    setAccountPanelBusy(false);
  }
}

async function saveAccountFromPanel() {
  let account = readAccountPanelAccount();
  if (!account.sessionCookie) {
    el.accountPanelStatus.textContent = "请先填写账号 Cookie。";
    el.accountCookie.focus();
    return;
  }
  if (!account.accountLabel) {
    const resolved = await resolveAccountFromPanel();
    account = readAccountPanelAccount();
    if (!resolved?.resolved && !account.accountLabel) {
      el.accountPanelStatus.textContent = resolved?.message || "请填写账号名称后再保存。";
      el.accountName.focus();
      return;
    }
  }
  setAccountPanelBusy(true);
  el.accountPanelStatus.textContent = "正在保存账号...";
  try {
    const response = await apiPost("/api/accounts/save", { account });
    state.settings = response.settings;
    closeAccountPanel();
    el.saveStatus.textContent = response.accountResolveWarnings?.length
      ? `账号已保存：${response.accountResolveWarnings.join("；")}`
      : "账号已保存。";
    setLastError();
    await refreshAll();
  } catch (error) {
    el.accountPanelStatus.textContent = error.message;
    el.accountName.focus();
  } finally {
    setAccountPanelBusy(false);
  }
}

function clearManualNameHints() {
  el.accountsList.querySelectorAll(".account-editor.manual-name-required").forEach((editor) => {
    editor.classList.remove("manual-name-required");
    const input = editor.querySelector('input[data-field="accountLabelHint"]');
    if (input) {
      input.required = false;
    }
  });
}

function requestManualAccountNames(accountKeys = []) {
  clearManualNameHints();
  const keys = new Set(accountKeys);
  let firstInput = null;
  el.accountsList.querySelectorAll(".account-editor").forEach((editor) => {
    if (!keys.has(editor.dataset.accountKey)) {
      return;
    }
    editor.classList.add("manual-name-required");
    const detail = editor.querySelector(".account-detail");
    const input = editor.querySelector('input[data-field="accountLabelHint"]');
    if (detail) {
      detail.open = true;
    }
    if (input) {
      input.required = true;
      input.placeholder = "请填写账号名称";
      firstInput ||= input;
    }
  });
  firstInput?.focus();
}

function addAccountEditor(account = {}) {
  const index = el.accountsList.querySelectorAll(".account-editor").length;
  el.accountsList.appendChild(createAccountEditor(account, index));
}

async function handleAccountCaptureAction(accountKey, account, status) {
  if (state.isCapturing) {
    return;
  }
  const savedAccount = getSavedAccount(accountKey);
  if (!savedAccount) {
    setLastError("请先保存账号配置，再选择视频或控制采集。");
    return;
  }
  const selectedCount = getAccountSelectedCount(account, status);
  if (!selectedCount) {
    await beginCaptureSetup(accountKey);
    return;
  }
  state.isCapturing = true;
  renderAccountEditors(getSettingsAccounts(state.settings));
  try {
    await apiPost("/api/accounts/capture-enabled", {
      accountKey,
      enabled: savedAccount.captureEnabled === false,
    });
    await refreshAll();
  } catch (error) {
    setLastError(error.message);
  } finally {
    state.isCapturing = false;
    renderAccountEditors(getSettingsAccounts(state.settings));
  }
}

function collectAccountSettings() {
  return Array.from(el.accountsList.querySelectorAll(".account-editor"))
    .map((editor) => {
      const field = (name) => editor.querySelector(`[data-field="${name}"]`)?.value?.trim() || "";
      const existingAccount = (state.settings?.accounts || []).find((item) => item.key === editor.dataset.accountKey);
      return {
        key: editor.dataset.accountKey || createAccountKey(),
        accountId: field("accountId"),
        accountLabel: existingAccount?.accountLabel || "",
        accountLabelHint: field("accountLabelHint"),
        sessionCookie: field("sessionCookie"),
        selectedVideoIds: existingAccount?.selectedVideoIds || [],
        captureEnabled: existingAccount?.captureEnabled ?? true,
      };
    })
    .filter((account) => account.sessionCookie);
}

function renderSettings() {
  if (!state.settings) {
    return;
  }
  el.pollInterval.value = state.settings.pollIntervalMinutes;
  el.compareWindow.value = state.settings.defaultCompareWindowMinutes;
  el.retentionDays.value = state.settings.retentionDays;
  el.targetUrl.value = state.settings.targetUrl;
  el.requestTimeout.value = state.settings.requestTimeoutSeconds || 20;
  renderAccountEditors(getSettingsAccounts(state.settings));
  if (!state.hasInitializedChartWindow) {
    el.windowMinutes.value = state.settings.defaultCompareWindowMinutes;
    state.hasInitializedChartWindow = true;
  }
}

function renderRecentSnapshots() {
  if (!state.recentSnapshots.length) {
    el.recentSnapshots.innerHTML = '<div class="empty">暂无采集数据</div>';
    return;
  }
  el.recentSnapshots.innerHTML = state.recentSnapshots
    .map(
      (row) => `
        <div class="snapshot-item">
          <div class="snapshot-title">${escapeHtml(cleanVideoTitle(row.description, row.videoTitle, row.videoId))}</div>
          <div class="snapshot-meta">账号：${escapeHtml(row.accountLabel || "-")}</div>
          <div class="snapshot-meta">采集时间：${escapeHtml(formatTimestamp(row.capturedAt))}</div>
          <div class="snapshot-meta">videoId：${escapeHtml(row.videoId)}</div>
          <div class="snapshot-metrics">
            播放 ${formatNumber(row.metrics.playCount)} / 点赞 ${formatNumber(row.metrics.likeCount)} / 评论 ${formatNumber(row.metrics.commentCount)} / 分享 ${formatNumber(row.metrics.shareCount)}
          </div>
        </div>
      `,
    )
    .join("");
}

function hideSelectionPanel() {
  state.currentPreview = null;
  state.selectedVideoIdsByAccount = new Map();
  el.selectionPanel.hidden = true;
  el.selectionBackdrop.hidden = true;
  setModalOpen();
  el.videoSelectionList.innerHTML = '<div class="empty">等待读取近期视频...</div>';
  el.selectionStatus.textContent = "先读取近期视频，再选择本次要采集的内容。";
}

function defaultSelectedVideoIds(preview, account) {
  const previewIds = new Set(preview.videos.map((item) => item.videoId));
  const savedIds = account?.savedSelectedVideoIds || [];
  const preserved = savedIds.filter((item) => previewIds.has(item));
  return preserved.length ? preserved : preview.videos.map((item) => item.videoId);
}

function getSelectablePreviews() {
  return state.currentPreview?.previews?.filter((preview) => preview.ok && preview.videos.length) || [];
}

function getSelectionTotals() {
  const previews = getSelectablePreviews();
  const total = previews.reduce((sum, preview) => sum + preview.videos.length, 0);
  const selectedCount = previews.reduce(
    (sum, preview) => sum + (state.selectedVideoIdsByAccount.get(preview.accountKey)?.size || 0),
    0,
  );
  return { total, selectedCount };
}

function updateSelectionSummary() {
  const { total, selectedCount } = getSelectionTotals();
  el.selectionSummary.textContent = `已选择 ${selectedCount} / ${total} 条视频`;
  el.selectAllVideos.checked = total > 0 && selectedCount === total;
  el.selectAllVideos.indeterminate = selectedCount > 0 && selectedCount < total;
  el.confirmSelection.disabled = state.isCapturing || selectedCount === 0;
  el.cancelSelection.disabled = state.isCapturing;
  el.selectionClose.disabled = state.isCapturing;
}

function renderSelectionList() {
  if (!state.currentPreview) {
    return;
  }
  if (!state.currentPreview.previews?.length) {
    el.videoSelectionList.innerHTML = '<div class="empty">没有可读取的账号配置。</div>';
    updateSelectionSummary();
    return;
  }
  el.videoSelectionList.innerHTML = state.currentPreview.previews
    .map((preview) => {
      const accountKey = preview.accountKey;
      const selectedIds = state.selectedVideoIdsByAccount.get(accountKey) || new Set();
      const videosHtml = preview.ok && preview.videos.length
        ? preview.videos
            .map((video) => {
              const checked = selectedIds.has(video.videoId) ? "checked" : "";
              return `
                <label class="video-option">
                  <input type="checkbox" data-account-key="${escapeHtml(accountKey)}" data-video-id="${escapeHtml(video.videoId)}" ${checked} />
                  <div class="video-option-body">
                    <div class="video-option-title">${escapeHtml(cleanVideoTitle(video.description, video.title, video.videoId))}</div>
                    <div class="video-option-meta">发布时间：${escapeHtml(formatTimestamp(video.publishTime))}</div>
                    <div class="video-option-meta">videoId：${escapeHtml(video.videoId)}</div>
                    <div class="video-option-meta">
                      播放 ${formatNumber(video.metrics.playCount)} / 点赞 ${formatNumber(video.metrics.likeCount)} / 评论 ${formatNumber(video.metrics.commentCount)} / 分享 ${formatNumber(video.metrics.shareCount)}
                    </div>
                  </div>
                </label>
              `;
            })
            .join("")
        : `<div class="empty">${escapeHtml(preview.message || "当前账号没有可采集的视频。")}</div>`;
      return `
        <div class="selection-account-group">
          <div class="selection-account-head">
            <div>
              <div class="selection-account-title" title="${escapeHtml(preview.accountLabel || preview.accountKey || "未知账号")}">${escapeHtml(preview.accountLabel || preview.accountKey || "未知账号")}</div>
            </div>
            <span class="badge">${preview.ok ? `${preview.videos.length} 条视频` : "读取失败"}</span>
          </div>
          <div class="selection-account-videos">${videosHtml}</div>
        </div>
      `;
    })
    .join("");

  el.videoSelectionList.querySelectorAll('input[type="checkbox"][data-account-key][data-video-id]').forEach((checkbox) => {
    checkbox.addEventListener("change", () => {
      const accountKey = checkbox.dataset.accountKey;
      const videoId = checkbox.dataset.videoId;
      if (!accountKey || !videoId) {
        return;
      }
      const selectedIds = state.selectedVideoIdsByAccount.get(accountKey) || new Set();
      if (checkbox.checked) {
        selectedIds.add(videoId);
      } else {
        selectedIds.delete(videoId);
      }
      state.selectedVideoIdsByAccount.set(accountKey, selectedIds);
      updateSelectionSummary();
    });
  });
  updateSelectionSummary();
}

function showSelectionPanel(previewPayload) {
  state.currentPreview = previewPayload;
  state.selectedVideoIdsByAccount = new Map();
  (previewPayload.previews || []).forEach((preview) => {
    state.selectedVideoIdsByAccount.set(preview.accountKey, new Set(defaultSelectedVideoIds(preview, preview)));
  });
  el.selectionPanel.hidden = false;
  el.selectionBackdrop.hidden = false;
  setModalOpen();
  el.selectionAccount.textContent = `${previewPayload.previews?.length || 0} 个账号`;
  el.selectionStatus.textContent = "已按账号读取近期视频，请勾选本次要采集的内容。";
  renderSelectionList();
}

function renderVideoOptions(rows) {
  if (!rows.length) {
    state.selectedVideoId = "";
    el.videoSelect.innerHTML = '<option value="">暂无视频</option>';
    return;
  }
  if (!rows.some((row) => row.videoId === state.selectedVideoId)) {
    state.selectedVideoId = rows[0].videoId;
  }
  el.videoSelect.innerHTML = rows
    .map((row) => {
      const title = cleanVideoTitle(row.description, row.title, row.videoId);
      const accountPrefix = row.accountLabel ? `【${row.accountLabel}】` : "";
      return `<option value="${escapeHtml(row.videoId)}">${escapeHtml(`${accountPrefix}${title}`)}</option>`;
    })
    .join("");
  el.videoSelect.value = state.selectedVideoId;
}

function renderSummary(rows, windowMinutes) {
  if (!rows.length) {
    el.summaryBody.innerHTML = '<tr><td colspan="7" class="empty">暂无采集数据</td></tr>';
    el.summaryMeta.textContent = `${windowMinutes} 分钟窗口 · 0 个视频`;
    return;
  }

  el.summaryBody.innerHTML = rows
    .map((row) => {
      const metrics = row.delta;
      const cells = row.hasEnoughData
        ? `
          <td class="number">${formatDelta(metrics.playCount)}</td>
          <td class="number">${formatDelta(metrics.likeCount)}</td>
          <td class="number">${formatDelta(metrics.commentCount)}</td>
          <td class="number">${formatDelta(metrics.shareCount)}</td>
        `
        : '<td colspan="4" class="muted">数据不足</td>';
      return `
        <tr>
          <td>
            <div>${escapeHtml(cleanVideoTitle(row.description, row.title, row.videoId))}</div>
            <div class="muted">${escapeHtml(row.accountLabel || "-")}</div>
            <div class="muted">${escapeHtml(row.videoId)}</div>
          </td>
          ${cells}
          <td>${formatTimestamp(row.startSnapshot?.capturedAt)}</td>
          <td>${formatTimestamp(row.endSnapshot?.capturedAt)}</td>
        </tr>
      `;
    })
    .join("");
  el.summaryMeta.textContent = `${windowMinutes} 分钟窗口 · ${rows.length} 个视频`;
}

function createSvgElement(tagName, attributes = {}) {
  const element = document.createElementNS("http://www.w3.org/2000/svg", tagName);
  Object.entries(attributes).forEach(([name, value]) => {
    element.setAttribute(name, String(value));
  });
  return element;
}

function createCountAxis(values) {
  const rawMin = Math.min(0, ...values);
  const rawMax = Math.max(1, ...values);
  const span = Math.max(1, rawMax - rawMin);
  const roughStep = span / 4;
  const magnitude = 10 ** Math.floor(Math.log10(roughStep || 1));
  const normalized = roughStep / magnitude;
  const stepMultiplier = normalized <= 1 ? 1 : normalized <= 2 ? 2 : normalized <= 5 ? 5 : 10;
  const step = Math.max(1, stepMultiplier * magnitude);
  const minY = Math.floor(rawMin / step) * step;
  const maxY = Math.ceil(rawMax / step) * step;
  const ticks = [];
  for (let value = minY; value <= maxY + step / 2; value += step) {
    ticks.push(Math.round(value));
  }
  return { minY, maxY, ticks };
}

function createMetricChart(metric) {
  const card = document.createElement("div");
  card.className = "chart-card";

  const head = document.createElement("div");
  head.className = "chart-card-head";

  const title = document.createElement("h3");
  title.className = "chart-card-title";
  title.textContent = `${metricLabels[metric]}趋势`;

  const meta = document.createElement("p");
  meta.className = "chart-card-meta";

  const wrapper = document.createElement("div");
  wrapper.className = "chart-wrapper";

  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.classList.add("chart-svg");

  const empty = document.createElement("div");
  empty.className = "chart-empty";
  empty.textContent = "暂无数据";

  const tooltip = document.createElement("div");
  tooltip.className = "chart-tooltip";
  tooltip.hidden = true;

  head.append(title, meta);
  wrapper.append(svg, empty, tooltip);
  card.append(head, wrapper);

  return { card, title, meta, wrapper, svg, empty, tooltip };
}

function clearChart(chart) {
  while (chart.svg.firstChild) {
    chart.svg.removeChild(chart.svg.firstChild);
  }
  chart.tooltip.hidden = true;
}

function renderEmptyChart(chart, message) {
  clearChart(chart);
  chart.empty.hidden = false;
  chart.empty.textContent = message;
  chart.meta.textContent = "";
}

function renderEmptyChartList(message) {
  el.chartTitle.textContent = "指标趋势总览";
  el.chartMeta.textContent = "";
  el.chartList.innerHTML = "";
  chartMetrics.forEach((metric) => {
    const chart = createMetricChart(metric);
    el.chartList.appendChild(chart.card);
    renderEmptyChart(chart, message);
  });
}

function showChartTooltip(event, point, metric, chart) {
  const wrapperRect = chart.wrapper.getBoundingClientRect();
  chart.tooltip.textContent = `横轴：${formatTimestamp(point.capturedAt || point.timestamp)}\n纵轴：${metricLabels[metric]} ${formatNumber(point.value)}\n增长：${formatDelta(point.growth || 0)}`;
  chart.tooltip.hidden = false;
  const left = Math.min(Math.max(event.clientX - wrapperRect.left + 12, 8), wrapperRect.width - chart.tooltip.offsetWidth - 8);
  const top = Math.min(Math.max(event.clientY - wrapperRect.top - chart.tooltip.offsetHeight - 12, 8), wrapperRect.height - chart.tooltip.offsetHeight - 8);
  chart.tooltip.style.left = `${left}px`;
  chart.tooltip.style.top = `${top}px`;
}

function hideChartTooltip(chart) {
  chart.tooltip.hidden = true;
}

function findNearestPoint(points, targetTimestamp) {
  if (!points.length) {
    return null;
  }
  let nearest = points[0];
  let minDistance = Math.abs(points[0].capturedAtMs - targetTimestamp);
  for (let index = 1; index < points.length; index += 1) {
    const point = points[index];
    const distance = Math.abs(point.capturedAtMs - targetTimestamp);
    if (distance < minDistance) {
      nearest = point;
      minDistance = distance;
    }
  }
  return nearest;
}

function getChartViewportWidth(svg) {
  const svgWidth = svg.getBoundingClientRect().width;
  const wrapperWidth = svg.parentElement?.getBoundingClientRect().width || 0;
  const width = Math.round(svgWidth || wrapperWidth || 920);
  return Math.max(320, width);
}

function renderLineChart(points, metric, chart) {
  const normalizedPoints = points
    .map((point) => ({
      ...point,
      capturedAtLabel: point.capturedAt || point.timestamp,
      capturedAtMs: parseDateTime(point.capturedAt || point.timestamp),
    }))
    .filter((point) => point.capturedAtMs !== null)
    .map((point, index, items) => {
      const value = Number(point.value || 0);
      const previousValue = index > 0 ? Number(items[index - 1].value || 0) : value;
      return {
        ...point,
        value,
        growth: Number(point.growth ?? value - previousValue),
      };
    });

  if (normalizedPoints.length < 2) {
    chart.title.textContent = `${metricLabels[metric]}趋势`;
    renderEmptyChart(chart, "当前周期下可用节点不足，至少需要两个满足周期间隔的采集点才能显示趋势。");
    return;
  }

  clearChart(chart);
  chart.empty.hidden = true;
  chart.title.textContent = `${metricLabels[metric]}趋势`;
  chart.meta.textContent = `${formatTimestamp(normalizedPoints[0].capturedAtLabel)} 至 ${formatTimestamp(normalizedPoints[normalizedPoints.length - 1].capturedAtLabel)} · ${normalizedPoints.length} 个点`;

  const width = getChartViewportWidth(chart.svg);
  const height = 340;
  const margin = { top: 28, right: 4, bottom: 48, left: 40 };
  const innerWidth = width - margin.left - margin.right;
  const innerHeight = height - margin.top - margin.bottom;
  const minX = normalizedPoints[0].capturedAtMs;
  const maxX = normalizedPoints[normalizedPoints.length - 1].capturedAtMs;
  const values = normalizedPoints.map((point) => point.value);
  const { minY, maxY, ticks } = createCountAxis(values);

  const xScale = (value) => margin.left + ((value - minX) / Math.max(1, maxX - minX)) * innerWidth;
  const yScale = (value) => margin.top + (1 - (value - minY) / Math.max(1, maxY - minY)) * innerHeight;
  const chartPoints = normalizedPoints.map((point) => ({
    ...point,
    chartX: xScale(point.capturedAtMs),
    chartY: yScale(point.value),
  }));

  chart.svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
  chart.svg.appendChild(createSvgElement("rect", { x: 0, y: 0, width, height, fill: "#ffffff" }));

  ticks.forEach((tick) => {
    const y = yScale(tick);
    chart.svg.appendChild(createSvgElement("line", { x1: margin.left, y1: y, x2: width - margin.right, y2: y, stroke: "#e7ebf2" }));
    const label = createSvgElement("text", { x: margin.left - 8, y: y + 4, "text-anchor": "end", fill: "#667085", "font-size": 12 });
    label.textContent = Math.round(tick).toLocaleString();
    chart.svg.appendChild(label);
  });

  const tickIndexes = Array.from(
    new Set([0, Math.floor((normalizedPoints.length - 1) / 2), normalizedPoints.length - 1]),
  );
  tickIndexes.forEach((index, tickPosition) => {
    const point = chartPoints[index];
    const x = point.chartX;
    chart.svg.appendChild(createSvgElement("line", { x1: x, y1: margin.top, x2: x, y2: height - margin.bottom, stroke: "#f1f3f7" }));
    const textAnchor = tickPosition === tickIndexes.length - 1 ? "end" : "middle";
    const label = createSvgElement("text", { x, y: height - 14, "text-anchor": textAnchor, fill: "#667085", "font-size": 12 });
    label.textContent = formatClock(point.capturedAtLabel);
    chart.svg.appendChild(label);
  });

  const pathData = chartPoints
    .map((point, index) => `${index === 0 ? "M" : "L"} ${point.chartX.toFixed(2)} ${point.chartY.toFixed(2)}`)
    .join(" ");
  const areaData = `${pathData} L ${chartPoints[chartPoints.length - 1].chartX.toFixed(2)} ${height - margin.bottom} L ${chartPoints[0].chartX.toFixed(2)} ${height - margin.bottom} Z`;
  chart.svg.appendChild(createSvgElement("path", { d: areaData, fill: "#d5f5f1", opacity: 0.9 }));
  chart.svg.appendChild(createSvgElement("path", { d: pathData, fill: "none", stroke: "#0f766e", "stroke-width": 3, "stroke-linejoin": "round" }));

  const visibleStep = Math.max(1, Math.ceil(normalizedPoints.length / 60));
  chartPoints.forEach((point, index) => {
    if (index % visibleStep === 0 || index === normalizedPoints.length - 1) {
      chart.svg.appendChild(createSvgElement("circle", { cx: point.chartX, cy: point.chartY, r: 3.5, fill: "#ef6c45", stroke: "#ffffff", "stroke-width": 2 }));
    }
  });

  const hoverRect = createSvgElement("rect", {
    x: 0,
    y: 0,
    width,
    height,
    fill: "#ffffff",
    opacity: 0,
    cursor: "crosshair",
    "pointer-events": "all",
  });
  const hoverGuide = createSvgElement("line", {
    x1: margin.left,
    y1: margin.top,
    x2: margin.left,
    y2: height - margin.bottom,
    stroke: "#ef6c45",
    "stroke-width": 1.5,
    "stroke-dasharray": "4 4",
    opacity: 0,
    "pointer-events": "none",
  });
  const hoverMarker = createSvgElement("circle", {
    cx: margin.left,
    cy: margin.top,
    r: 5,
    fill: "#ef6c45",
    stroke: "#ffffff",
    "stroke-width": 2,
    opacity: 0,
    "pointer-events": "none",
  });
  const setHoverVisible = (visible) => {
    const opacity = visible ? "1" : "0";
    hoverGuide.setAttribute("opacity", opacity);
    hoverMarker.setAttribute("opacity", opacity);
  };
  const hideHoverState = () => {
    hideChartTooltip(chart);
    setHoverVisible(false);
  };
  const updateHoverState = (event) => {
    const svgRect = chart.svg.getBoundingClientRect();
    const relativeX = ((event.clientX - svgRect.left) / Math.max(1, svgRect.width)) * width;
    const clampedX = Math.min(width - margin.right, Math.max(margin.left, relativeX));
    const ratio = (clampedX - margin.left) / Math.max(1, innerWidth);
    const targetTimestamp = minX + ratio * Math.max(1, maxX - minX);
    const point = findNearestPoint(chartPoints, targetTimestamp);
    if (!point) {
      hideHoverState();
      return;
    }

    hoverGuide.setAttribute("x1", point.chartX.toFixed(2));
    hoverGuide.setAttribute("x2", point.chartX.toFixed(2));
    hoverMarker.setAttribute("cx", point.chartX.toFixed(2));
    hoverMarker.setAttribute("cy", point.chartY.toFixed(2));
    setHoverVisible(true);
    showChartTooltip(event, point, metric, chart);
  };

  hoverRect.addEventListener("pointermove", updateHoverState);
  hoverRect.addEventListener("pointerleave", hideHoverState);

  chart.svg.appendChild(hoverRect);
  chart.svg.appendChild(hoverGuide);
  chart.svg.appendChild(hoverMarker);
}

async function refreshDashboard() {
  const windowMinutes = Math.max(1, Number(el.windowMinutes.value || 5));
  const payload = await apiGet(`/api/window-stats?windowMinutes=${windowMinutes}`);
  state.windowRows = payload.rows || [];
  renderVideoOptions(state.windowRows);
  renderSummary(state.windowRows, windowMinutes);

  const row = state.windowRows.find((item) => item.videoId === state.selectedVideoId);
  if (!row) {
    renderEmptyChartList("暂无可展示的视频。");
    return;
  }

  el.chartTitle.textContent = "指标趋势总览";
  el.chartMeta.textContent = `${windowMinutes} 分钟周期`;
  const trendResults = await Promise.all(
    chartMetrics.map(async (metric) => {
      const trend = await apiGet(
        `/api/trend?videoId=${encodeURIComponent(state.selectedVideoId)}&metric=${encodeURIComponent(metric)}&windowMinutes=${windowMinutes}`,
      );
      return { metric, points: trend.points || [] };
    }),
  );

  el.chartList.innerHTML = "";
  trendResults.forEach(({ metric, points }) => {
    const chart = createMetricChart(metric);
    el.chartList.appendChild(chart.card);
    renderLineChart(points, metric, chart);
  });
}

function scheduleDashboardRefresh() {
  if (state.dashboardRefreshTimer) {
    clearTimeout(state.dashboardRefreshTimer);
  }
  state.dashboardRefreshTimer = setTimeout(() => {
    state.dashboardRefreshTimer = null;
    refreshDashboard().catch((error) => {
      setLastError(error.message);
    });
  }, 300);
}

async function refreshBootstrap() {
  const activeElement = document.activeElement;
  const shouldSyncForm =
    !activeElement ||
    !["INPUT", "TEXTAREA", "SELECT"].includes(activeElement.tagName) ||
    activeElement.form !== el.settingsForm;
  const payload = await apiGet("/api/bootstrap");
  state.status = payload.status;
  state.settings = payload.settings;
  state.accountStatuses = payload.accountStatuses || [];
  state.recentSnapshots = payload.recentSnapshots || [];
  state.hasCaptureHistory = Boolean(payload.hasCaptureHistory);
  setLastError(state.status?.lastError);
  if (shouldSyncForm) {
    renderSettings();
  }
  renderRecentSnapshots();
}

async function refreshAll() {
  await refreshBootstrap();
  await refreshDashboard();
}

async function beginCaptureSetup(accountKey = null) {
  if (accountKey && !getSavedAccount(accountKey)) {
    setLastError("请先保存账号配置，再选择视频。");
    return;
  }
  state.isCapturing = true;
  renderAccountEditors(getSettingsAccounts(state.settings));
  setLastError("正在读取账号和近期视频...");
  try {
    const body = accountKey ? { accountKeys: [accountKey] } : {};
    const response = await apiPost("/api/capture/prepare", body);
    showSelectionPanel(response);
    setLastError();
  } catch (error) {
    setLastError(error.message);
    hideSelectionPanel();
  } finally {
    state.isCapturing = false;
    renderAccountEditors(getSettingsAccounts(state.settings));
    updateSelectionSummary();
  }
}

el.refreshAllButton.addEventListener("click", async () => {
  await refreshAll();
});

el.addAccountButton.addEventListener("click", () => {
  openAccountPanel();
});

el.settingsForm.addEventListener("submit", async (event) => {
  event.preventDefault();
});

[el.pollInterval, el.compareWindow, el.retentionDays, el.targetUrl, el.requestTimeout].forEach((input) => {
  input.addEventListener("input", scheduleSettingsSave);
  input.addEventListener("change", () => {
    if (state.settingsSaveTimer) {
      clearTimeout(state.settingsSaveTimer);
      state.settingsSaveTimer = null;
    }
    saveBasicSettings().catch((error) => {
      el.saveStatus.textContent = error.message;
    });
  });
});

el.resolveAccount.addEventListener("click", resolveAccountFromPanel);
el.saveAccount.addEventListener("click", saveAccountFromPanel);
el.cancelAccount.addEventListener("click", closeAccountPanel);
el.accountBackdrop.addEventListener("click", closeAccountPanel);

el.selectAllVideos.addEventListener("change", () => {
  if (!state.currentPreview) {
    return;
  }
  if (el.selectAllVideos.checked) {
    getSelectablePreviews().forEach((preview) => {
      state.selectedVideoIdsByAccount.set(preview.accountKey, new Set(preview.videos.map((item) => item.videoId)));
    });
  } else {
    state.selectedVideoIdsByAccount = new Map();
  }
  renderSelectionList();
});

el.confirmSelection.addEventListener("click", async () => {
  const selectedAccounts = getSelectablePreviews()
    .map((preview) => ({
      accountKey: preview.accountKey,
      selectedVideoIds: Array.from(state.selectedVideoIdsByAccount.get(preview.accountKey) || []),
    }))
    .filter((item) => item.selectedVideoIds.length > 0);
  if (!state.currentPreview || state.isCapturing || selectedAccounts.length === 0) {
    return;
  }
  state.isCapturing = true;
  renderAccountEditors(getSettingsAccounts(state.settings));
  try {
    await apiPost("/api/capture/start", { accounts: selectedAccounts });
    hideSelectionPanel();
    await refreshAll();
  } catch (error) {
    el.selectionStatus.textContent = error.message;
    setLastError(error.message);
  } finally {
    state.isCapturing = false;
    renderAccountEditors(getSettingsAccounts(state.settings));
  }
});

el.cancelSelection.addEventListener("click", () => {
  hideSelectionPanel();
});

el.selectionClose.addEventListener("click", () => {
  if (!state.isCapturing) {
    hideSelectionPanel();
  }
});

el.selectionBackdrop.addEventListener("click", () => {
  if (!state.isCapturing) {
    hideSelectionPanel();
  }
});

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !el.accountPanel.hidden && !el.saveAccount.disabled) {
    closeAccountPanel();
    return;
  }
  if (event.key === "Escape" && !el.selectionPanel.hidden && !state.isCapturing) {
    hideSelectionPanel();
  }
});

el.windowMinutes.addEventListener("change", refreshDashboard);
el.windowMinutes.addEventListener("input", scheduleDashboardRefresh);
el.videoSelect.addEventListener("change", () => {
  state.selectedVideoId = el.videoSelect.value;
  refreshDashboard();
});

refreshAll().catch((error) => {
  setLastError(error.message);
});

setInterval(() => {
  refreshBootstrap().catch(() => undefined);
}, 15000);
