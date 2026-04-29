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
  hasInitializedChartWindow: false,
  dashboardRefreshTimer: null,
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
  videoSelect: document.getElementById("video-select"),
  chartTitle: document.getElementById("chart-title"),
  chartMeta: document.getElementById("chart-meta"),
  summaryMeta: document.getElementById("summary-meta"),
  summaryBody: document.getElementById("summary-body"),
  chartList: document.getElementById("chart-list"),
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
    .map((row) => `<option value="${escapeHtml(row.videoId)}">${escapeHtml(cleanVideoTitle(row.description, row.title, row.videoId))}</option>`)
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
      el.lastError.textContent = error.message;
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

el.windowMinutes.addEventListener("change", refreshDashboard);
el.windowMinutes.addEventListener("input", scheduleDashboardRefresh);
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
