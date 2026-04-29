const state = {
  settings: null,
  status: null,
  recentSnapshots: [],
  hasCaptureHistory: false,
  currentPreview: null,
  selectedVideoIds: new Set(),
  selectedVideoId: "",
  windowRows: [],
  isCapturing: false,
};

const metricLabels = {
  playCount: "播放量",
  likeCount: "点赞量",
  commentCount: "评论量",
  shareCount: "分享量",
  followCount: "关注量",
};

const el = {
  captureButton: document.getElementById("capture-button"),
  runNowButton: document.getElementById("run-now-button"),
  refreshAllButton: document.getElementById("refresh-all-button"),
  exportButton: document.getElementById("export-button"),
  lastRun: document.getElementById("last-run"),
  lastSuccess: document.getElementById("last-success"),
  lastError: document.getElementById("last-error"),
  accountLabel: document.getElementById("account-label"),
  captureScope: document.getElementById("capture-scope"),
  recentSnapshots: document.getElementById("recent-snapshots"),
  settingsForm: document.getElementById("settings-form"),
  pollInterval: document.getElementById("poll-interval"),
  compareWindow: document.getElementById("compare-window"),
  retentionDays: document.getElementById("retention-days"),
  targetUrl: document.getElementById("target-url"),
  sessionCookie: document.getElementById("session-cookie"),
  accountLabelHint: document.getElementById("account-label-hint"),
  requestTimeout: document.getElementById("request-timeout"),
  saveStatus: document.getElementById("save-status"),
  selectionPanel: document.getElementById("selection-panel"),
  selectionAccount: document.getElementById("selection-account"),
  selectionStatus: document.getElementById("selection-status"),
  selectionSummary: document.getElementById("selection-summary"),
  videoSelectionList: document.getElementById("video-selection-list"),
  selectAllVideos: document.getElementById("select-all-videos"),
  confirmSelection: document.getElementById("confirm-selection"),
  cancelSelection: document.getElementById("cancel-selection"),
  windowMinutes: document.getElementById("window-minutes"),
  metricSelect: document.getElementById("metric-select"),
  videoSelect: document.getElementById("video-select"),
  chartTitle: document.getElementById("chart-title"),
  chartMeta: document.getElementById("chart-meta"),
  summaryMeta: document.getElementById("summary-meta"),
  summaryBody: document.getElementById("summary-body"),
  chartSvg: document.getElementById("trend-chart"),
  chartEmpty: document.getElementById("chart-empty"),
  chartTooltip: document.getElementById("chart-tooltip"),
};

function formatTimestamp(value) {
  return value ? new Date(value).toLocaleString() : "未记录";
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

function renderStatus() {
  el.lastRun.textContent = state.status?.lastMessage
    ? `${formatTimestamp(state.status.lastRunAt)}，${state.status.lastMessage}`
    : formatTimestamp(state.status?.lastRunAt);
  el.lastSuccess.textContent = formatTimestamp(state.status?.lastSuccessAt);
  el.lastError.textContent = state.status?.lastError || "无";
  el.accountLabel.textContent =
    state.status?.accountLabel || state.settings?.selectedAccountLabel || state.settings?.accountLabelHint || "未知";
  const selectedCount = state.settings?.selectedVideoIds?.length || 0;
  if (selectedCount > 0) {
    el.captureScope.textContent = `${state.settings?.selectedAccountLabel || "当前账号"} · 已选择 ${selectedCount} 条视频`;
  } else {
    el.captureScope.textContent = "尚未选择视频范围";
  }
}

function renderSettings() {
  if (!state.settings) {
    return;
  }
  el.pollInterval.value = state.settings.pollIntervalMinutes;
  el.compareWindow.value = state.settings.defaultCompareWindowMinutes;
  el.retentionDays.value = state.settings.retentionDays;
  el.targetUrl.value = state.settings.targetUrl;
  el.sessionCookie.value = state.settings.sessionCookie || "";
  el.accountLabelHint.value = state.settings.accountLabelHint || "";
  el.requestTimeout.value = state.settings.requestTimeoutSeconds || 20;
  el.windowMinutes.value = state.settings.defaultCompareWindowMinutes;
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
          <div class="snapshot-title">${escapeHtml(row.description || row.videoTitle || row.videoId)}</div>
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

function renderPrimaryButton() {
  const isPaused = Boolean(state.settings?.capturePaused);
  if (state.isCapturing) {
    el.captureButton.disabled = true;
    el.captureButton.textContent = "处理中...";
    return;
  }
  el.captureButton.disabled = false;
  if (isPaused) {
    el.captureButton.textContent = "恢复采集";
    return;
  }
  el.captureButton.textContent = state.hasCaptureHistory ? "暂停采集" : "开始采集";
}

function hideSelectionPanel() {
  state.currentPreview = null;
  state.selectedVideoIds = new Set();
  el.selectionPanel.hidden = true;
  el.videoSelectionList.innerHTML = '<div class="empty">等待读取近期视频...</div>';
  el.selectionStatus.textContent = "先读取近期视频，再选择本次要采集的内容。";
}

function defaultSelectedVideoIds(preview) {
  const previewIds = new Set(preview.videos.map((item) => item.videoId));
  const savedIds = state.settings?.selectedVideoIds || [];
  const preserved = savedIds.filter((item) => previewIds.has(item));
  return preserved.length ? preserved : preview.videos.map((item) => item.videoId);
}

function updateSelectionSummary() {
  const total = state.currentPreview?.videos.length || 0;
  const selectedCount = state.selectedVideoIds.size;
  el.selectionSummary.textContent = `已选择 ${selectedCount} / ${total} 条视频`;
  el.selectAllVideos.checked = total > 0 && selectedCount === total;
  el.selectAllVideos.indeterminate = selectedCount > 0 && selectedCount < total;
  el.confirmSelection.disabled = state.isCapturing || selectedCount === 0;
  el.cancelSelection.disabled = state.isCapturing;
}

function renderSelectionList() {
  if (!state.currentPreview) {
    return;
  }
  if (!state.currentPreview.videos.length) {
    el.videoSelectionList.innerHTML = '<div class="empty">当前账号没有可采集的视频。</div>';
    updateSelectionSummary();
    return;
  }
  el.videoSelectionList.innerHTML = state.currentPreview.videos
    .map((video) => {
      const checked = state.selectedVideoIds.has(video.videoId) ? "checked" : "";
      return `
        <label class="video-option">
          <input type="checkbox" data-video-id="${escapeHtml(video.videoId)}" ${checked} />
          <div class="video-option-body">
            <div class="video-option-title">${escapeHtml(video.description || video.title || video.videoId)}</div>
            <div class="video-option-meta">发布时间：${escapeHtml(formatTimestamp(video.publishTime))}</div>
            <div class="video-option-meta">videoId：${escapeHtml(video.videoId)}</div>
            <div class="video-option-meta">
              播放 ${formatNumber(video.metrics.playCount)} / 点赞 ${formatNumber(video.metrics.likeCount)} / 评论 ${formatNumber(video.metrics.commentCount)} / 分享 ${formatNumber(video.metrics.shareCount)}
            </div>
          </div>
        </label>
      `;
    })
    .join("");

  el.videoSelectionList.querySelectorAll('input[type="checkbox"][data-video-id]').forEach((checkbox) => {
    checkbox.addEventListener("change", () => {
      const videoId = checkbox.dataset.videoId;
      if (!videoId) {
        return;
      }
      if (checkbox.checked) {
        state.selectedVideoIds.add(videoId);
      } else {
        state.selectedVideoIds.delete(videoId);
      }
      updateSelectionSummary();
    });
  });
  updateSelectionSummary();
}

function showSelectionPanel(preview) {
  state.currentPreview = preview;
  state.selectedVideoIds = new Set(defaultSelectedVideoIds(preview));
  el.selectionPanel.hidden = false;
  el.selectionAccount.textContent = preview.accountLabel || "未知账号";
  el.selectionStatus.textContent = `已读取 ${preview.videos.length} 条近期视频，请勾选本次要采集的内容。`;
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
    .map((row) => `<option value="${escapeHtml(row.videoId)}">${escapeHtml(row.description || row.title || row.videoId)}</option>`)
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
            <div>${escapeHtml(row.description || row.title || row.videoId)}</div>
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

function clearChart() {
  while (el.chartSvg.firstChild) {
    el.chartSvg.removeChild(el.chartSvg.firstChild);
  }
  el.chartTooltip.hidden = true;
}

function renderEmptyChart(message) {
  clearChart();
  el.chartEmpty.hidden = false;
  el.chartEmpty.textContent = message;
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

function showChartTooltip(event, point, metric) {
  const wrapperRect = el.chartSvg.parentElement.getBoundingClientRect();
  el.chartTooltip.textContent = `横轴：${formatTimestamp(point.timestamp)}\n纵轴：${metricLabels[metric]} ${formatDelta(point.value)}`;
  el.chartTooltip.hidden = false;
  const left = Math.min(Math.max(event.clientX - wrapperRect.left + 12, 8), wrapperRect.width - el.chartTooltip.offsetWidth - 8);
  const top = Math.min(Math.max(event.clientY - wrapperRect.top - el.chartTooltip.offsetHeight - 12, 8), wrapperRect.height - el.chartTooltip.offsetHeight - 8);
  el.chartTooltip.style.left = `${left}px`;
  el.chartTooltip.style.top = `${top}px`;
}

function renderLineChart(points, metric, row) {
  if (points.length < 2) {
    renderEmptyChart("当前视频的快照不足，至少需要两次采集才能显示趋势。");
    el.chartTitle.textContent = `${metricLabels[metric]}新增趋势`;
    el.chartMeta.textContent = row ? `${row.description || row.title || row.videoId} · 快照不足` : "";
    return;
  }

  clearChart();
  el.chartEmpty.hidden = true;
  el.chartTitle.textContent = `${metricLabels[metric]}新增趋势`;
  el.chartMeta.textContent = `${row.description || row.title || row.videoId} · ${formatTimestamp(points[0].timestamp)} 至 ${formatTimestamp(points[points.length - 1].timestamp)} · ${points.length} 个点`;

  const width = 920;
  const height = 380;
  const margin = { top: 24, right: 28, bottom: 44, left: 68 };
  const innerWidth = width - margin.left - margin.right;
  const innerHeight = height - margin.top - margin.bottom;
  const minX = points[0].timestamp;
  const maxX = points[points.length - 1].timestamp;
  const values = points.map((point) => point.value);
  const { minY, maxY, ticks } = createCountAxis(values);

  const xScale = (value) => margin.left + ((value - minX) / Math.max(1, maxX - minX)) * innerWidth;
  const yScale = (value) => margin.top + (1 - (value - minY) / Math.max(1, maxY - minY)) * innerHeight;

  el.chartSvg.setAttribute("viewBox", `0 0 ${width} ${height}`);
  el.chartSvg.appendChild(createSvgElement("rect", { x: 0, y: 0, width, height, fill: "#ffffff" }));

  ticks.forEach((tick) => {
    const y = yScale(tick);
    el.chartSvg.appendChild(createSvgElement("line", { x1: margin.left, y1: y, x2: width - margin.right, y2: y, stroke: "#e7ebf2" }));
    const label = createSvgElement("text", { x: margin.left - 10, y: y + 4, "text-anchor": "end", fill: "#667085", "font-size": 12 });
    label.textContent = Math.round(tick).toLocaleString();
    el.chartSvg.appendChild(label);
  });

  const tickIndexes = Array.from(new Set([0, Math.floor((points.length - 1) / 2), points.length - 1]));
  tickIndexes.forEach((index) => {
    const point = points[index];
    const x = xScale(point.timestamp);
    el.chartSvg.appendChild(createSvgElement("line", { x1: x, y1: margin.top, x2: x, y2: height - margin.bottom, stroke: "#f1f3f7" }));
    const label = createSvgElement("text", { x, y: height - 14, "text-anchor": "middle", fill: "#667085", "font-size": 12 });
    label.textContent = new Date(point.timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    el.chartSvg.appendChild(label);
  });

  const pathData = points
    .map((point, index) => `${index === 0 ? "M" : "L"} ${xScale(point.timestamp).toFixed(2)} ${yScale(point.value).toFixed(2)}`)
    .join(" ");
  const areaData = `${pathData} L ${xScale(points[points.length - 1].timestamp).toFixed(2)} ${height - margin.bottom} L ${xScale(points[0].timestamp).toFixed(2)} ${height - margin.bottom} Z`;
  el.chartSvg.appendChild(createSvgElement("path", { d: areaData, fill: "#d5f5f1", opacity: 0.9 }));
  el.chartSvg.appendChild(createSvgElement("path", { d: pathData, fill: "none", stroke: "#0f766e", "stroke-width": 3, "stroke-linejoin": "round" }));

  const visibleStep = Math.max(1, Math.ceil(points.length / 60));
  points.forEach((point, index) => {
    const x = xScale(point.timestamp);
    const y = yScale(point.value);
    if (index % visibleStep === 0 || index === points.length - 1) {
      el.chartSvg.appendChild(createSvgElement("circle", { cx: x, cy: y, r: 3.5, fill: "#ef6c45", stroke: "#ffffff", "stroke-width": 2 }));
    }
    const hitArea = createSvgElement("circle", { cx: x, cy: y, r: 10, fill: "transparent" });
    hitArea.addEventListener("mouseenter", (event) => showChartTooltip(event, point, metric));
    hitArea.addEventListener("mousemove", (event) => showChartTooltip(event, point, metric));
    hitArea.addEventListener("mouseleave", () => {
      el.chartTooltip.hidden = true;
    });
    el.chartSvg.appendChild(hitArea);
  });
}

async function refreshDashboard() {
  const windowMinutes = Math.max(1, Number(el.windowMinutes.value || 5));
  const metric = el.metricSelect.value;
  const payload = await apiGet(`/api/window-stats?windowMinutes=${windowMinutes}`);
  state.windowRows = payload.rows || [];
  renderVideoOptions(state.windowRows);
  renderSummary(state.windowRows, windowMinutes);

  const row = state.windowRows.find((item) => item.videoId === state.selectedVideoId);
  if (!row) {
    renderEmptyChart("暂无可展示的视频。");
    el.chartTitle.textContent = "新增趋势";
    el.chartMeta.textContent = "";
    return;
  }
  const trend = await apiGet(`/api/trend?videoId=${encodeURIComponent(state.selectedVideoId)}&metric=${encodeURIComponent(metric)}`);
  renderLineChart(trend.points || [], metric, row);
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
  state.recentSnapshots = payload.recentSnapshots || [];
  state.hasCaptureHistory = Boolean(payload.hasCaptureHistory);
  renderStatus();
  if (shouldSyncForm) {
    renderSettings();
  }
  renderRecentSnapshots();
  renderPrimaryButton();
}

async function refreshAll() {
  await refreshBootstrap();
  await refreshDashboard();
}

async function beginCaptureSetup() {
  state.isCapturing = true;
  renderPrimaryButton();
  el.lastError.textContent = "正在读取账号和近期视频...";
  try {
    const response = await apiPost("/api/capture/prepare");
    showSelectionPanel(response.preview);
    el.lastError.textContent = "无";
  } catch (error) {
    el.lastError.textContent = error.message;
    hideSelectionPanel();
  } finally {
    state.isCapturing = false;
    renderPrimaryButton();
    updateSelectionSummary();
  }
}

el.captureButton.addEventListener("click", async () => {
  if (state.isCapturing) {
    return;
  }
  if (state.settings?.capturePaused || !state.hasCaptureHistory) {
    await beginCaptureSetup();
    return;
  }
  await apiPost("/api/capture/pause", { paused: true });
  await refreshAll();
});

el.runNowButton.addEventListener("click", async () => {
  try {
    await apiPost("/api/capture/run");
    await refreshAll();
  } catch (error) {
    el.lastError.textContent = error.message;
  }
});

el.refreshAllButton.addEventListener("click", async () => {
  await refreshAll();
});

el.settingsForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    await apiPost("/api/settings", {
      pollIntervalMinutes: Number(el.pollInterval.value || 1),
      defaultCompareWindowMinutes: Number(el.compareWindow.value || 5),
      retentionDays: Number(el.retentionDays.value || 30),
      targetUrl: el.targetUrl.value,
      sessionCookie: el.sessionCookie.value,
      accountLabelHint: el.accountLabelHint.value,
      requestTimeoutSeconds: Number(el.requestTimeout.value || 20),
    });
    el.saveStatus.textContent = `保存成功：${new Date().toLocaleString()}`;
    await refreshAll();
  } catch (error) {
    el.saveStatus.textContent = error.message;
  }
});

el.selectAllVideos.addEventListener("change", () => {
  if (!state.currentPreview) {
    return;
  }
  if (el.selectAllVideos.checked) {
    state.selectedVideoIds = new Set(state.currentPreview.videos.map((item) => item.videoId));
  } else {
    state.selectedVideoIds = new Set();
  }
  renderSelectionList();
});

el.confirmSelection.addEventListener("click", async () => {
  if (!state.currentPreview || state.isCapturing || state.selectedVideoIds.size === 0) {
    return;
  }
  state.isCapturing = true;
  renderPrimaryButton();
  try {
    await apiPost("/api/capture/start", { selectedVideoIds: Array.from(state.selectedVideoIds) });
    hideSelectionPanel();
    await refreshAll();
  } catch (error) {
    el.selectionStatus.textContent = error.message;
    el.lastError.textContent = error.message;
  } finally {
    state.isCapturing = false;
    renderPrimaryButton();
  }
});

el.cancelSelection.addEventListener("click", () => {
  hideSelectionPanel();
});

el.metricSelect.addEventListener("change", refreshDashboard);
el.windowMinutes.addEventListener("change", refreshDashboard);
el.videoSelect.addEventListener("change", () => {
  state.selectedVideoId = el.videoSelect.value;
  refreshDashboard();
});

refreshAll().catch((error) => {
  el.lastError.textContent = error.message;
});

setInterval(() => {
  refreshBootstrap().catch(() => undefined);
}, 15000);
