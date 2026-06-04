// ═══════════════════════════════════════════════════════════════
// utils.js
// ═══════════════════════════════════════════════════════════════

import { state, RISK_LABELS, getTopicRiskCategory } from './state.js';

export const $  = (sel, ctx = document) => ctx.querySelector(sel);
export const $$ = (sel, ctx = document) => [...ctx.querySelectorAll(sel)];

export function toast(msg, type = '') {
  const toastBox = $('#toast-container');
  if (!toastBox) return;
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  el.textContent = msg;
  toastBox.appendChild(el);
  setTimeout(() => el.remove(), 3200);
}

export function esc(str) {
  if (str == null) return '';
  const d = document.createElement('div');
  d.textContent = String(str);
  return d.innerHTML;
}

export function statusPill(status) {
  const map = {
    pending: 'dot-warning', processing: 'dot-accent', running: 'dot-accent',
    completed: 'dot-success', complete: 'dot-success',
    failed: 'dot-error', error: 'dot-error',
    active: 'dot-success', retired: 'dot-warning',
    approved: 'dot-success', rejected: 'dot-error',
    'needs_review': 'dot-warning',
    'conflict_detected': 'dot-error',
  };
  const cls = map[status] || 'dot-neutral';
  return `<span class="status-indicator ${cls}"><span class="status-dot"></span>${esc(status || 'unknown')}</span>`;
}

export function typePill(type) {
  return `<span class="pill pill-neutral">${esc(type || '—')}</span>`;
}

export function stagger(container) {
  if (!container) return;
  container.classList.remove('view-entering');
  void container.offsetWidth; // force reflow
  const children = container.children;
  for (let i = 0; i < children.length; i++) {
    children[i].style.setProperty('--stagger', i);
  }
  container.classList.add('view-entering');
  setTimeout(() => {
    container.classList.remove('view-entering');
  }, 500);
}

export function randomUUID() {
  if (crypto.randomUUID) return crypto.randomUUID();
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, c => {
    const r = Math.random() * 16 | 0;
    return (c === 'x' ? r : (r & 0x3 | 0x8)).toString(16);
  });
}

export function topicLabel(t) {
  return t.topic_name;
}

export function formatTs(ts) {
  if (!ts) return '—';
  const d = new Date(ts);
  return d.toLocaleString('en-GB', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' });
}

export function formatCost(tokens) {
  return '$' + ((tokens || 0) / 1000 * 0.002).toFixed(4);
}

export function humanizeFieldName(name) {
  return String(name || '')
    .replace(/_/g, ' ')
    .replace(/\b\w/g, ch => ch.toUpperCase());
}

export function humanizeFieldNameWithTopic(name, topic) {
  if (name && name.includes('.') && /^\d+\./.test(name)) {
    const parts = name.split('.', 2);
    const subIdx = parseInt(parts[0], 10);
    const fieldPart = parts[1];
    const subtopics = topic && topic.topic_name
      ? topic.topic_name.split(',').map(s => s.trim())
      : [];
    const subtopicName = subtopics[subIdx] || `Subtopic ${subIdx + 1}`;
    const humanField = fieldPart.replace(/_/g, ' ').replace(/\b\w/g, ch => ch.toUpperCase());
    return `${subtopicName} — ${humanField}`;
  }
  return humanizeFieldName(name);
}

export function sourceTitle(sourceId) {
  const source = state.sources.find(s => s.id === sourceId);
  return source ? source.title : sourceId;
}

export function formatKnowledgeValue(value) {
  if (value == null || value === '') return 'Not available';
  if (Array.isArray(value)) return value.map(formatKnowledgeValue).join('; ');
  if (typeof value === 'object') {
    if (value.name && value.description) return `${value.name}: ${value.description}`;
    if (value.command && value.description) return `${value.command}: ${value.description}`;
    return JSON.stringify(value);
  }
  return String(value);
}

export function renderMath(el) {
  if (!el) return;
  console.log("renderMath called on element:", el.id, "typeof renderMathInElement:", typeof window.renderMathInElement);
  if (window.renderMathInElement) {
    try {
      window.renderMathInElement(el, {
        delimiters: [
          {left: '$$', right: '$$', display: true},
          {left: '$', right: '$', display: false},
          {left: '\\(', right: '\\)', display: false},
          {left: '\\[', right: '\\]', display: true}
        ],
        throwOnError: false
      });
      console.log("renderMathInElement executed successfully!");
    } catch (e) {
      console.error("Error in renderMathInElement:", e.message, e.stack);
    }
  }
}

export function buildTopicOptions(selectedId, showRisk = false) {
  return `<option value="">Select a topic...</option>` +
    state.topics.map(t => {
      let label = t.topic_name;
      if (showRisk && t._riskCategory !== undefined) {
        const prefix = RISK_LABELS[t._riskCategory] || '';
        label = `${prefix} ${t.topic_name}`;
      }
      return `<option value="${t.id}" ${t.id === selectedId ? 'selected' : ''}>${esc(label)}</option>`;
    }).join('');
}

export function applyCustomSelects(container) {
  if (!container) return;
  $$('select.form-select', container).forEach(selectEl => {
    if (selectEl.nextElementSibling && selectEl.nextElementSibling.classList.contains('custom-select-wrap')) {
      selectEl.nextElementSibling.remove();
    }
    
    selectEl.style.display = 'none';
    
    const wrapper = document.createElement('div');
    wrapper.className = 'custom-select-wrap';
    
    const trigger = document.createElement('div');
    trigger.className = 'custom-select-trigger';
    
    const label = document.createElement('span');
    const selectedOpt = selectEl.options[selectEl.selectedIndex];
    label.textContent = selectedOpt ? selectedOpt.textContent : 'Select...';
    trigger.appendChild(label);
    
    const arrow = document.createElement('i');
    arrow.className = 'ph-light ph-caret-down';
    trigger.appendChild(arrow);
    wrapper.appendChild(trigger);
    
    const dropdown = document.createElement('div');
    dropdown.className = 'custom-select-dropdown';
    
    const toggleParents = (isOpen) => {
      const group = wrapper.closest('.form-group');
      const row = wrapper.closest('.form-row');
      const maxW = wrapper.closest('.max-w-form');
      if (group) group.classList.toggle('select-open', isOpen);
      if (row) row.classList.toggle('select-open', isOpen);
      if (maxW) maxW.classList.toggle('select-open', isOpen);
    };
    
    Array.from(selectEl.options).forEach(opt => {
      const item = document.createElement('div');
      item.className = 'custom-select-option';
      item.dataset.value = opt.value;
      item.textContent = opt.textContent;
      if (opt.selected) {
        item.classList.add('selected');
      }
      
      item.addEventListener('click', (e) => {
        e.stopPropagation();
        selectEl.value = opt.value;
        label.textContent = opt.textContent;
        $$('.custom-select-option', dropdown).forEach(o => o.classList.remove('selected'));
        item.classList.add('selected');
        
        dropdown.classList.remove('open');
        trigger.classList.remove('open');
        wrapper.classList.remove('open');
        toggleParents(false);
        
        selectEl.dispatchEvent(new Event('change'));
      });
      dropdown.appendChild(item);
    });
    
    wrapper.appendChild(dropdown);
    
    trigger.addEventListener('click', (e) => {
      e.stopPropagation();
      const willOpen = !dropdown.classList.contains('open');
      $$('.custom-select-dropdown.open').forEach(d => {
        if (d !== dropdown) {
          d.classList.remove('open');
          d.previousElementSibling.classList.remove('open');
          if (d.parentNode) {
            d.parentNode.classList.remove('open');
            const group = d.parentNode.closest('.form-group');
            const row = d.parentNode.closest('.form-row');
            const maxW = d.parentNode.closest('.max-w-form');
            if (group) group.classList.remove('select-open');
            if (row) row.classList.remove('select-open');
            if (maxW) maxW.classList.remove('select-open');
          }
        }
      });
      dropdown.classList.toggle('open', willOpen);
      trigger.classList.toggle('open', willOpen);
      wrapper.classList.toggle('open', willOpen);
      toggleParents(willOpen);
    });
    
    document.addEventListener('click', () => {
      dropdown.classList.remove('open');
      trigger.classList.remove('open');
      wrapper.classList.remove('open');
      toggleParents(false);
    });
    
    selectEl.parentNode.insertBefore(wrapper, selectEl.nextSibling);
  });
}

export function compareTopicNumbers(a, b) {
  const parse = (name) => {
    // Topic names are like "1.10 Some Title" or "Topic 1.10 Some Title"
    const m = String(name).match(/^(?:Topic\s+)?(\d+(?:\.\d+)*)/i);
    return m ? m[1].split('.').map(Number) : [];
  };
  const partsA = parse(a.topic_name);
  const partsB = parse(b.topic_name);
  for (let i = 0; i < Math.max(partsA.length, partsB.length); i++) {
    const numA = partsA[i] || 0;
    const numB = partsB[i] || 0;
    if (numA !== numB) return numA - numB;
  }
  return String(a.topic_name).localeCompare(String(b.topic_name));
}

// ── Markdown Utilities ─────────────────────────────────────────────

export function safeMarkdown(text) {
  if (!text) return '';
  const raw = window.marked ? window.marked.parse(String(text)) : esc(String(text));
  return window.DOMPurify ? window.DOMPurify.sanitize(raw) : raw;
}

export function safeMarkdownInline(text) {
  if (!text) return '';
  const raw = window.marked ? window.marked.parseInline(String(text)) : esc(String(text));
  return window.DOMPurify ? window.DOMPurify.sanitize(raw) : raw;
}

export function mapSupabaseError(error) {
  if (!error) return 'An unknown error occurred.';
  const code = error.code;
  const msg = error.message || String(error);
  const errorMap = {
    '23505': 'A record with this value already exists.',
    '42501': 'Access denied: You do not have permission for this action.',
    '23503': 'Database reference constraint violation.',
    'P0001': 'Database validation rule failed.',
  };
  if (code && errorMap[code]) return errorMap[code];
  if (msg.includes('JWT') || msg.includes('token') || msg.includes('unauthorized') || msg.includes('Unauthorized') || msg.includes('401') || msg.includes('403')) {
    return 'Session expired or invalid. Please sign in again.';
  }
  if (msg.includes('rate limit') || msg.includes('429')) {
    return 'Too many requests. Please try again later.';
  }
  if (msg.includes('row-level security') || msg.includes('RLS') || msg.includes('permission denied')) {
    return 'Access denied: Insufficient permissions to access this data.';
  }
  return 'An error occurred. Please try again.';
}
