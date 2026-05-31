'use strict';
// ── State ──────────────────────────────────────────────────────────────
let uploadedFile = null;
let currentMode = 'full';
let lastFullResultData = null;
let lastDecryptResultData = null;
let exportDialogState = { results: [], initialized: false };
let resultNavObserver = null;

const ALLOWED_IMAGE_EXTENSIONS = new Set(['png', 'bmp', 'tif', 'tiff']);
const ALLOWED_IMAGE_MIME_TYPES = new Set(['image/png', 'image/bmp', 'image/tiff', 'image/x-tiff']);
const UI_IMPLEMENTATION_ERROR = 'No fue posible completar esta implementación.';

// ── Upload ────────────────────────────────────────────────────────────
const dropZone  = document.getElementById('drop-zone');
const fileInput = document.getElementById('file-input');
const pickBtn   = document.getElementById('pick-btn');

pickBtn.addEventListener('click', e => { e.stopPropagation(); fileInput.click(); });

dropZone.addEventListener('click', e => {
  if (e.target !== fileInput && e.target !== pickBtn) fileInput.click();
});
dropZone.addEventListener('dragover',  e => { e.preventDefault(); dropZone.classList.add('dragover'); });
dropZone.addEventListener('dragleave', () => dropZone.classList.remove('dragover'));
dropZone.addEventListener('drop', e => {
  e.preventDefault(); dropZone.classList.remove('dragover');
  if (e.dataTransfer.files[0]) handleFile(e.dataTransfer.files[0]);
});
fileInput.addEventListener('change', () => { if (fileInput.files[0]) handleFile(fileInput.files[0]); });

document.querySelectorAll('.session-option input[name="session-mode"]').forEach(input => {
  input.addEventListener('change', syncSessionModeUi);
});
document.querySelectorAll('.op-option input[name="operation-mode"]').forEach(input => {
  input.addEventListener('change', syncOperationModeUi);
});
syncSessionModeUi();
syncOperationModeUi();
bindUiDialog();
bindDecryptFilePickers();
bindExportDialog();
bindResultsNavigation();
bindResultsTabs();

function bindDecryptFilePickers() {
  [
    ['decrypt-cipher', 'decrypt-cipher-name'],
    ['decrypt-prev', 'decrypt-prev-name'],
    ['decrypt-session', 'decrypt-session-name'],
  ].forEach(([inputId, labelId]) => {
    const input = document.getElementById(inputId);
    const label = document.getElementById(labelId);
    if (!input || !label || input.dataset.bound === '1') return;

    const updateLabel = () => {
      label.textContent = input.files && input.files[0]
        ? input.files[0].name
        : 'No se ha seleccionado ningún archivo';
      lastDecryptResultData = null;
      if (currentMode === 'decrypt') {
        hideResultsView();
      }
    };

    input.addEventListener('change', updateLabel);
    updateLabel();
    input.dataset.bound = '1';
  });
}

function bindUiDialog() {
  const dialog = document.getElementById('ui-dialog');
  const closeBtn = document.getElementById('ui-dialog-close');
  const primaryBtn = document.getElementById('ui-dialog-primary');
  if (!dialog || !closeBtn || !primaryBtn || dialog.dataset.bound === '1') return;

  const close = () => closeUiDialog();
  closeBtn.addEventListener('click', close);
  primaryBtn.addEventListener('click', close);
  dialog.addEventListener('click', event => {
    if (event.target === dialog) close();
  });
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && !dialog.classList.contains('panel-hidden')) {
      close();
    }
  });
  dialog.dataset.bound = '1';
}

function bindExportDialog() {
  const dialog = document.getElementById('export-dialog');
  const closeBtn = document.getElementById('export-dialog-close');
  const cancelBtn = document.getElementById('export-dialog-cancel');
  const submitBtn = document.getElementById('export-dialog-submit');
  const languageSelect = document.getElementById('export-language');
  const filenameInput = document.getElementById('export-filename');
  if (!dialog || !closeBtn || !cancelBtn || !submitBtn || !languageSelect || !filenameInput || exportDialogState.initialized) return;

  const close = () => closeExportDialog();
  closeBtn.addEventListener('click', close);
  cancelBtn.addEventListener('click', close);
  dialog.addEventListener('click', event => {
    if (event.target === dialog) close();
  });
  languageSelect.addEventListener('change', () => {
    const selected = exportDialogState.results.find(item => item.lang === languageSelect.value);
    if (!selected) return;
    if (!filenameInput.dataset.userEdited || !filenameInput.value.trim()) {
      filenameInput.value = selected.defaultName;
    }
  });
  filenameInput.addEventListener('input', () => {
    filenameInput.dataset.userEdited = filenameInput.value.trim() ? '1' : '';
  });
  submitBtn.addEventListener('click', submitExportDialog);
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && !dialog.classList.contains('panel-hidden')) {
      close();
    }
  });
  exportDialogState.initialized = true;
}

function showUiDialog(title, message) {
  const dialog = document.getElementById('ui-dialog');
  const titleEl = document.getElementById('ui-dialog-title');
  const msgEl = document.getElementById('ui-dialog-message');
  if (!dialog || !titleEl || !msgEl) return;
  titleEl.textContent = title || 'Mensaje';
  msgEl.textContent = message || '';
  dialog.classList.remove('panel-hidden');
  dialog.setAttribute('aria-hidden', 'false');
  document.body.classList.add('dialog-open');
}

function closeUiDialog() {
  const dialog = document.getElementById('ui-dialog');
  if (!dialog) return;
  dialog.classList.add('panel-hidden');
  dialog.setAttribute('aria-hidden', 'true');
  document.body.classList.remove('dialog-open');
}

function openExportDialog(results) {
  const dialog = document.getElementById('export-dialog');
  const languageSelect = document.getElementById('export-language');
  const filenameInput = document.getElementById('export-filename');
  const formatSelect = document.getElementById('export-format');
  if (!dialog || !languageSelect || !filenameInput || !formatSelect) return;

  const exportable = (results || [])
    .filter(item => item.download_url && item.download_name && item.lang)
    .map(item => ({
      lang: item.lang,
      sourceName: item.download_name,
      defaultName: `imagen_descifrada_${item.lang.toLowerCase().replace('#', 'sharp')}`,
      outputFormat: item.output_format || 'png',
      outputLabel: item.output_format_label || 'PNG',
    }));

  if (!exportable.length) {
    showUiDialog('No hay archivos exportables', 'No hay imágenes descifradas disponibles para exportar en este momento.');
    return;
  }

  exportDialogState.results = exportable;
  languageSelect.innerHTML = exportable
    .map(item => `<option value="${item.lang}">${item.lang}</option>`)
    .join('');
  filenameInput.value = exportable[0].defaultName;
  filenameInput.dataset.userEdited = '';
  const originalOption = formatSelect.querySelector('option[value="png"]');
  if (originalOption) {
    originalOption.value = exportable[0].outputFormat;
    originalOption.textContent = `${exportable[0].outputLabel} (original)`;
  }
  formatSelect.value = exportable[0].outputFormat;
  dialog.classList.remove('panel-hidden');
  dialog.setAttribute('aria-hidden', 'false');
  document.body.classList.add('dialog-open');
}

function closeExportDialog() {
  const dialog = document.getElementById('export-dialog');
  if (!dialog) return;
  dialog.classList.add('panel-hidden');
  dialog.setAttribute('aria-hidden', 'true');
  document.body.classList.remove('dialog-open');
}

async function submitExportDialog() {
  const languageSelect = document.getElementById('export-language');
  const filenameInput = document.getElementById('export-filename');
  const formatSelect = document.getElementById('export-format');
  const submitBtn = document.getElementById('export-dialog-submit');
  if (!languageSelect || !filenameInput || !formatSelect || !submitBtn) return;

  const selected = exportDialogState.results.find(item => item.lang === languageSelect.value);
  if (!selected) {
    showUiDialog('Implementación no disponible', 'Selecciona una implementación válida para exportar la imagen.');
    return;
  }

  const rawName = filenameInput.value.trim();
  if (!rawName) {
    showUiDialog('Nombre inválido', 'Escribe un nombre de archivo para exportar la imagen descifrada.');
    return;
  }

  submitBtn.disabled = true;
  try {
    const resp = await fetch('/api/export-recovered', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        source_name: selected.sourceName,
        output_name: rawName,
        output_format: formatSelect.value,
      }),
    });
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) {
      throw new Error(data.error || 'No se pudo preparar la exportación.');
    }
    closeExportDialog();
    await saveUrlWithPicker(data.download_url, data.download_name || `${rawName}.${formatSelect.value}`);
  } catch (err) {
    showUiDialog('No se pudo exportar la imagen', err.message || 'No se pudo exportar la imagen.');
  } finally {
    submitBtn.disabled = false;
  }
}

function resetImageSelection() {
  uploadedFile = null;
  lastFullResultData = null;
  if (fileInput) fileInput.value = '';
  const canvas = document.getElementById('preview-canvas');
  if (canvas) {
    const ctx = canvas.getContext('2d');
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    canvas.width = 0;
    canvas.height = 0;
  }
  const roundsBox = document.getElementById('rounds-recommendation');
  if (roundsBox) {
    roundsBox.innerHTML = '<strong>Nota:</strong> Selecciona una imagen para ver una recomendación de rondas según su tamaño.';
  }
  document.getElementById('encrypt-workspace').classList.add('panel-hidden');
  hideResultsView();
  if (currentMode === 'full') {
    document.getElementById('run-btn').style.display = 'none';
  }
}

function hideResultsView() {
  const results = document.getElementById('results');
  if (!results) return;
  results.style.display = 'none';
  document.getElementById('results-nav')?.classList.add('panel-hidden');
  document.getElementById('results-tabs')?.classList.add('panel-hidden');
  document.getElementById('results-tabs-label')?.classList.add('panel-hidden');
  document.getElementById('results-nav-label')?.classList.add('panel-hidden');
}

function restoreResultsForCurrentMode() {
  if (currentMode === 'full') {
    if (lastFullResultData) {
      renderResults(lastFullResultData, 'full');
    } else {
      hideResultsView();
    }
    return;
  }

  if (lastDecryptResultData) {
    renderDecryptOnlyResult(lastDecryptResultData);
  } else {
    hideResultsView();
  }
}

function validateImageFile(file) {
  const extension = (file?.name?.split('.').pop() || '').toLowerCase();
  const mimeType = (file?.type || '').toLowerCase();
  const extOk = ALLOWED_IMAGE_EXTENSIONS.has(extension);
  const mimeOk = !mimeType || ALLOWED_IMAGE_MIME_TYPES.has(mimeType);
  if (extOk && mimeOk) return true;
  resetImageSelection();
  showUiDialog('Archivo no permitido', 'Selecciona una imagen con extensión PNG, BMP, TIF o TIFF para continuar con el cifrado.');
  return false;
}

function getRecommendedRounds(width, height) {
  const pixels = width * height;
  if (pixels <= 256 * 256) return { range: '6 a 8', reason: 'imagen pequena' };
  if (pixels <= 512 * 512) return { range: '8 a 12', reason: 'imagen mediana' };
  if (pixels <= 1024 * 1024) return { range: '12 a 16', reason: 'imagen grande' };
  return { range: '16 a 24', reason: 'imagen de alta resolucion' };
}

function updateRoundsRecommendation(width, height) {
  const target = document.getElementById('rounds-recommendation');
  if (!target) return;
  const rec = getRecommendedRounds(width, height);
  target.innerHTML = `<strong>Nota:</strong> Para una imagen de ${width} x ${height} px se recomiendan ${rec.range} rondas.`;
}

function handleFile(file) {
  if (!validateImageFile(file)) return;

  uploadedFile = file;
  const reader = new FileReader();
  reader.onerror = () => {
    resetImageSelection();
    showUiDialog('No se pudo leer el archivo', 'El archivo seleccionado no pudo procesarse correctamente. Intenta nuevamente con una imagen PNG, BMP o TIFF válida.');
  };
  reader.onload = ev => {
    const img = new Image();
    img.onerror = () => {
      resetImageSelection();
      showUiDialog('Imagen no válida', 'El archivo seleccionado no pudo interpretarse como una imagen compatible. Verifica el formato e inténtalo de nuevo.');
    };
    img.onload = () => {
      const canvas = document.getElementById('preview-canvas');
      canvas.width = img.width;
      canvas.height = img.height;
      canvas.getContext('2d').drawImage(img, 0, 0);
      updateRoundsRecommendation(img.width, img.height);
      document.getElementById('encrypt-workspace').classList.toggle('panel-hidden', currentMode === 'decrypt' || !uploadedFile);
      document.getElementById('run-btn').style.display = 'block';
      lastFullResultData = null;
      if (currentMode === 'full') {
        hideResultsView();
      }
    };
    img.src = ev.target.result;
  };
  reader.readAsDataURL(file);
}

function syncSessionModeUi() {
  document.querySelectorAll('.session-option').forEach(option => {
    const input = option.querySelector('input[name="session-mode"]');
    option.classList.toggle('selected', !!input?.checked);
  });
}

function syncOperationModeUi() {
  document.querySelectorAll('.op-option').forEach(option => {
    const input = option.querySelector('input[name="operation-mode"]');
    option.classList.toggle('selected', !!input?.checked);
  });
  currentMode = document.querySelector('input[name="operation-mode"]:checked')?.value || 'full';
  const isDecrypt = currentMode === 'decrypt';
  document.getElementById('drop-zone').classList.toggle('panel-hidden', isDecrypt);
  document.getElementById('encrypt-workspace').classList.toggle('panel-hidden', isDecrypt || !uploadedFile);
  document.getElementById('decrypt-panel').classList.toggle('panel-hidden', !isDecrypt);

  const btn = document.getElementById('run-btn');
  btn.style.display = (currentMode === 'decrypt' || !!uploadedFile) ? 'block' : 'none';
  btn.textContent =
    currentMode === 'full' ? '▶ Ejecutar cifrado' :
    '▶ Ejecutar descifrado';

  document.getElementById('page-subtitle').textContent =
    currentMode === 'full'
      ? 'Compara el cifrado y el descifrado de imágenes mediante un autómata celular reversible con vecindad de Moore en Java, C y C#.'
      : 'Recupera imágenes a partir de los archivos generados por el proceso de cifrado basado en un autómata celular reversible con vecindad de Moore.';

  restoreResultsForCurrentMode();
}

function bindResultsNavigation() {
  const nav = document.getElementById('results-nav');
  if (!nav || nav.dataset.bound === '1') return;

  nav.addEventListener('click', event => {
    const btn = event.target.closest('.results-nav-link');
    if (!btn) return;
    const target = document.getElementById(btn.dataset.target || '');
    if (!target || target.classList.contains('panel-hidden')) return;
    target.scrollIntoView({ behavior: 'smooth', block: 'start' });
    setActiveResultsNavItem(btn.dataset.target);
  });

  nav.dataset.bound = '1';
}

function bindResultsTabs() {
  const tabs = document.getElementById('results-tabs');
  if (!tabs || tabs.dataset.bound === '1') return;

  tabs.addEventListener('click', event => {
    const btn = event.target.closest('.results-tab');
    if (!btn || btn.classList.contains('panel-hidden')) return;
    activateResultsPanel(btn.dataset.panel || '');
  });

  tabs.dataset.bound = '1';
}

function activateResultsPanel(panelId) {
  const panels = ['results-summary-panel', 'results-analysis-panel', 'results-guide-panel'];
  panels.forEach(id => {
    document.getElementById(id)?.classList.toggle('panel-hidden', id !== panelId);
  });
  document.querySelectorAll('.results-tab').forEach(tab => {
    tab.classList.toggle('active', tab.dataset.panel === panelId);
  });
  updateResultsNavigation(currentMode, panelId);
  const firstVisible = document.querySelector(`#${panelId} .section-title:not(.panel-hidden), #${panelId} .result-action:not(.panel-hidden)`);
  if (firstVisible) {
    setActiveResultsNavItem(firstVisible.id || '');
  }
  if (panelId === 'results-guide-panel') {
    const results = document.getElementById('results');
    const tabs = document.getElementById('results-tabs');
    if (results) {
      requestAnimationFrame(() => {
        const offset = (tabs?.offsetHeight || 0) + 18;
        const top = results.getBoundingClientRect().top + window.scrollY - offset;
        window.scrollTo({ top: Math.max(0, top), behavior: 'smooth' });
      });
    }
  }
}

function setActiveResultsNavItem(targetId) {
  document.querySelectorAll('.results-nav-link').forEach(link => {
    link.classList.toggle('active', link.dataset.target === targetId);
  });
}

function updateResultsTabs(mode) {
  const tabs = document.getElementById('results-tabs');
  const tabsLabel = document.getElementById('results-tabs-label');
  if (!tabs) return;

  const tabButtons = Array.from(tabs.querySelectorAll('.results-tab'));
  tabButtons.forEach(tab => {
    const panel = tab.dataset.panel;
    const shouldShow = mode === 'full'
      ? true
      : panel === 'results-summary-panel';
    tab.classList.toggle('panel-hidden', !shouldShow);
  });

  const visibleTabs = tabButtons.filter(tab => !tab.classList.contains('panel-hidden'));
  tabs.classList.toggle('panel-hidden', visibleTabs.length <= 1);
  tabsLabel?.classList.toggle('panel-hidden', visibleTabs.length <= 1);

  const preferredPanel = 'results-summary-panel';
  const currentActive = tabButtons.find(tab => tab.classList.contains('active') && !tab.classList.contains('panel-hidden'));
  activateResultsPanel(currentActive?.dataset.panel || preferredPanel);
}

function updateResultsNavigation(mode, activePanelId) {
  const nav = document.getElementById('results-nav');
  const navLabel = document.getElementById('results-nav-label');
  if (!nav) return;

  const panelTargets = {
    'results-summary-panel': [],
    'results-analysis-panel': ['perf-section-title', 'metricas-criptograficas', 'hist-section-title', 'table-section-title', 'download-section-title', 'export-section-title'],
    'results-guide-panel': [],
  };
  const allowedTargets = new Set(panelTargets[activePanelId] || []);

  document.querySelectorAll('.results-nav-link').forEach(link => {
    const linkMode = link.dataset.mode;
    const target = document.getElementById(link.dataset.target || '');
    const targetPanel = target?.closest('.results-panel')?.id;
    const panelMatches = targetPanel === activePanelId;
    const isAllowedInPanel = allowedTargets.has(link.dataset.target || '');
    const shouldShow = (!linkMode || linkMode === mode) && !!target && !target.classList.contains('panel-hidden') && panelMatches && isAllowedInPanel;
    link.classList.toggle('panel-hidden', !shouldShow);
  });

  const visibleLinks = Array.from(nav.querySelectorAll('.results-nav-link'))
    .filter(link => !link.classList.contains('panel-hidden'));
  const shouldShowNav = visibleLinks.length > 0;
  nav.classList.toggle('panel-hidden', !shouldShowNav);
  navLabel?.classList.toggle('panel-hidden', !shouldShowNav);

  const firstVisible = visibleLinks
    .find(link => !link.classList.contains('panel-hidden'));
  setActiveResultsNavItem(firstVisible?.dataset.target || '');
  if (shouldShowNav) {
    bindResultsNavObserver(mode, activePanelId);
  } else if (resultNavObserver) {
    resultNavObserver.disconnect();
    resultNavObserver = null;
  }
}

function bindResultsNavObserver(mode, activePanelId) {
  if (resultNavObserver) {
    resultNavObserver.disconnect();
    resultNavObserver = null;
  }

  const targets = [
    'images-section-title',
    ...(mode === 'full'
      ? ['download-section-title', 'perf-section-title', 'metricas-criptograficas', 'hist-section-title', 'table-section-title', 'guide-section-title', 'how-section-title']
      : ['export-section-title'])
  ]
    .map(id => document.getElementById(id))
    .filter(el => el && !el.classList.contains('panel-hidden') && el.closest('.results-panel')?.id === activePanelId);

  if (!targets.length) return;

  resultNavObserver = new IntersectionObserver(entries => {
    const visible = entries
      .filter(entry => entry.isIntersecting)
      .sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];
    if (visible?.target?.id) {
      setActiveResultsNavItem(visible.target.id);
    }
  }, {
    root: null,
    rootMargin: '-80px 0px -55% 0px',
    threshold: [0.2, 0.4, 0.65]
  });

  targets.forEach(target => resultNavObserver.observe(target));
}

function focusResultsStart() {
  const results = document.getElementById('results');
  if (!results) return;
  requestAnimationFrame(() => {
    results.scrollIntoView({ behavior: 'smooth', block: 'start' });
  });
}

// ── Run ───────────────────────────────────────────────────────────────
async function runOperation() {
  if (currentMode === 'full' && !uploadedFile) return;
  if (currentMode === 'decrypt') {
    const cipher = document.getElementById('decrypt-cipher').files[0];
    const prev = document.getElementById('decrypt-prev').files[0];
    const session = document.getElementById('decrypt-session').files[0];
    if (!cipher || !prev || !session) {
      showUiDialog('Archivos incompletos', 'Selecciona los tres archivos requeridos para ejecutar el descifrado: .bin, .prev.bin y .session.txt.');
      return;
    }
  }
  const btn = document.getElementById('run-btn');
  btn.disabled = true;

  const prog = document.getElementById('progress');
  prog.style.display = 'flex';
  hideResultsView();

  // Reset progress rows
  ['java','c','cs'].forEach(l => {
    const sp  = document.getElementById('sp-'+l);
    const row = document.getElementById('row-'+l);
    const msg = document.getElementById('msg-'+l);
    if (sp)  { sp.style.display=''; }
    if (row) { row.style.opacity = l==='java' ? '1' : '0.4'; row.querySelectorAll('.check').forEach(x=>x.remove()); }
    if (msg) msg.textContent = l==='java' ? 'Ejecutando Java…' : l==='c' ? 'Esperando C…' : 'Esperando C#…';
  });

  const fd = new FormData();
  let endpoint = '/api/run';
  if (currentMode === 'full') {
    fd.append('image', uploadedFile);
    const sessionMode = document.querySelector('input[name="session-mode"]:checked')?.value || 'independent';
    const roundsInput = document.getElementById('rounds-input');
    const rounds = Math.max(1, Math.min(10000, parseInt(roundsInput?.value || '10', 10) || 10));
    if (roundsInput) roundsInput.value = String(rounds);
    fd.append('session_mode', sessionMode);
    fd.append('steps', String(rounds));
    endpoint = '/api/run';
  } else {
    fd.append('cipher', document.getElementById('decrypt-cipher').files[0]);
    fd.append('prev', document.getElementById('decrypt-prev').files[0]);
    fd.append('session', document.getElementById('decrypt-session').files[0]);
    endpoint = '/api/decrypt-only';
  }

  let data;
  try {
    const resp = await fetch(endpoint, { method:'POST', body:fd });
    if (!resp.ok) {
      const errData = await resp.json().catch(()=>({error:'HTTP '+resp.status}));
      throw new Error(errData.error || ('HTTP '+resp.status));
    }
    data = await resp.json();
  } catch(err) {
    console.warn('No se pudo ejecutar el backend', err);
    showUiDialog('Error de ejecución', err.message || 'No se pudo ejecutar el backend.');
    btn.disabled = false;
    prog.style.display = 'none';
    return;
  }

  const results = data.results || [];
  const jR = results.find(r=>r.lang==='Java') || {};
  const cR = results.find(r=>r.lang==='C')    || {};
  const csR= results.find(r=>r.lang==='C#')   || {};

  if (currentMode === 'decrypt') {
    setProgress('java','done', 'Preparando salida…');
    setProgress('c',   'done', 'Descifrado listo ✓');
    setProgress('cs',  'done', 'Listo');
  } else {
    setProgress('java','done', jR.error  ? 'Java ⚠ error'          : 'Java listo ✓');
    setProgress('c',   'done', cR.error  ? 'C ⚠ no compilado'      : 'C listo ✓');
    setProgress('cs',  'done', csR.error ? 'C# ⚠ no compilado'     : 'C# listo ✓');
  }

  await delay(350);
  prog.style.display = 'none';
  if (currentMode === 'decrypt') {
    lastDecryptResultData = data;
    renderDecryptOnlyResult(data);
  } else {
    lastFullResultData = data;
    renderResults(data, currentMode);
  }
  focusResultsStart();
  btn.disabled = false;
}

let lightboxBound = false;
let lightboxImages = [];
let lightboxIndex = -1;

function bindImageZoom() {
  const results = document.getElementById('results');
  const lightbox = document.getElementById('image-lightbox');
  const lightboxImage = document.getElementById('lightbox-image');
  const lightboxCaption = document.getElementById('lightbox-caption');
  const closeBtn = document.getElementById('lightbox-close');
  const prevBtn = document.getElementById('lightbox-prev');
  const nextBtn = document.getElementById('lightbox-next');
  if (!results || !lightbox || !lightboxImage || !lightboxCaption || !closeBtn || !prevBtn || !nextBtn) return;

  const getZoomableImages = () => Array.from(results.querySelectorAll('img[data-lightbox="1"]'));
  lightboxImages = getZoomableImages();

  const renderLightboxImage = () => {
    if (lightboxIndex < 0 || lightboxIndex >= lightboxImages.length) return;
    const img = lightboxImages[lightboxIndex];
    lightboxImage.src = img.src;
    lightboxImage.alt = img.alt || 'Vista ampliada';
    const label = img.dataset.kind || img.closest('.img-card')?.querySelector('.img-label')?.textContent?.trim() || img.alt || 'Imagen';
    const lang = (img.dataset.lang || '').trim();
    lightboxCaption.textContent = lang ? `${lang} · ${label}` : label;
  };

  const openLightbox = (index) => {
    lightboxImages = getZoomableImages();
    lightboxIndex = index;
    renderLightboxImage();
    lightbox.classList.remove('panel-hidden');
    lightbox.setAttribute('aria-hidden', 'false');
    document.body.classList.add('lightbox-open');
  };

  const closeLightbox = () => {
    lightbox.classList.add('panel-hidden');
    lightbox.setAttribute('aria-hidden', 'true');
    lightboxImage.removeAttribute('src');
    lightboxCaption.textContent = 'Vista ampliada';
    lightboxIndex = -1;
    document.body.classList.remove('lightbox-open');
  };

  const moveLightbox = (delta) => {
    if (!lightboxImages.length) return;
    lightboxIndex = (lightboxIndex + delta + lightboxImages.length) % lightboxImages.length;
    renderLightboxImage();
  };

  if (!lightboxBound) {
    results.addEventListener('click', (event) => {
      const target = event.target.closest('img[data-lightbox="1"]');
      if (!target) return;
      const images = getZoomableImages();
      const index = images.indexOf(target);
      if (index >= 0) openLightbox(index);
    });

    closeBtn.addEventListener('click', closeLightbox);
    prevBtn.addEventListener('click', () => moveLightbox(-1));
    nextBtn.addEventListener('click', () => moveLightbox(1));
    lightbox.addEventListener('click', (event) => {
      if (event.target === lightbox) closeLightbox();
    });
    document.addEventListener('keydown', (event) => {
      if (lightbox.classList.contains('panel-hidden')) return;
      if (event.key === 'Escape') closeLightbox();
      if (event.key === 'ArrowLeft') moveLightbox(-1);
      if (event.key === 'ArrowRight') moveLightbox(1);
    });
    lightboxBound = true;
  }
}

function setProgress(lang, state, msg) {
  const sp  = document.getElementById('sp-'+lang);
  const row = document.getElementById('row-'+lang);
  const msgEl = document.getElementById('msg-'+lang);
  if (row) row.style.opacity = '1';
  if (msgEl) msgEl.textContent = msg;
  if (state==='done' && sp) {
    sp.style.display = 'none';
    if (row && !row.querySelector('.check'))
      msgEl.insertAdjacentHTML('beforebegin','<span class="check">✓</span> ');
  }
}

// ── Lang meta ─────────────────────────────────────────────────────────
const LM = {
  'Java': {color:'var(--java-color)', cls:'lang-java', icon:'<img class="lang-icon" src="/static/img/java.svg" alt="Java">'},
  'C':    {color:'var(--c-color)', cls:'lang-c',    icon:'<img class="lang-icon" src="/static/img/c.svg" alt="C">'},
  'C#':   {color:'var(--cs-color)', cls:'lang-cs',   icon:'<img class="lang-icon" src="/static/img/c-sharp.svg" alt="C#">'},
};

function getLastMetric(result) {
  const metrics = result?.metrics || [];
  return metrics[metrics.length - 1] || {};
}

function formatRecoveryLabel(value) {
  if (value === 'OK') return 'Exacta';
  if (value === 'FAIL') return 'Fallida';
  return '—';
}

function renderSummaryDashboard(data, mode = 'full') {
  const overview = document.getElementById('summary-overview');
  const highlights = document.getElementById('summary-highlights');
  const cards = document.getElementById('summary-language-cards');
  const actions = document.getElementById('summary-actions');
  if (!overview || !highlights || !cards || !actions) return;

  const results = data.results || [];
  const cleanResults = results.filter(r => !r.error);
  const sessionMode = data.session_mode === 'shared' ? 'Compartida' : 'Independiente';
  const rounds = data.steps || Number(document.getElementById('rounds-input')?.value || 0) || null;
  const fastest = cleanResults
    .filter(r => Number.isFinite(r.elapsed_s))
    .sort((a, b) => a.elapsed_s - b.elapsed_s)[0];
  const bestEntropy = cleanResults
    .map(r => ({ lang: r.lang, entropy: getLastMetric(r).entropy }))
    .filter(item => Number.isFinite(item.entropy))
    .sort((a, b) => b.entropy - a.entropy)[0];
  const bestCorr = cleanResults
    .map(r => ({ lang: r.lang, corr: Math.abs(getLastMetric(r).corr) }))
    .filter(item => Number.isFinite(item.corr))
    .sort((a, b) => a.corr - b.corr)[0];
  const recoveredCount = results.filter(r => r.recovery === 'OK').length;
  const statusClass = mode === 'decrypt'
    ? (recoveredCount ? 'ok' : 'error')
    : (recoveredCount === results.length ? 'ok' : recoveredCount > 0 ? 'warn' : 'error');
  const statusText = mode === 'decrypt'
    ? (recoveredCount ? 'Descifrado disponible' : 'No se recuperó ninguna imagen')
    : (recoveredCount === results.length ? 'Recuperación correcta en todas las implementaciones' : recoveredCount > 0 ? 'Recuperación parcial' : 'Sin recuperación exacta');

  overview.innerHTML = `
    <div class="summary-hero-top">
      <div>
        <div class="summary-kicker">${mode === 'full' ? 'Resumen ejecutivo' : 'Resumen de descifrado'}</div>
        <div class="summary-title">${fastest ? `${fastest.lang} lidera el resultado actual` : 'Resultado disponible para revisión'}</div>
        <div class="summary-copy">
          ${mode === 'full'
            ? 'Esta vista concentra el resultado general, los indicadores más relevantes y las acciones principales sin obligarte a entrar al análisis completo.'
            : 'Esta vista resume el estado del descifrado, las implementaciones disponibles y las acciones de exportación.'}
        </div>
      </div>
      <div class="summary-status ${statusClass}">${statusText}</div>
    </div>
    <div class="summary-meta">
      ${rounds ? `<div class="summary-chip">Rondas: <strong>${rounds}</strong></div>` : ''}
      ${mode === 'full' ? `<div class="summary-chip">Sesión: <strong>${sessionMode}</strong></div>` : ''}
      <div class="summary-chip">Implementaciones válidas: <strong>${cleanResults.length}/${results.length}</strong></div>
      ${fastest ? `<div class="summary-chip">Más rápida: <strong>${fastest.lang}</strong></div>` : ''}
    </div>
  `;

  const highlightItems = mode === 'full'
    ? [
        {
          label: 'Más rápida',
          value: fastest ? `${fastest.lang} · ${fastest.elapsed_s.toFixed(4)}s` : '—',
          note: 'Menor tiempo total observado en la ejecución actual.'
        },
        {
          label: 'Mayor entropía',
          value: bestEntropy ? `${bestEntropy.lang} · ${bestEntropy.entropy.toFixed(4)} bits` : '—',
          note: 'Valor más cercano a la distribución idealmente incierta.'
        },
        {
          label: 'Mejor correlación',
          value: bestCorr ? `${bestCorr.lang} · ${bestCorr.corr.toFixed(4)}` : '—',
          note: 'Valor absoluto más cercano a cero entre píxeles vecinos.'
        },
        {
          label: 'Recuperación',
          value: `${recoveredCount}/${results.length}`,
          note: 'Implementaciones que recuperaron la imagen exactamente.'
        }
      ]
    : [
        {
          label: 'Recuperación disponible',
          value: `${cleanResults.length}/${results.length}`,
          note: 'Implementaciones que generaron una salida exportable.'
        },
        {
          label: 'Más rápida',
          value: fastest ? `${fastest.lang} · ${fastest.elapsed_s.toFixed(4)}s` : '—',
          note: 'Menor tiempo total observado en el descifrado actual.'
        }
      ];
  highlights.innerHTML = highlightItems.map(item => `
    <div class="summary-highlight">
      <div class="summary-highlight-label">${item.label}</div>
      <div class="summary-highlight-value">${item.value}</div>
      <div class="summary-highlight-note">${item.note}</div>
    </div>
  `).join('');

  cards.innerHTML = results.map(result => {
    const meta = LM[result.lang] || {};
    const metric = getLastMetric(result);
    const imageItems = mode === 'full'
      ? [
          { label: 'Original', kind: 'Original', src: data.original_img || '' },
          { label: 'Cifrada', kind: 'Cifrada', src: result.cipher_img || '' },
          { label: 'Descifrada', kind: 'Descifrada', src: result.recovered_img || '' }
        ].filter(item => item.src)
      : [
          { label: 'Descifrada', kind: 'Descifrada', src: result.recovered_img || '' }
        ].filter(item => item.src);
    return `
      <div class="summary-language-card">
        <div class="summary-language-head">
          <div class="summary-language-name ${meta.cls || ''}">${meta.icon || ''} ${result.lang || '?'}</div>
          <div class="summary-language-badge">${result.error ? 'Con incidencia' : (mode === 'full' ? formatRecoveryLabel(result.recovery) : (result.status || 'OK'))}</div>
        </div>
        <div class="summary-language-visual">
          ${imageItems.length ? `
            <div class="summary-image-strip">
              ${imageItems.map(item => `
                <div class="summary-image-card">
                  <img
                    src="data:image/png;base64,${item.src}"
                    alt="${item.kind} ${result.lang || ''}"
                    data-lightbox="1"
                    data-lang="${result.lang || ''}"
                    data-kind="${item.kind}">
                  <div class="summary-image-label">${item.label}</div>
                </div>
              `).join('')}
            </div>
          ` : ''}
          <div class="summary-language-stats">
            <div class="summary-stat"><span class="summary-stat-label">Tiempo</span><span class="summary-stat-value">${Number.isFinite(result.elapsed_s) ? `${result.elapsed_s.toFixed(4)}s` : '—'}</span></div>
            ${mode === 'full' ? `
              <div class="summary-stat"><span class="summary-stat-label">Entropía</span><span class="summary-stat-value">${Number.isFinite(metric.entropy) ? `${metric.entropy.toFixed(4)} bits` : '—'}</span></div>
              <div class="summary-stat"><span class="summary-stat-label">Correlación</span><span class="summary-stat-value">${Number.isFinite(metric.corr) ? metric.corr.toFixed(4) : '—'}</span></div>
              <div class="summary-stat"><span class="summary-stat-label">Recuperación</span><span class="summary-stat-value">${formatRecoveryLabel(result.recovery)}</span></div>
            ` : `
              <div class="summary-stat"><span class="summary-stat-label">Estado</span><span class="summary-stat-value">${result.status || (result.error ? 'ERROR' : 'OK')}</span></div>
              <div class="summary-stat"><span class="summary-stat-label">Formato</span><span class="summary-stat-value">${result.output_format_label || '—'}</span></div>
              <div class="summary-stat"><span class="summary-stat-label">SHA-256</span><span class="summary-stat-value">${result.sha256_output ? `${result.sha256_output.slice(0, 12)}…` : '—'}</span></div>
            `}
          </div>
        </div>
      </div>
    `;
  }).join('');

  actions.innerHTML = '';
  if (mode === 'full') {
    if (data.bundle_url) {
      actions.innerHTML += `<button class="secondary-btn" id="summary-download-bundle-btn">Descargar archivos del cifrado (.zip)</button>`;
    }
    actions.innerHTML += `<button class="secondary-btn" id="summary-open-analysis-btn">Ir a análisis</button>`;
    document.getElementById('summary-download-bundle-btn')?.addEventListener('click', () => {
      saveUrlWithPicker(data.bundle_url, data.bundle_name || 'cipher_bundle.zip');
    });
    document.getElementById('summary-open-analysis-btn')?.addEventListener('click', () => {
      activateResultsPanel('results-analysis-panel');
    });
  } else {
    const exportableResults = results.filter(r => r.download_url && r.download_name);
    if (exportableResults.length) {
      actions.innerHTML += `<button class="secondary-btn" id="summary-open-export-btn">Guardar imagen descifrada</button>`;
      document.getElementById('summary-open-export-btn')?.addEventListener('click', () => {
        openExportDialog(exportableResults);
      });
    }
  }
}

// ── Render ────────────────────────────────────────────────────────────
function renderResults(data, mode='full') {
  const res = document.getElementById('results');
  res.style.display = 'block';
  res.classList.add('fade-in');
  setResultSectionsForMode(mode);
  const encryptActions = document.getElementById('encrypt-actions');
  const decryptActions = document.getElementById('decrypt-actions');
  encryptActions.innerHTML = '';
  decryptActions.innerHTML = '';

  const results = data.results || [];
  const sessionMode = data.session_mode || 'independent';
  const jR  = results.find(r=>r.lang==='Java') || {};
  const cR  = results.find(r=>r.lang==='C')    || {};
  const csR = results.find(r=>r.lang==='C#')   || {};

  // ── Performance ──────────────────────────────────────────────────
  const times = [jR,cR,csR].map(r=>r.elapsed_s||0).filter(Boolean);
  const maxT = Math.max(...times, 0.001);
  const minT = Math.min(...times.filter(x=>x>0), 9999);
  document.getElementById('perf-row').innerHTML = [jR,cR,csR].map(r => {
    const m=LM[r.lang]||{}, t=r.elapsed_s||0, pct=(t/maxT*100).toFixed(1);
    const isFastest = times.length>1 && t===minT;
    return `<div class="perf-bar-wrap">
      <div class="perf-lang-label" style="color:${m.color}">${m.icon||''} ${r.lang||'?'}</div>
      <div class="perf-time-label">${r.error?'N/A':t.toFixed(4)+'s'}</div>
      <div class="perf-bar-track"><div class="perf-bar-fill" style="width:${r.error?0:pct}%;background:${m.color}"></div></div>
      <div class="perf-rel">${r.error ? '⚠ Implementación no disponible' : isFastest ? '🏆 más rápido' : (t>0 ? (t/minT).toFixed(2)+'× vs más rápido' : '—')}</div>
    </div>`;
  }).join('');

  // ── Metric cards ─────────────────────────────────────────────────
  document.getElementById('metrics-cards').innerHTML = [jR,cR,csR].map(r => {
    const m=LM[r.lang]||{}, mets=r.metrics||[], last=mets[mets.length-1]||{};
    const e=last.entropy||0, chi=last.chi||0, corr=last.corr||0, ePct=(e/8*100).toFixed(1);
    return `<div class="metric-card">
      <div class="metric-card-header">
        <span class="metric-lang ${m.cls||''}">${m.icon||''} ${r.lang||'?'}</span>
        <span class="metric-time">${r.elapsed_s?r.elapsed_s.toFixed(4)+'s':'N/A'}</span>
      </div>
      ${r.error?`<div style="font-size:.82rem;color:#f87171;line-height:1.6;font-weight:700">${UI_IMPLEMENTATION_ERROR}</div>`
        :`<div class="metric-row"><a class="metric-link" href="#desc-entropia">Entropía</a><span class="metric-value" style="color:${m.color}">${e.toFixed(4)} bits</span></div>
         <div class="metric-bar-track"><div class="metric-bar-fill" style="width:${ePct}%;background:${m.color}"></div></div>
         <div class="metric-row"><a class="metric-link" href="#desc-chi">Chi²</a><span class="metric-value">${chi.toFixed(1)}</span></div>
         <div class="metric-row"><a class="metric-link" href="#desc-correlacion">Correlación</a><span class="metric-value">${corr.toFixed(4)}</span></div>
         <div class="metric-row"><span class="metric-name">Recuperación</span><span class="${r.recovery==='OK'?'recovery-ok':'recovery-fail'}">${r.recovery||'—'}</span></div>`}
    </div>`;
  }).join('');

  // ── Histograms ──────────────────────────────────────────────────
  const histCards = [
    {label:'Original', color:'var(--muted)', hist:data.original_histogram},
    {label:'Java cifrada', color:LM.Java.color, hist:jR.histogram, error:jR.error},
    {label:'C cifrada', color:LM.C.color, hist:cR.histogram, error:cR.error},
    {label:'C# cifrada', color:LM['C#'].color, hist:csR.histogram, error:csR.error},
  ];
  document.getElementById('histogram-grid').innerHTML = histCards.map((item, idx) => `
    <div class="hist-card">
      <div class="hist-head">
        <div class="chart-title" style="color:${item.color};margin-bottom:0">${item.label}</div>
        ${item.error ? '' : `<div class="hist-controls" data-hist="hist-${idx}">
          <button class="hist-btn active" data-ch="r" type="button">R</button>
          <button class="hist-btn active" data-ch="g" type="button">G</button>
          <button class="hist-btn active" data-ch="b" type="button">B</button>
          <button class="hist-btn" data-ch="reset" type="button">Reset</button>
        </div>`}
      </div>
      ${item.error ? `<div style="font-size:.7rem;color:#f87171">${item.error.substring(0,100)}</div>` : `
        <canvas class="hist-canvas" id="hist-${idx}"></canvas>
        <div class="hist-help">Rueda: zoom · Arrastra: desplazar · Doble clic: reset · Mouse: valor del bin</div>
      `}
    </div>
  `).join('');
  histCards.forEach((item, idx) => {
    if (!item.error && item.hist) drawHistogram(`hist-${idx}`, item.hist);
  });

  // ── Table ────────────────────────────────────────────────────────
  const last=r=>(r.metrics||[])[(r.metrics||[]).length-1]||{};
  const rows=[
    {f:'Modo sesión',  j:sessionMode==='shared'?'Compartida':'Independiente', c:sessionMode==='shared'?'Compartida':'Independiente', cs:sessionMode==='shared'?'Compartida':'Independiente'},
    {f:'Tiempo (s)',   j:jR.elapsed_s?.toFixed(4), c:cR.elapsed_s?.toFixed(4), cs:csR.elapsed_s?.toFixed(4)},
    {f:'Entropía',     j:last(jR).entropy?.toFixed(4), c:last(cR).entropy?.toFixed(4), cs:last(csR).entropy?.toFixed(4)},
    {f:'Chi²',         j:last(jR).chi?.toFixed(2),     c:last(cR).chi?.toFixed(2),     cs:last(csR).chi?.toFixed(2)},
    {f:'Correlación',  j:last(jR).corr?.toFixed(4),    c:last(cR).corr?.toFixed(4),    cs:last(csR).corr?.toFixed(4)},
    {f:'SHA-256/Recuperación', j:`MessageDigest / ${jR.recovery||'—'}`, c:`OpenSSL / ${cR.recovery||'—'}`, cs:`System.Security / ${csR.recovery||'—'}`},
    {f:'Entorno de ejecución', j:'JVM', c:'nativo -O2', cs:'.NET 8'},
  ];
  document.getElementById('comparison-table').innerHTML=`<div style="background:var(--surface);border:1px solid var(--border);border-radius:8px;overflow:hidden;padding:1rem">
    <table style="width:100%;border-collapse:collapse;font-size:.78rem">
      <thead><tr style="border-bottom:1px solid var(--border)">
        <th style="text-align:left;padding:.6rem .4rem;color:var(--muted);font-weight:400;font-size:.65rem;text-transform:uppercase;letter-spacing:.1em">Campo</th>
        <th style="padding:.6rem;color:var(--java-color);font-weight:700">${LM.Java.icon} Java</th>
        <th style="padding:.6rem;color:var(--c-color);font-weight:700">${LM.C.icon} C</th>
        <th style="padding:.6rem;color:var(--cs-color);font-weight:700">${LM['C#'].icon} C#</th>
      </tr></thead>
      <tbody>${rows.map((r,i)=>`<tr style="border-bottom:1px solid var(--border);background:${i%2?'rgba(255,255,255,.01)':'transparent'}">
        <td style="padding:.5rem .4rem;color:var(--muted)">${r.f}</td>
        <td style="padding:.5rem;text-align:center;color:var(--java-color)">${r.j??'—'}</td>
        <td style="padding:.5rem;text-align:center;color:var(--c-color)">${r.c??'—'}</td>
        <td style="padding:.5rem;text-align:center;color:var(--cs-color)">${r.cs??'—'}</td>
      </tr>`).join('')}</tbody>
    </table></div>`;



  if (mode === 'full') {
    if (data.bundle_url) {
      encryptActions.innerHTML = `
        <button class="secondary-btn" id="download-bundle-btn">Descargar archivos del cifrado (.zip)</button>
      `;
      document.getElementById('download-bundle-btn').addEventListener('click', () => {
        saveUrlWithPicker(data.bundle_url, data.bundle_name || 'cipher_bundle.zip');
      });
    } else {
      encryptActions.innerHTML = `
        <button class="secondary-btn" type="button" disabled>No hay paquete cifrado disponible</button>
      `;
    }
  }
  bindImageZoom();
  renderSummaryDashboard(data, 'full');
  updateResultsTabs(mode);
}

function renderDecryptOnlyResult(data) {
  const res = document.getElementById('results');
  res.style.display = 'block';
  res.classList.add('fade-in');
  setResultSectionsForMode('decrypt');
  document.getElementById('perf-row').innerHTML = '';
  document.getElementById('metrics-cards').innerHTML = '';
  document.getElementById('histogram-grid').innerHTML = '';
  document.getElementById('comparison-table').innerHTML = '';
  const results = data.results || [];
  const jR  = results.find(r=>r.lang==='Java') || {};
  const cR  = results.find(r=>r.lang==='C')    || {};
  const csR = results.find(r=>r.lang==='C#')   || {};
  document.getElementById('encrypt-actions').innerHTML = '';
  const actions = document.getElementById('decrypt-actions');
  const exportableResults = [jR, cR, csR].filter(r => r.download_url && r.download_name);
  actions.innerHTML = exportableResults.length
    ? '<button class="secondary-btn" id="open-export-dialog-btn">Guardar imagen descifrada</button>'
    : '';
  document.getElementById('open-export-dialog-btn')?.addEventListener('click', () => {
    openExportDialog(exportableResults);
  });
  bindImageZoom();
  renderSummaryDashboard(data, 'decrypt');
  updateResultsTabs('decrypt');
}

function setResultSectionsForMode(mode) {
  const showCompareBlocks = mode !== 'decrypt';
  ['download-section-title','perf-section-title','perf-row','metricas-criptograficas','metrics-cards','hist-section-title','histogram-grid','table-section-title','comparison-table'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.classList.toggle('panel-hidden', !showCompareBlocks);
  });
  ['export-section-title', 'decrypt-actions'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.classList.toggle('panel-hidden', mode !== 'decrypt');
  });
  ['guide-section-title','guide-grid','back-metrics-link','how-section-title','how-grid','guide-note'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.classList.toggle('panel-hidden', mode === 'decrypt');
  });
  const encryptActions = document.getElementById('encrypt-actions');
  if (encryptActions) encryptActions.classList.toggle('panel-hidden', mode === 'decrypt');
}

async function saveUrlWithPicker(url, suggestedName) {
  try {
    const resp = await fetch(url);
    if (!resp.ok) throw new Error('No se pudo descargar el archivo.');
    const blob = await resp.blob();
    if (window.showSaveFilePicker) {
      const handle = await window.showSaveFilePicker({
        suggestedName,
        types: [{ description: 'Archivo', accept: { [blob.type || 'application/octet-stream']: ['.' + suggestedName.split('.').pop()] } }]
      });
      const writable = await handle.createWritable();
      await writable.write(blob);
      await writable.close();
      return;
    }
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = suggestedName;
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(link.href), 5000);
  } catch (err) {
    showUiDialog('No se pudo guardar el archivo', err.message || 'No se pudo guardar el archivo.');
  }
}

const histogramStates = {};

function drawHistogram(id,hist){
  const canvas=document.getElementById(id); if(!canvas||!hist) return;
  histogramStates[id]={
    hist,
    min:0,
    max:255,
    hover:null,
    drag:false,
    lastX:0,
    channels:{r:true,g:true,b:true}
  };
  attachHistogramEvents(id);
  renderHistogram(id);
}

function attachHistogramEvents(id){
  const canvas=document.getElementById(id); if(!canvas||canvas.dataset.ready) return;
  canvas.dataset.ready='1';
  const relX=e=>e.clientX-canvas.getBoundingClientRect().left;
  canvas.addEventListener('mousemove',e=>{
    const st=histogramStates[id]; if(!st) return;
    const x=relX(e), W=canvas.offsetWidth, pad={l:48,r:16};
    if(st.drag){
      const span=st.max-st.min;
      const dx=x-st.lastX;
      const shift=-(dx/(W-pad.l-pad.r))*span;
      setHistogramRange(st,st.min+shift,st.max+shift);
      st.lastX=x;
    }
    st.hover=x;
    renderHistogram(id);
  });
  canvas.addEventListener('mouseleave',()=>{const st=histogramStates[id]; if(st){st.hover=null;st.drag=false;renderHistogram(id);}});
  canvas.addEventListener('mousedown',e=>{const st=histogramStates[id]; if(st){st.drag=true;st.lastX=relX(e);}});
  window.addEventListener('mouseup',()=>{const st=histogramStates[id]; if(st) st.drag=false;});
  canvas.addEventListener('dblclick',()=>{const st=histogramStates[id]; if(st){st.min=0;st.max=255;renderHistogram(id);}});
  canvas.addEventListener('wheel',e=>{
    e.preventDefault();
    const st=histogramStates[id]; if(!st) return;
    const W=canvas.offsetWidth,pad={l:48,r:16},plotW=W-pad.l-pad.r;
    const x=Math.max(0,Math.min(plotW,relX(e)-pad.l));
    const center=st.min+(x/plotW)*(st.max-st.min);
    const factor=e.deltaY<0?.78:1.28;
    const newSpan=Math.max(8,Math.min(255,(st.max-st.min)*factor));
    const leftRatio=(center-st.min)/(st.max-st.min||1);
    setHistogramRange(st,center-newSpan*leftRatio,center+newSpan*(1-leftRatio));
    renderHistogram(id);
  },{passive:false});
  const controls=document.querySelector(`.hist-controls[data-hist="${id}"]`);
  if(controls){
    controls.addEventListener('click',e=>{
      const btn=e.target.closest('.hist-btn'); if(!btn) return;
      const st=histogramStates[id]; if(!st) return;
      const ch=btn.dataset.ch;
      if(ch==='reset'){
        st.min=0;st.max=255;st.channels={r:true,g:true,b:true};
        controls.querySelectorAll('.hist-btn[data-ch="r"],.hist-btn[data-ch="g"],.hist-btn[data-ch="b"]').forEach(b=>b.classList.add('active'));
      }else if(st.channels[ch]!==undefined){
        st.channels[ch]=!st.channels[ch];
        btn.classList.toggle('active',st.channels[ch]);
      }
      renderHistogram(id);
    });
  }
}

function setHistogramRange(st,min,max){
  let span=max-min;
  if(span>=255){st.min=0;st.max=255;return;}
  if(min<0){max-=min;min=0;}
  if(max>255){min-=max-255;max=255;}
  st.min=Math.max(0,min);
  st.max=Math.min(255,max);
}

function renderHistogram(id){
  const canvas=document.getElementById(id),st=histogramStates[id]; if(!canvas||!st) return;
  const dpr=window.devicePixelRatio||1;
  const W=canvas.offsetWidth,H=300,pad={t:18,r:16,b:58,l:86};
  canvas.width=W*dpr; canvas.height=H*dpr;
  const ctx=canvas.getContext('2d'); ctx.scale(dpr,dpr);
  const pw=W-pad.l-pad.r,ph=H-pad.t-pad.b;
  const minBin=Math.max(0,Math.floor(st.min)),maxBin=Math.min(255,Math.ceil(st.max));
  const active=Object.entries(st.channels).filter(([,v])=>v).map(([k])=>k);
  const maxV=Math.max(1,...active.flatMap(ch=>(st.hist[ch]||[]).slice(minBin,maxBin+1)));
  ctx.clearRect(0,0,W,H);

  ctx.strokeStyle='rgba(148,163,184,.28)';ctx.lineWidth=1;
  for(let i=0;i<=5;i++){
    const y=pad.t+ph*(i/5);
    ctx.beginPath();ctx.moveTo(pad.l,y);ctx.lineTo(pad.l+pw,y);ctx.stroke();
    ctx.fillStyle='rgba(15,23,42,.78)';ctx.font="9px 'IBM Plex Mono'";ctx.textAlign='right';
    ctx.fillText(Math.round(maxV-(maxV*i/5)).toString(),pad.l-12,y+3);
  }

  ctx.strokeStyle='rgba(15,23,42,.72)';
  ctx.lineWidth=1.15;
  ctx.beginPath();
  ctx.moveTo(pad.l, pad.t);
  ctx.lineTo(pad.l, pad.t + ph);
  ctx.lineTo(pad.l + pw, pad.t + ph);
  ctx.stroke();

  ctx.save();
  ctx.translate(42, pad.t + ph / 2);
  ctx.rotate(-Math.PI / 2);
  ctx.fillStyle='rgba(15,23,42,.86)';
  ctx.font="11px 'Manrope'";
  ctx.textAlign='center';
  ctx.fillText('Cantidad de píxeles', 0, 0);
  ctx.restore();
  ctx.textAlign='start';

  const xForBin=bin=>pad.l+((bin-st.min)/(st.max-st.min))*pw;
  const yForVal=v=>pad.t+ph-(v/maxV)*ph;
  const drawChannel=(ch,color)=>{
    if(!st.channels[ch]) return;
    const arr=st.hist[ch]||[];
    ctx.beginPath();
    for(let bin=minBin;bin<=maxBin;bin++){
      const x=xForBin(bin),y=yForVal(arr[bin]||0);
      bin===minBin?ctx.moveTo(x,y):ctx.lineTo(x,y);
    }
    ctx.strokeStyle=color;ctx.lineWidth=1.8;ctx.globalAlpha=.9;ctx.stroke();ctx.globalAlpha=1;
  };
  ctx.save();
  ctx.beginPath();
  ctx.rect(pad.l, pad.t, pw, ph);
  ctx.clip();
  drawChannel('r','#ff0000');drawChannel('g','#00ff00');drawChannel('b','#0000ff');
  ctx.restore();
  ctx.fillStyle='rgba(15,23,42,.82)';
  ctx.font="10px 'IBM Plex Mono'";
  const xTickCount = 9;
  const xTicks = Array.from({ length: xTickCount }, (_, i) =>
    st.min + ((st.max - st.min) * i) / (xTickCount - 1)
  );
  xTicks.forEach((value, index) => {
    const rounded = Math.round(value);
    const x = xForBin(value);
    const text = String(rounded);
    const width = ctx.measureText(text).width;
    let tx = x - width / 2;
    if (index === 0) tx = pad.l;
    if (index === xTicks.length - 1) tx = pad.l + pw - width;
    tx = Math.max(pad.l, Math.min(pad.l + pw - width, tx));
    ctx.beginPath();
    ctx.moveTo(x, pad.t + ph);
    ctx.lineTo(x, pad.t + ph + 5);
    ctx.strokeStyle='rgba(15,23,42,.72)';
    ctx.lineWidth=1;
    ctx.stroke();
    ctx.fillText(text, tx, pad.t + ph + 14);
  });

  ctx.fillStyle='rgba(15,23,42,.86)';
  ctx.font="11px 'Manrope'";
  ctx.textAlign='center';
  ctx.fillText('Valor de píxel', pad.l + pw / 2, H - 10);
  ctx.textAlign='start';

  if(st.hover!==null){
    const hx=Math.max(pad.l,Math.min(pad.l+pw,st.hover));
    const bin=Math.max(0,Math.min(255,Math.round(st.min+((hx-pad.l)/pw)*(st.max-st.min))));
    ctx.save();
    ctx.beginPath();
    ctx.rect(pad.l, pad.t, pw, ph);
    ctx.clip();
    ctx.strokeStyle='rgba(0,0,0,.55)';ctx.beginPath();ctx.moveTo(hx,pad.t);ctx.lineTo(hx,pad.t+ph);ctx.stroke();
    ctx.restore();
    const parts=[];
    if(st.channels.r) parts.push(`R:${st.hist.r[bin]||0}`);
    if(st.channels.g) parts.push(`G:${st.hist.g[bin]||0}`);
    if(st.channels.b) parts.push(`B:${st.hist.b[bin]||0}`);
    const txt=`bin ${bin} · ${parts.join(' · ')}`;
    ctx.font="11px 'IBM Plex Mono'";
    const tw=ctx.measureText(txt).width+16;
    const tx=Math.min(W-tw-8,Math.max(8,hx+10));
    ctx.fillStyle='rgba(10,10,15,.92)';ctx.fillRect(tx,8,tw,24);
    ctx.strokeStyle='rgba(255,255,255,.12)';ctx.strokeRect(tx,8,tw,24);
    ctx.fillStyle='rgba(255,255,255,.82)';ctx.fillText(txt,tx+8,24);
  }
}

// ── Simulate demo data ────────────────────────────────────────────────
function simulateData(){
  const steps=10;
  const mkHist=()=>({
    r:Array.from({length:256},(_,i)=>Math.round(80+Math.random()*120+60*Math.sin(i/17))),
    g:Array.from({length:256},(_,i)=>Math.round(80+Math.random()*120+60*Math.sin(i/23))),
    b:Array.from({length:256},(_,i)=>Math.round(80+Math.random()*120+60*Math.sin(i/31))),
  });
  const mkM=(off)=>Array.from({length:steps+1},(_,i)=>({
    gen:i,
    entropy:Math.min(8,Math.max(0,3.5+(i/steps)*4.0+off+(Math.random()-.5)*.15)),
    chi:Math.max(200,28000-i*2200+off*400+(Math.random()-.5)*300),
    corr:Math.max(-1,Math.min(1,0.82-(i/steps)*0.86+(Math.random()-.5)*.04)),
  }));
  const noiseImg=()=>{const c=document.createElement('canvas');c.width=c.height=64;const ctx=c.getContext('2d'),id=ctx.createImageData(64,64);for(let i=0;i<id.data.length;i+=4){id.data[i]=~~(Math.random()*255);id.data[i+1]=~~(Math.random()*255);id.data[i+2]=~~(Math.random()*255);id.data[i+3]=255;}ctx.putImageData(id,0,0);return c.toDataURL('image/png').split(',')[1];};
  const origC=document.createElement('canvas');origC.width=origC.height=64;const oc=origC.getContext('2d');
  oc.fillStyle='#336699';oc.fillRect(0,0,32,32);oc.fillStyle='#cc4422';oc.fillRect(32,0,32,32);
  oc.fillStyle='#22aa55';oc.fillRect(0,32,32,32);oc.fillStyle='#aa22cc';oc.fillRect(32,32,32,32);
  const origB64=origC.toDataURL('image/png').split(',')[1];
  return {image_size:[64,64],steps,session_mode:'independent',original_img:origB64,original_histogram:mkHist(),results:[
    {lang:'Java',elapsed_s:0.83,recovery:'OK',metrics:mkM(0),   histogram:mkHist(),cipher_img:noiseImg(),recovered_img:origB64},
    {lang:'C',   elapsed_s:0.04,recovery:'OK',metrics:mkM(0.08),histogram:mkHist(),cipher_img:noiseImg(),recovered_img:origB64},
    {lang:'C#',  elapsed_s:0.14,recovery:'OK',metrics:mkM(0.04),histogram:mkHist(),cipher_img:noiseImg(),recovered_img:origB64},
  ]};
}

const delay=ms=>new Promise(r=>setTimeout(r,ms));
