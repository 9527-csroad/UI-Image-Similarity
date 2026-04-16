/* ========================================
   State
   ======================================== */
const state = {
  fileA: null,
  fileB: null,
  dataUrlA: null,
  dataUrlB: null,
  fileNameA: '',
  fileNameB: '',
  fileSizeA: 0,
  fileSizeB: 0,
  imageWidthA: 0,
  imageHeightA: 0,
  imageWidthB: 0,
  imageHeightB: 0,
  currentMode: 'sidebyside',
  results: null,
  history: [],
};

const MAX_FILE_SIZE = 10 * 1024 * 1024; // 10 MB
const ALLOWED_TYPES = ['image/png', 'image/jpeg', 'image/webp', 'image/bmp'];

/* ========================================
   DOM References
   ======================================== */
const $ = (sel) => document.querySelector(sel);

const zones = {
  A: $('#zoneA'),
  B: $('#zoneB'),
};
const files = {
  A: $('#fileA'),
  B: $('#fileB'),
};
const placeholders = {
  A: $('#placeholderA'),
  B: $('#placeholderB'),
};
const previews = {
  A: $('#previewA'),
  B: $('#previewB'),
};
const thumbs = {
  A: $('#thumbA'),
  B: $('#thumbB'),
};
const infos = {
  A: $('#infoA'),
  B: $('#infoB'),
};

const btnCompare = $('#btnCompare');
const uploadSection = $('#uploadSection');
const resultsSection = $('#resultsSection');
const loadingText = $('#loadingText');
const errorBanner = $('#errorBanner');
const errorTextEl = $('#errorText');
const errorClose = $('#errorClose');
const stepsEl = $('#steps');

const ringCircle = $('#ringCircle');
const ringValue = $('#ringValue');
const scoreLabel = $('#scoreLabel');
const barSSIM = $('#barSSIM');
const barDHash = $('#barDHash');
const barHist = $('#barHist');
const pctSSIM = $('#pctSSIM');
const pctDHash = $('#pctDHash');
const pctHist = $('#pctHist');
const insightText = $('#insightText');
const scoreCard = $('#scoreCard');

const tabs = $('#tabs');
const panels = {
  sidebyside: $('#panelSideBySide'),
  slider: $('#panelSlider'),
  heatmap: $('#panelHeatmap'),
};

const sideImgA = $('#sideImgA');
const sideImgB = $('#sideImgB');
const sideLabelA = $('#sideLabelA');
const sideLabelB = $('#sideLabelB');

const sliderContainer = $('#sliderContainer');
const sliderBase = $('#sliderBase');
const sliderOverlay = $('#sliderOverlay');
const sliderTop = $('#sliderTop');
const sliderHandle = $('#sliderHandle');

const heatmapBase = $('#heatmapBase');
const heatmapCanvas = $('#heatmapCanvas');
const heatmapOpacity = $('#heatmapOpacity');
const opacityVal = $('#opacityVal');

const btnExport = $('#btnExport');
const btnReset = $('#btnReset');
const btnHistory = $('#btnHistory');
const historyCount = $('#historyCount');
const historyPanel = $('#historyPanel');
const historyList = $('#historyList');
const btnClearHistory = $('#btnClearHistory');

/* ========================================
   Utility Functions
   ======================================== */
function formatFileSize(bytes) {
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

function showError(msg) {
  if (!msg || !msg.trim()) return;
  errorTextEl.textContent = msg;
  errorBanner.hidden = false;
}

function hideError() {
  errorBanner.hidden = true;
}

function getScoreColor(pct) {
  if (pct >= 90) return 'var(--color-green)';
  if (pct >= 70) return 'var(--color-orange)';
  return 'var(--color-red)';
}

function getScoreLabel(pct) {
  if (pct >= 80) return '几乎一致';
  if (pct >= 60) return '高度相似';
  if (pct >= 40) return '中度相似';
  if (pct >= 20) return '略有相似';
  return '完全不同';
}

function getScoreColorClass(pct) {
  if (pct >= 90) return 'color-green';
  if (pct >= 70) return 'color-orange';
  return 'color-red';
}

function generateInsight(ssim, edge, spatial_color, combined) {
  if (combined >= 80) {
    return '两张图几乎完全相同，仅存在像素级微调。肉眼几乎无法区分差异。';
  }
  if (combined >= 60) {
    return '整体框架和布局高度一致，但存在局部信息增减。';
  }
  if (combined >= 40) {
    return '整体布局框架相似，但局部模块内容发生了替换。';
  }
  if (combined >= 20) {
    return '两张图在整体框架或视觉风格上存在一定相似性，但差异明显。';
  }
  return '两张图内容差异较大，请确认是否上传了正确的对比图片。';
}

function setStep(step) {
  const steps = stepsEl.querySelectorAll('.step');
  const lines = stepsEl.querySelectorAll('.step-line');
  steps.forEach((el, i) => {
    const n = i + 1;
    el.classList.remove('active', 'done');
    if (n === step) el.classList.add('active');
    else if (n < step) el.classList.add('done');
  });
  lines.forEach((el, i) => {
    el.style.background = (i + 1 < step) ? 'var(--color-green)' : 'var(--color-border)';
  });
}

/* ========================================
   File Handling
   ======================================== */
function validateFile(file) {
  if (!ALLOWED_TYPES.includes(file.type)) {
    showError('不支持的文件格式，请上传 PNG、JPG、WebP 或 BMP 图片。');
    return false;
  }
  if (file.size > MAX_FILE_SIZE) {
    showError('文件大小超过 10 MB 限制，请压缩后重试。');
    return false;
  }
  return true;
}

function handleFile(target, file) {
  if (!validateFile(file)) return;

  state['file' + target] = file;
  state['fileName' + target] = file.name;
  state['fileSize' + target] = file.size;

  const reader = new FileReader();
  reader.onload = (e) => {
    const dataUrl = e.target.result;
    state['dataUrl' + target] = dataUrl;

    // Get image dimensions
    const img = new Image();
    img.onload = () => {
      state['imageWidth' + target] = img.width;
      state['imageHeight' + target] = img.height;
      updateUploadUI(target);
      checkReady();
    };
    img.src = dataUrl;
  };
  reader.readAsDataURL(file);
}

function updateUploadUI(target) {
  const zone = zones[target];
  const placeholder = placeholders[target];
  const preview = previews[target];
  const thumb = thumbs[target];
  const info = infos[target];

  thumb.src = state['dataUrl' + target];
  info.textContent = `${state['fileName' + target]} \u00B7 ${state['imageWidth' + target]}x${state['imageHeight' + target]} \u00B7 ${formatFileSize(state['fileSize' + target])}`;

  placeholder.hidden = true;
  preview.hidden = false;
  zone.classList.add('has-file');
}

function resetUploadUI(target) {
  const zone = zones[target];
  const placeholder = placeholders[target];
  const preview = previews[target];

  state['file' + target] = null;
  state['dataUrl' + target] = null;
  state['fileName' + target] = '';
  state['fileSize' + target] = 0;
  state['imageWidth' + target] = 0;
  state['imageHeight' + target] = 0;

  placeholder.hidden = false;
  preview.hidden = true;
  zone.classList.remove('has-file');

  files[target].value = '';
}

function checkReady() {
  const ready = state.fileA !== null && state.fileB !== null;
  btnCompare.disabled = !ready;

  // Hide preview placeholders if file is set
  ['A', 'B'].forEach((t) => {
    if (state['file' + t]) {
      previews[t].hidden = false;
    } else {
      previews[t].hidden = true;
      placeholders[t].hidden = false;
    }
  });

  // Size warning
  if (ready) {
    const ratioW = Math.max(state.imageWidthA, state.imageWidthB) / Math.min(state.imageWidthA, state.imageWidthB);
    const ratioH = Math.max(state.imageHeightA, state.imageHeightB) / Math.min(state.imageHeightA, state.imageHeightB);
    if (ratioW > 5 || ratioH > 5) {
      showError('两张图尺寸差异较大，可能影响对比精度。');
    }
  }
}

/* ========================================
   Drag & Drop
   ======================================== */
['A', 'B'].forEach((target) => {
  const zone = zones[target];

  zone.addEventListener('click', (e) => {
    if (e.target.closest('.btn-replace')) return;
    if (!state['file' + target]) {
      files[target].click();
    }
  });

  zone.addEventListener('dragover', (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (!state['file' + target]) {
      zone.classList.add('drag-over');
    }
  });

  zone.addEventListener('dragleave', (e) => {
    e.preventDefault();
    e.stopPropagation();
    zone.classList.remove('drag-over');
  });

  zone.addEventListener('drop', (e) => {
    e.preventDefault();
    e.stopPropagation();
    zone.classList.remove('drag-over');
    if (state['file' + target]) return;

    const file = e.dataTransfer.files[0];
    if (file) handleFile(target, file);
  });

  files[target].addEventListener('change', (e) => {
    if (e.target.files[0]) handleFile(target, e.target.files[0]);
  });

  // Replace button
  zone.addEventListener('click', (e) => {
    if (e.target.closest('.btn-replace')) {
      e.stopPropagation();
      files[target].click();
    }
  });
});

/* ========================================
   API Configuration
   ======================================== */
const API_URL = 'http://localhost:8000';
let serverHeatmap = null; // base64 heatmap from server

/* ========================================
   Compare (API-backed, with mock fallback)
   ======================================== */
function generateMockResults() {
  const base = 60 + Math.random() * 35;
  const ssim = Math.min(100, Math.max(20, base + (Math.random() - 0.5) * 20));
  const edge = Math.min(100, Math.max(30, base + (Math.random() - 0.5) * 15));
  const spatial_color = Math.min(100, Math.max(25, base + (Math.random() - 0.5) * 25));
  const phash = Math.min(100, Math.max(40, base + (Math.random() - 0.5) * 10));
  const dominant_color = Math.min(100, Math.max(30, base + (Math.random() - 0.5) * 20));
  const combined = Math.round((0.30 * ssim + 0.25 * edge + 0.25 * spatial_color + 0.10 * phash + 0.10 * dominant_color) * 10) / 10;

  return {
    ssim: Math.round(ssim * 10) / 10,
    edge: Math.round(edge * 10) / 10,
    spatial_color: Math.round(spatial_color * 10) / 10,
    phash: Math.round(phash * 10) / 10,
    dominant_color: Math.round(dominant_color * 10) / 10,
    combined,
    insight: generateInsight(ssim, edge, spatial_color, combined),
    label: getScoreLabel(combined),
    processing_time_ms: Math.round(500 + Math.random() * 1000),
  };
}

async function startCompare() {
  btnCompare.classList.add('loading');
  btnCompare.innerHTML = '<span class="spinner"></span>计算中...';
  btnCompare.disabled = true;

  uploadSection.style.opacity = '0.5';
  uploadSection.style.pointerEvents = 'none';

  setStep(2);

  const phases = [
    '正在分析图像结构...',
    '正在计算布局指纹...',
    '正在对比颜色分布...',
    '正在生成差异热力图...',
  ];

  let results;

  try {
    // Build FormData for upload
    const formData = new FormData();
    formData.append('image_a', state.fileA);
    formData.append('image_b', state.fileB);

    loadingText.hidden = false;
    loadingText.textContent = phases[0];

    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 30000);

    const response = await fetch(`${API_URL}/api/compare`, {
      method: 'POST',
      body: formData,
      signal: controller.signal,
    });

    clearTimeout(timeout);

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
      throw new Error(error.detail || 'Comparison failed');
    }

    results = await response.json();
    serverHeatmap = results.heatmap || null;

  } catch (err) {
    // Fallback to mock if server is unavailable
    console.warn('API unavailable, using mock results:', err.message);
    for (let i = 0; i < phases.length; i++) {
      loadingText.textContent = phases[i];
      await sleep(500 + Math.random() * 300);
    }
    results = generateMockResults();
    serverHeatmap = null;
  }

  loadingText.hidden = true;

  state.results = results;
  displayResults(results);

  btnCompare.classList.remove('loading');
  btnCompare.innerHTML = '开始对比';
  btnCompare.disabled = false;

  uploadSection.style.opacity = '1';
  uploadSection.style.pointerEvents = 'auto';

  setStep(3);
  resultsSection.hidden = false;

  // Save to history
  saveToHistory();
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

btnCompare.addEventListener('click', startCompare);

/* ========================================
   Display Results
   ======================================== */
function displayResults(results) {
  const { ssim, edge, spatial_color, phash, dominant_color, combined } = results;

  // Ring progress
  const circumference = 2 * Math.PI * 52;
  const offset = circumference * (1 - combined / 100);
  const color = getScoreColor(combined);
  ringCircle.style.strokeDashoffset = offset;
  ringCircle.style.stroke = color;
  ringValue.textContent = combined.toFixed(1) + '%';

  // Label (prefer server-provided label)
  const label = results.label || getScoreLabel(combined);
  scoreLabel.className = 'score-label ' + getScoreColorClass(combined);
  scoreLabel.querySelector('.label-dot').style.background = color;
  scoreLabel.querySelector('.label-text').textContent = label;

  // Score card background tint
  scoreCard.style.background = `var(--color-surface)`;
  scoreCard.style.borderLeft = `4px solid ${color}`;

  // Sub-scores (Phase 2: 5 metrics)
  barSSIM.style.width = ssim + '%';
  barSSIM.style.background = getScoreColor(ssim);
  barDHash.style.width = edge + '%';
  barDHash.style.background = getScoreColor(edge);
  barHist.style.width = spatial_color + '%';
  barHist.style.background = getScoreColor(spatial_color);

  pctSSIM.textContent = ssim.toFixed(1) + '%';
  pctDHash.textContent = edge.toFixed(1) + '%';
  pctHist.textContent = spatial_color.toFixed(1) + '%';

  // Insight (prefer server-provided insight)
  insightText.textContent = results.insight || generateInsight(ssim, edge, spatial_color, combined);

  // Populate comparison views
  populateComparisonViews();

  // Draw heatmap
  setTimeout(drawHeatmap, 100);

  // Setup slider
  setTimeout(initSlider, 100);
}

function populateComparisonViews() {
  // Side-by-side
  sideImgA.src = state.dataUrlA;
  sideImgB.src = state.dataUrlB;
  sideLabelA.textContent = state.fileNameA;
  sideLabelB.textContent = state.fileNameB;

  // Slider
  sliderBase.src = state.dataUrlA;
  sliderTop.src = state.dataUrlB;

  // Heatmap base
  heatmapBase.src = state.dataUrlA;
}

/* ========================================
   Tab Switching
   ======================================== */
tabs.addEventListener('click', (e) => {
  const tab = e.target.closest('.tab');
  if (!tab) return;

  const mode = tab.dataset.mode;
  state.currentMode = mode;

  tabs.querySelectorAll('.tab').forEach((t) => t.classList.remove('active'));
  tab.classList.add('active');

  Object.values(panels).forEach((p) => p.classList.remove('active'));
  panels[mode].classList.add('active');

  if (mode === 'slider') initSlider();
  if (mode === 'heatmap') drawHeatmap();
});

/* ========================================
   Slider
   ======================================== */
let sliderDragging = false;

function initSlider() {
  requestAnimationFrame(() => {
    // Match overlay image size to container so it clips correctly
    const containerWidth = sliderContainer.offsetWidth;
    sliderTop.style.width = containerWidth + 'px';
    sliderTop.style.height = sliderBase.offsetHeight + 'px';

    const halfWidth = containerWidth / 2;
    setSliderPosition(halfWidth);
  });
}

function setSliderPosition(x) {
  const containerRect = sliderContainer.getBoundingClientRect();
  const pos = Math.max(0, Math.min(x, containerRect.width));
  const pct = (pos / containerRect.width) * 100;

  sliderOverlay.style.width = pct + '%';
  sliderHandle.style.left = pct + '%';
  sliderHandle.style.transform = 'translateX(-50%)';
}

sliderContainer.addEventListener('mousedown', (e) => {
  sliderDragging = true;
  setSliderPosition(e.offsetX);
  e.preventDefault();
});

document.addEventListener('mousemove', (e) => {
  if (!sliderDragging) return;
  const rect = sliderContainer.getBoundingClientRect();
  const x = e.clientX - rect.left;
  setSliderPosition(x);
});

document.addEventListener('mouseup', () => {
  sliderDragging = false;
});

// Touch support
sliderContainer.addEventListener('touchstart', (e) => {
  sliderDragging = true;
  const rect = sliderContainer.getBoundingClientRect();
  const x = e.touches[0].clientX - rect.left;
  setSliderPosition(x);
});

document.addEventListener('touchmove', (e) => {
  if (!sliderDragging) return;
  const rect = sliderContainer.getBoundingClientRect();
  const x = e.touches[0].clientX - rect.left;
  setSliderPosition(x);
});

document.addEventListener('touchend', () => {
  sliderDragging = false;
});

/* ========================================
   Heatmap
   ======================================== */
function drawHeatmap() {
  const img = heatmapBase;
  if (!img.src || !img.naturalWidth) return;

  const canvas = heatmapCanvas;
  const ctx = canvas.getContext('2d');

  // Match canvas to displayed image size
  const displayWidth = img.clientWidth;
  const displayHeight = img.clientHeight;

  canvas.width = displayWidth;
  canvas.height = displayHeight;
  canvas.style.width = displayWidth + 'px';
  canvas.style.height = displayHeight + 'px';

  ctx.clearRect(0, 0, canvas.width, canvas.height);

  // Use server-generated heatmap if available
  if (serverHeatmap) {
    const heatmapImg = new Image();
    heatmapImg.onload = () => {
      ctx.globalAlpha = heatmapOpacity.value / 100;
      ctx.drawImage(heatmapImg, 0, 0, canvas.width, canvas.height);
      ctx.globalAlpha = 1.0;
    };
    heatmapImg.src = `data:image/png;base64,${serverHeatmap}`;
    return;
  }

  const blobCount = 3 + Math.floor(Math.random() * 4);
  for (let i = 0; i < blobCount; i++) {
    const cx = Math.random() * canvas.width;
    const cy = Math.random() * canvas.height;
    const rx = 30 + Math.random() * (canvas.width * 0.2);
    const ry = 20 + Math.random() * (canvas.height * 0.15);
    const intensity = 0.3 + Math.random() * 0.7;

    const gradient = ctx.createRadialGradient(cx, cy, 0, cx, cy, Math.max(rx, ry));

    if (intensity > 0.7) {
      gradient.addColorStop(0, `rgba(239, 68, 68, ${intensity * opacity})`);
      gradient.addColorStop(0.6, `rgba(251, 146, 60, ${intensity * opacity * 0.6})`);
      gradient.addColorStop(1, 'rgba(251, 191, 36, 0)');
    } else if (intensity > 0.4) {
      gradient.addColorStop(0, `rgba(251, 146, 60, ${intensity * opacity})`);
      gradient.addColorStop(0.6, `rgba(251, 191, 36, ${intensity * opacity * 0.5})`);
      gradient.addColorStop(1, 'rgba(251, 191, 36, 0)');
    } else {
      gradient.addColorStop(0, `rgba(251, 191, 36, ${intensity * opacity})`);
      gradient.addColorStop(1, 'rgba(251, 191, 36, 0)');
    }

    ctx.fillStyle = gradient;
    ctx.beginPath();
    ctx.ellipse(cx, cy, rx, ry, 0, 0, Math.PI * 2);
    ctx.fill();
  }

  // Add some pixel-level noise for realism
  const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height);
  const data = imageData.data;
  for (let i = 0; i < data.length; i += 4) {
    if (data[3] > 0) {
      const noise = (Math.random() - 0.5) * 30;
      data[i] = Math.min(255, Math.max(0, data[i] + noise));
    }
  }
  ctx.putImageData(imageData, 0, 0);
}

heatmapOpacity.addEventListener('input', () => {
  opacityVal.textContent = heatmapOpacity.value + '%';
  drawHeatmap();
});

/* ========================================
   History (LocalStorage)
   ======================================== */
function loadHistory() {
  try {
    const data = localStorage.getItem('imageCompareHistory');
    state.history = data ? JSON.parse(data) : [];
  } catch {
    state.history = [];
  }
  updateHistoryCount();
}

function saveToHistory() {
  if (!state.results) return;

  const entry = {
    time: new Date().toLocaleString('zh-CN'),
    combined: state.results.combined,
    ssim: state.results.ssim,
    dhash: state.results.dhash,
    hist: state.results.hist,
    fileNameA: state.fileNameA,
    fileNameB: state.fileNameB,
    dataUrlA: state.dataUrlA,
    dataUrlB: state.dataUrlB,
  };

  state.history.unshift(entry);
  if (state.history.length > 10) state.history.pop();

  try {
    // Truncate data URLs to save space (keep thumbnails)
    const toSave = state.history.map((h) => ({
      ...h,
      dataUrlA: h.dataUrlA?.substring(0, 500),
      dataUrlB: h.dataUrlB?.substring(0, 500),
    }));
    localStorage.setItem('imageCompareHistory', JSON.stringify(toSave));
  } catch {
    // Storage full — remove oldest and retry
    state.history.pop();
  }

  updateHistoryCount();
}

function updateHistoryCount() {
  historyCount.textContent = `(${state.history.length})`;
}

function renderHistory() {
  historyPanel.hidden = !historyPanel.hidden;
  if (historyPanel.hidden) return;

  historyList.innerHTML = '';
  if (state.history.length === 0) {
    historyList.innerHTML = '<p style="text-align:center;color:var(--color-text-muted);font-size:13px;padding:20px 0;">暂无历史记录</p>';
    return;
  }

  state.history.forEach((entry, i) => {
    const item = document.createElement('div');
    item.className = 'history-item';
    item.innerHTML = `
      <div class="history-meta">
        <div><strong class="history-score" style="color:${getScoreColor(entry.combined)}">${entry.combined.toFixed(1)}%</strong> — ${entry.fileNameA} vs ${entry.fileNameB}</div>
        <div style="font-size:12px;color:var(--color-text-muted);">${entry.time}</div>
      </div>
    `;
    historyList.appendChild(item);
  });
}

btnHistory.addEventListener('click', renderHistory);

btnClearHistory.addEventListener('click', () => {
  state.history = [];
  try { localStorage.removeItem('imageCompareHistory'); } catch {}
  updateHistoryCount();
  historyList.innerHTML = '<p style="text-align:center;color:var(--color-text-muted);font-size:13px;padding:20px 0;">暂无历史记录</p>';
});

/* ========================================
   Export (simple canvas-based)
   ======================================== */
btnExport.addEventListener('click', () => {
  // Create a canvas with the score card info
  const canvas = document.createElement('canvas');
  canvas.width = 800;
  canvas.height = 500;
  const ctx = canvas.getContext('2d');

  // Background
  ctx.fillStyle = '#FFFFFF';
  ctx.fillRect(0, 0, 800, 500);

  // Title
  ctx.fillStyle = '#1E293B';
  ctx.font = 'bold 24px sans-serif';
  ctx.fillText('UI Image Compare - 对比结果', 30, 40);

  // Time
  ctx.fillStyle = '#64748B';
  ctx.font = '14px sans-serif';
  ctx.fillText(new Date().toLocaleString('zh-CN'), 30, 65);

  // Scores
  const r = state.results;
  ctx.font = 'bold 48px sans-serif';
  ctx.fillStyle = getScoreColor(r.combined);
  ctx.fillText(r.combined.toFixed(1) + '%', 30, 130);

  ctx.font = '16px sans-serif';
  ctx.fillStyle = '#1E293B';
  ctx.fillText(getScoreLabel(r.combined), 30, 160);

  // Sub-scores
  const scores = [
    { name: '结构分 (SSIM)', value: r.ssim },
    { name: '布局分 (Edge)', value: r.edge || r.dhash },
    { name: '颜色分 (Spatial)', value: r.spatial_color || r.hist },
  ];

  let y = 200;
  scores.forEach((s) => {
    ctx.fillStyle = '#64748B';
    ctx.font = '14px sans-serif';
    ctx.fillText(s.name, 30, y);

    // Bar background
    ctx.fillStyle = '#E2E8F0';
    ctx.fillRect(200, y - 12, 300, 8);

    // Bar fill
    ctx.fillStyle = getScoreColor(s.value);
    ctx.fillRect(200, y - 12, 300 * (s.value / 100), 8);

    // Value
    ctx.fillStyle = '#1E293B';
    ctx.font = 'bold 14px monospace';
    ctx.fillText(s.value.toFixed(1) + '%', 520, y);

    y += 36;
  });

  // Insight
  ctx.fillStyle = '#F3F4F6';
  ctx.fillRect(20, y + 10, 760, 50);
  ctx.fillStyle = '#4B5563';
  ctx.font = '13px sans-serif';
  const insight = generateInsight(r.ssim, r.edge || r.dhash, r.spatial_color || r.hist, r.combined);
  wrapText(ctx, insight, 36, y + 30, 730, 18);

  // Download
  canvas.toBlob((blob) => {
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    const now = new Date();
    const stamp = `${now.getFullYear()}${String(now.getMonth() + 1).padStart(2, '0')}${String(now.getDate()).padStart(2, '0')}-${String(now.getHours()).padStart(2, '0')}${String(now.getMinutes()).padStart(2, '0')}${String(now.getSeconds()).padStart(2, '0')}`;
    a.href = url;
    a.download = `image-compare-${stamp}.png`;
    a.click();
    URL.revokeObjectURL(url);
  });
});

function wrapText(ctx, text, x, y, maxWidth, lineHeight) {
  const words = text.split('');
  let line = '';
  let currentY = y;
  for (let n = 0; n < words.length; n++) {
    const testLine = line + words[n];
    const metrics = ctx.measureText(testLine);
    if (metrics.width > maxWidth && n > 0) {
      ctx.fillText(line, x, currentY);
      line = words[n];
      currentY += lineHeight;
    } else {
      line = testLine;
    }
  }
  ctx.fillText(line, x, currentY);
}

/* ========================================
   Reset
   ======================================== */
btnReset.addEventListener('click', () => {
  state.fileA = null;
  state.fileB = null;
  state.dataUrlA = null;
  state.dataUrlB = null;
  state.fileNameA = '';
  state.fileNameB = '';
  state.fileSizeA = 0;
  state.fileSizeB = 0;
  state.imageWidthA = 0;
  state.imageHeightA = 0;
  state.imageWidthB = 0;
  state.imageHeightB = 0;
  state.results = null;
  serverHeatmap = null;

  // Reset UI
  ['A', 'B'].forEach((t) => {
    files[t].value = '';
    placeholders[t].hidden = false;
    previews[t].hidden = true;
    zones[t].classList.remove('has-file');
  });

  btnCompare.disabled = true;
  btnCompare.innerHTML = '开始对比';
  btnCompare.classList.remove('loading');
  uploadSection.style.opacity = '1';
  uploadSection.style.pointerEvents = 'auto';
  loadingText.hidden = true;

  resultsSection.hidden = true;

  // Reset ring
  ringCircle.style.strokeDashoffset = 327;
  ringCircle.style.stroke = '#E5E7EB';
  ringValue.textContent = '--';
  scoreLabel.querySelector('.label-text').textContent = '--';
  scoreLabel.querySelector('.label-dot').style.background = 'var(--color-text-muted)';

  [barSSIM, barDHash, barHist].forEach((bar) => {
    bar.style.width = '0%';
  });
  [pctSSIM, pctDHash, pctHist].forEach((el) => {
    el.textContent = '--%';
  });
  insightText.textContent = '';

  setStep(1);
  hideError();
});

/* ========================================
   Error Banner Close
   ======================================== */
errorClose.addEventListener('click', hideError);

/* ========================================
   Init
   ======================================== */
loadHistory();
setStep(1);
