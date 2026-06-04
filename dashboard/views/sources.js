// ═══════════════════════════════════════════════════════════════
// views/sources.js
// ═══════════════════════════════════════════════════════════════

import { state, db } from '../state.js';
import { fetchTopics, fetchSources, insertSource, apiFetch } from '../api.js';
import {
  $, $$, toast, esc, applyCustomSelects, typePill, statusPill,
  randomUUID, topicLabel
} from '../utils.js';

export async function renderSources() {
  const mainContent = $('#main-content');
  if (!mainContent) return;

  await Promise.all([fetchTopics(), fetchSources()]);

  mainContent.innerHTML = `
    <h1 class="page-title">Sources</h1>
    <p class="page-subtitle">Manage reference materials</p>

    <div class="segmented-control" id="sources-segments">
      <button class="segmented-btn ${state.sourcesSubView === 'add' ? 'active' : ''}" data-sub="add">Add Source</button>
      <button class="segmented-btn ${state.sourcesSubView === 'list' ? 'active' : ''}" data-sub="list">All Sources</button>
    </div>

    <div id="sources-sub-content"></div>
  `;

  $$('.segmented-btn', $('#sources-segments')).forEach(btn => {
    btn.addEventListener('click', () => {
      state.sourcesSubView = btn.dataset.sub;
      renderSources();
    });
  });

  const sub = $('#sources-sub-content');
  if (state.sourcesSubView === 'add') {
    renderSourceAdd(sub);
  } else {
    renderSourceList(sub);
  }
  applyCustomSelects(sub);
}

function renderSourceAdd(container) {
  container.innerHTML = `
    <div class="max-w-form">
      <div class="radio-group">
        <label class="radio-item">
          <input type="radio" name="src-mode" value="url" ${state.sourceMode === 'url' ? 'checked' : ''} />
          URL
        </label>
        <label class="radio-item">
          <input type="radio" name="src-mode" value="file" ${state.sourceMode === 'file' ? 'checked' : ''} />
          File Upload
        </label>
      </div>

      <div id="src-mode-fields"></div>

      <div class="form-group">
        <label class="form-label">Title</label>
        <input type="text" class="form-input" id="src-title" placeholder="Source title" />
      </div>

      <div class="form-group">
        <label class="form-label">Topics</label>
        <div class="multi-select-wrap" id="src-topics-ms">
          <div class="multi-select-trigger" id="src-topics-trigger">
            <span class="text-muted text-sm">Click to select topics...</span>
          </div>
          <div class="multi-select-dropdown" id="src-topics-dropdown">
            ${state.topics.map(t => {
              const isSelected = state.selectedSourceTopicIds.has(t.id);
              return `<div class="multi-select-option ${isSelected ? 'selected' : ''}" data-id="${t.id}">${esc(topicLabel(t))}</div>`;
            }).join('')}
          </div>
        </div>
      </div>

      <div class="form-group">
        <label class="form-label">Trust Score</label>
        <div class="form-range-wrap">
          <input type="range" class="form-range" id="src-trust" min="1" max="10" step="0.1" value="5" />
          <span class="form-range-value" id="src-trust-val">5</span>
        </div>
      </div>

      <div class="form-actions">
        <button class="btn btn-primary" id="btn-add-source">Add Source</button>
      </div>
    </div>
  `;

  // Radio toggle
  $$('input[name="src-mode"]').forEach(r => {
    r.addEventListener('change', () => {
      state.sourceMode = r.value;
      renderSourceModeFields();
    });
  });
  renderSourceModeFields();

  // Range value
  const range = $('#src-trust');
  const rVal  = $('#src-trust-val');
  range.addEventListener('input', () => rVal.textContent = range.value);

  // Multi-select
  const selectedTopicIds = state.selectedSourceTopicIds;
  const trigger  = $('#src-topics-trigger');
  const dropdown = $('#src-topics-dropdown');

  updateMultiSelectTrigger(trigger, selectedTopicIds);

  trigger.addEventListener('click', (e) => {
    e.stopPropagation();
    dropdown.classList.toggle('open');
  });

  document.addEventListener('click', () => dropdown.classList.remove('open'), { once: false });

  $$('.multi-select-option', dropdown).forEach(opt => {
    opt.addEventListener('click', (e) => {
      e.stopPropagation();
      const id = opt.dataset.id;
      if (selectedTopicIds.has(id)) {
        selectedTopicIds.delete(id);
        opt.classList.remove('selected');
      } else {
        selectedTopicIds.add(id);
        opt.classList.add('selected');
      }
      updateMultiSelectTrigger(trigger, selectedTopicIds);
    });
  });

  // Submit
  $('#btn-add-source').addEventListener('click', async () => {
    const title = $('#src-title').value.trim();
    const trust = parseFloat($('#src-trust').value);
    if (!title) { toast('Title is required', 'error'); return; }

    const src = {
      id: randomUUID(),
      title,
      trust_score: trust,
      topic_ids: [...selectedTopicIds],
      is_active: true,
      created_at: new Date().toISOString(),
      crawl_status: 'pending',
    };

    if (state.sourceMode === 'url') {
      const url = $('#src-url')?.value?.trim();
      if (!url) { toast('URL is required', 'error'); return; }
      src.source_type = 'website';
      src.url = url;
    } else {
      const file = state.selectedFile;
      if (!file) { toast('File is required', 'error'); return; }

      // Upload file raw bytes
      const btn = $('#btn-add-source');
      btn.disabled = true;
      btn.textContent = 'Uploading file...';
      
      try {
        const uploadRes = await apiFetch(`/api/upload?filename=${encodeURIComponent(file.name)}`, {
          method: 'POST',
          body: file
        });
        if (!uploadRes.ok) {
          const errData = await uploadRes.json().catch(() => ({}));
          toast(errData.detail || 'File upload failed', 'error');
          btn.disabled = false;
          btn.textContent = 'Add Source';
          return;
        }
      } catch (err) {
        console.error(err);
        toast('File upload error', 'error');
        btn.disabled = false;
        btn.textContent = 'Add Source';
        return;
      }

      const ext = file.name.split('.').pop().toLowerCase();
      let sourceType = 'website';
      if (ext === 'pdf') {
        sourceType = 'pdf';
      } else if (['png', 'jpg', 'jpeg', 'webp', 'bmp', 'tiff', 'tif'].includes(ext)) {
        sourceType = 'image';
      }
      
      src.source_type = sourceType;
      src.local_path = 'data/uploads/' + file.name;
    }

    const btn = $('#btn-add-source');
    btn.disabled = true;
    btn.textContent = 'Registering...';

    const ok = await insertSource(src);
    if (ok) {
      toast('Source added, triggering ingestion...', 'success');
      // Trigger background ingestion
      apiFetch('/api/ingest', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ source_id: src.id })
      }).catch(err => console.error("Ingest trigger error:", err));
      
      const sub = $('#sources-sub-content');
      showIngestionProgress(sub, src);
    } else {
      btn.disabled = false;
      btn.textContent = 'Add Source';
    }
  });
}

function renderSourceModeFields() {
  const area = $('#src-mode-fields');
  if (!area) return;
  if (state.sourceMode === 'url') {
    area.innerHTML = `
      <div class="form-group">
        <label class="form-label">URL</label>
        <input type="url" class="form-input" id="src-url" placeholder="https://..." />
      </div>
    `;
  } else {
    area.innerHTML = `
      <div class="form-group">
        <label class="form-label">File</label>
        <div id="file-selector-container">
          <div class="file-input-wrap" id="file-dropzone">
            <div class="file-input-label">
              <i class="ph-light ph-upload-simple" style="font-size:20px"></i>
              <span>Choose a file or drag it here</span>
            </div>
            <input type="file" id="src-file" />
          </div>
          <div id="selected-file-preview" style="display: none;"></div>
        </div>
      </div>
    `;

    const fileInput = $('#src-file');
    if (fileInput) {
      fileInput.addEventListener('change', (e) => {
        const file = e.target.files?.[0];
        if (file) {
          state.selectedFile = file;
          updateFilePreview();
        }
      });
    }

    updateFilePreview();
  }
}

function formatBytes(bytes, decimals = 2) {
  if (!+bytes) return '0 Bytes';
  const k = 1024;
  const dm = decimals < 0 ? 0 : decimals;
  const sizes = ['Bytes', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(dm))} ${sizes[i]}`;
}

function updateFilePreview() {
  const preview = $('#selected-file-preview');
  const dropzone = $('#file-dropzone');
  if (!preview || !dropzone) return;

  if (state.selectedFile) {
    const file = state.selectedFile;
    const name = file.name;
    const size = formatBytes(file.size);
    const ext = name.split('.').pop().toLowerCase();

    let iconClass = 'ph-file';
    if (ext === 'pdf') iconClass = 'ph-file-pdf';
    else if (['png', 'jpg', 'jpeg', 'webp', 'bmp', 'tiff', 'tif'].includes(ext)) iconClass = 'ph-image';
    else if (['txt', 'md', 'csv'].includes(ext)) iconClass = 'ph-file-text';
    else if (ext === 'pptx') iconClass = 'ph-file-ppt';

    preview.innerHTML = `
      <div class="selected-file-card">
        <div class="selected-file-icon">
          <i class="ph-light ${iconClass}"></i>
        </div>
        <div class="selected-file-info">
          <span class="selected-file-name" title="${esc(name)}">${esc(name)}</span>
          <span class="selected-file-size">${size}</span>
        </div>
        <button class="selected-file-remove" id="btn-remove-selected-file" type="button" title="Remove file">
          <i class="ph-light ph-x"></i>
        </button>
      </div>
    `;

    dropzone.style.display = 'none';
    preview.style.display = 'block';

    const removeBtn = $('#btn-remove-selected-file');
    if (removeBtn) {
      removeBtn.addEventListener('click', (e) => {
        e.preventDefault();
        state.selectedFile = null;
        const fileInput = $('#src-file');
        if (fileInput) fileInput.value = '';
        updateFilePreview();
      });
    }
  } else {
    dropzone.style.display = 'block';
    preview.style.display = 'none';
    preview.innerHTML = '';
  }
}

function showIngestionProgress(container, src) {
  if (state._sourceIngestTimer) {
    clearInterval(state._sourceIngestTimer);
  }

  const startTime = Date.now();
  
  container.innerHTML = `
    <div class="ingest-progress-card">
      <div class="spinner-editorial"></div>
      <div class="ingest-progress-header">
        <h3>Ingesting Reference Source</h3>
        <p>Registering source meta, parsing text, and extracting key knowledge concepts...</p>
      </div>
      <div class="ingest-progress-details">
        <div class="progress-step-item" style="color: var(--success);">
          <i class="ph-light ph-check-circle"></i>
          <span>Source Registration & Upload Completed</span>
        </div>
        <div class="progress-step-item" id="ingest-step-run">
          <div class="spinner-mini"></div>
          <span id="ingest-step-text">Processing and running OCR extraction...</span>
        </div>
      </div>
      <div class="ingest-timer">Time elapsed: <span id="ingest-duration">0s</span></div>
    </div>
  `;

  const timerInterval = setInterval(() => {
    const elapsed = Math.floor((Date.now() - startTime) / 1000);
    const timeSpan = $('#ingest-duration');
    if (timeSpan) {
      timeSpan.textContent = `${elapsed}s`;
    }
  }, 1000);

  state._sourceIngestTimer = setInterval(async () => {
    try {
      const { data, error } = await db
        .from('sources')
        .select('crawl_status, title')
        .eq('id', src.id)
        .limit(1);

      if (error) {
        console.error('Polling error:', error);
        return;
      }

      if (!data || data.length === 0) {
        return;
      }

      const sourceRecord = data[0];
      const status = sourceRecord.crawl_status;
      const title = sourceRecord.title || src.title;

      const stepText = $('#ingest-step-text');
      if (stepText) {
        if (status === 'processing') {
          stepText.textContent = 'Running parser, OCR & text normalization...';
        } else if (status === 'pending') {
          stepText.textContent = 'Queueing ingestion pipeline...';
        }
      }

      if (status === 'completed') {
        clearInterval(state._sourceIngestTimer);
        clearInterval(timerInterval);
        state._sourceIngestTimer = null;

        const { data: docData, error: docError } = await db
          .from('normalized_documents')
          .select('content')
          .eq('source_id', src.id)
          .limit(1);

        const extractedText = (docData && docData.length > 0) ? docData[0].content : 'No text content was found/extracted.';
        
        renderIngestSuccess(container, title, extractedText);
      } else if (status === 'failed') {
        clearInterval(state._sourceIngestTimer);
        clearInterval(timerInterval);
        state._sourceIngestTimer = null;

        renderIngestFailure(container, title);
      }
    } catch (pollErr) {
      console.error('Polling exception:', pollErr);
    }
  }, 1500);
}

function renderIngestSuccess(container, title, extractedText) {
  state.selectedFile = null;
  
  container.innerHTML = `
    <div class="ingest-success-card">
      <div class="ingest-success-header">
        <div class="success-icon-badge">
          <i class="ph-light ph-check-circle"></i>
        </div>
        <h3>Ingestion Completed</h3>
        <p class="text-muted">Successfully extracted content from source: <strong>${esc(title)}</strong></p>
      </div>

      <div class="extracted-text-section">
        <div class="extracted-text-header">
          <span>Extracted Plain Text (${extractedText.length} characters)</span>
          <button class="btn btn-secondary btn-copy-extracted" id="btn-copy-extracted" type="button">
            <i class="ph-light ph-copy"></i> Copy Text
          </button>
        </div>
        <div class="extracted-text-box" id="extracted-text-content">${esc(extractedText)}</div>
      </div>

      <div class="form-actions" style="justify-content: center; width: 100%;">
        <button class="btn btn-secondary" id="btn-add-another-src">Add Another Source</button>
        <button class="btn btn-primary" id="btn-view-all-srcs">View All Sources</button>
      </div>
    </div>
  `;

  const copyBtn = $('#btn-copy-extracted');
  if (copyBtn) {
    copyBtn.addEventListener('click', async () => {
      try {
        await navigator.clipboard.writeText(extractedText);
        toast('Extracted text copied to clipboard', 'success');
        copyBtn.innerHTML = '<i class="ph-light ph-check"></i> Copied!';
        setTimeout(() => {
          copyBtn.innerHTML = '<i class="ph-light ph-copy"></i> Copy Text';
        }, 2000);
      } catch (err) {
        toast('Failed to copy text', 'error');
      }
    });
  }

  $('#btn-add-another-src')?.addEventListener('click', () => {
    state.sourcesSubView = 'add';
    renderSources();
  });

  $('#btn-view-all-srcs')?.addEventListener('click', () => {
    state.sourcesSubView = 'list';
    renderSources();
  });
}

function renderIngestFailure(container, title) {
  container.innerHTML = `
    <div class="ingest-error-card">
      <div class="ingest-error-header">
        <div class="error-icon-badge">
          <i class="ph-light ph-warning-circle"></i>
        </div>
        <h3>Ingestion Failed</h3>
        <p class="text-muted">An error occurred during extraction/OCR processing for source: <strong>${esc(title)}</strong></p>
      </div>

      <div class="error-details-box">
        The pipeline failed to process this document. Please check that the file is not corrupted, is in a readable format (PDF, Image, text), or check the background worker logs.
      </div>

      <div class="form-actions" style="justify-content: center; width: 100%;">
        <button class="btn btn-secondary" id="btn-failed-back">Go Back</button>
      </div>
    </div>
  `;

  $('#btn-failed-back')?.addEventListener('click', () => {
    state.sourcesSubView = 'add';
    renderSources();
  });
}

function updateMultiSelectTrigger(trigger, ids) {
  if (ids.size === 0) {
    trigger.innerHTML = `<span class="text-muted text-sm">Click to select topics...</span>`;
    return;
  }
  trigger.innerHTML = [...ids].map(id => {
    const t = state.topics.find(x => x.id === id);
    return `<span class="multi-select-chip">${esc(t ? topicLabel(t) : id)}<button data-remove="${id}">&times;</button></span>`;
  }).join('');

  $$('.multi-select-chip button', trigger).forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      ids.delete(btn.dataset.remove);
      updateMultiSelectTrigger(trigger, ids);
      const opt = $(`.multi-select-option[data-id="${btn.dataset.remove}"]`);
      if (opt) opt.classList.remove('selected');
    });
  });
}

function renderSourceList(container) {
  container.innerHTML = `
    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Title</th>
            <th>Type</th>
            <th>Status</th>
            <th>Trust Score (Manual)</th>
            <th>Auto Trust (AI)</th>
            <th>URL</th>
          </tr>
        </thead>
        <tbody>
          ${state.sources.length === 0
            ? `<tr><td colspan="6" class="text-muted" style="text-align:center;padding:32px;">No sources found</td></tr>`
            : state.sources.map(s => `
              <tr>
                <td>${esc(s.title)}</td>
                <td>${typePill(s.source_type)}</td>
                <td>${statusPill(s.is_active === false ? 'retired' : 'active')}</td>
                <td>${s.trust_score != null ? s.trust_score + '/10' : '—'}</td>
                <td>${s.auto_trust_score != null ? s.auto_trust_score + '/10' : '—'}</td>
                <td>${s.url ? `<a href="${esc(s.url)}" target="_blank" rel="noopener">${esc(truncate(s.url, 50))}</a>` : '—'}</td>
              </tr>
            `).join('')}
        </tbody>
      </table>
    </div>
  `;
}

function truncate(str, n) {
  if (!str) return '';
  return str.length > n ? str.slice(0, n) + '...' : str;
}
