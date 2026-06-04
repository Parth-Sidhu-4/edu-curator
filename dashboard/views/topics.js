// ═══════════════════════════════════════════════════════════════
// views/topics.js
// ═══════════════════════════════════════════════════════════════

import { state } from '../state.js';
import { fetchTopics, insertTopic, updateTopic, deleteTopic } from '../api.js';
import {
  $, $$, toast, esc, applyCustomSelects, buildTopicOptions,
  randomUUID, topicLabel
} from '../utils.js';

export async function renderTopics() {
  const mainContent = $('#main-content');
  if (!mainContent) return;

  await fetchTopics();

  mainContent.innerHTML = `
    <h1 class="page-title">Topics</h1>
    <p class="page-subtitle">Manage syllabus topics</p>

    <div class="segmented-control" id="topics-segments">
      <button class="segmented-btn ${state.topicsSubView === 'add' ? 'active' : ''}" data-sub="add">Add</button>
      <button class="segmented-btn ${state.topicsSubView === 'edit' ? 'active' : ''}" data-sub="edit">Edit</button>
      <button class="segmented-btn ${state.topicsSubView === 'remove' ? 'active' : ''}" data-sub="remove">Remove</button>
    </div>

    <div id="topics-sub-content"></div>
  `;

  $$('.segmented-btn', $('#topics-segments')).forEach(btn => {
    btn.addEventListener('click', () => {
      state.topicsSubView = btn.dataset.sub;
      renderTopics();
    });
  });

  const sub = $('#topics-sub-content');
  switch (state.topicsSubView) {
    case 'add':    renderTopicAdd(sub); break;
    case 'edit':   renderTopicEdit(sub); break;
    case 'remove': renderTopicRemove(sub); break;
  }
  applyCustomSelects(sub);
}

function renderTopicAdd(container) {
  container.innerHTML = `
    <div class="max-w-form">
      <div class="form-row">
        <div class="form-group">
          <label class="form-label">Serial Number</label>
          <input type="number" class="form-input" id="t-sn" min="1" placeholder="e.g. 1" style="display:none" />
        </div>
        <div class="form-group">
          <label class="form-label">Chapter</label>
          <input type="text" class="form-input" id="t-chapter" placeholder="e.g. Introduction" />
        </div>
      </div>
      <div class="form-group">
        <label class="form-label">Topic Name</label>
        <input type="text" class="form-input" id="t-name" placeholder="e.g. What is DevOps" />
      </div>
      <div class="form-row">
        <div class="form-group">
          <label class="form-label">Type</label>
          <select class="form-select" id="t-type">
            <option value="concept">Concept</option>
            <option value="command">Command</option>
            <option value="tool">Tool</option>
            <option value="architecture">Architecture</option>
            <option value="process">Process</option>
          </select>
        </div>
        <div class="form-group">
          <label class="form-label">Difficulty</label>
          <select class="form-select" id="t-diff">
            <option value="Beginner">Beginner</option>
            <option value="Intermediate">Intermediate</option>
            <option value="Advanced">Advanced</option>
          </select>
        </div>
      </div>
      <div class="form-group">
        <label class="form-label">Keywords (comma-separated)</label>
        <input type="text" class="form-input" id="t-keywords" placeholder="e.g. devops, ci, cd" />
      </div>
      <div class="form-actions">
        <button class="btn btn-primary" id="btn-add-topic">Add Topic</button>
      </div>
    </div>
  `;

  $('#btn-add-topic').addEventListener('click', async () => {
    const chapter = $('#t-chapter').value.trim();
    const name    = $('#t-name').value.trim();
    const type    = $('#t-type').value;
    const diff    = $('#t-diff').value;
    const kw      = $('#t-keywords').value.trim();

    if (!chapter || !name) {
      toast('Please fill required fields', 'error');
      return;
    }

    const keywords = kw ? kw.split(',').map(k => k.trim()).filter(Boolean) : [];

    const ok = await insertTopic({
      id: randomUUID(),
      chapter,
      topic_name: name,
      topic_type: type,
      difficulty_level: diff,
      keywords,
      status: 'pending',
    });

    if (ok) {
      ['#t-sn','#t-chapter','#t-name','#t-keywords'].forEach(s => $(s).value = '');
      await fetchTopics();
    }
  });
}

function renderTopicEdit(container) {
  const selId = state.selectedEditTopicId;
  const topic = state.topics.find(t => t.id === selId);

  container.innerHTML = `
    <div class="max-w-form">
      <div class="form-group">
        <label class="form-label">Select Topic to Edit</label>
        <select class="form-select" id="edit-topic-select">
          ${buildTopicOptions(selId)}
        </select>
      </div>
      <div id="edit-topic-fields"></div>
    </div>
  `;

  $('#edit-topic-select').addEventListener('change', (e) => {
    state.selectedEditTopicId = e.target.value || null;
    renderTopics();
  });

  if (!topic) return;
  const fields = $('#edit-topic-fields');
  fields.innerHTML = `
    <hr class="section-divider" />
    <div class="form-row">
      <div class="form-group">
        <label class="form-label">Serial Number</label>
        <input type="text" class="form-input" id="e-sn" value="" style="display:none" />
      </div>
      <div class="form-group">
        <label class="form-label">Chapter</label>
        <input type="text" class="form-input" id="e-chapter" value="${esc(topic.chapter || '')}" />
      </div>
    </div>
    <div class="form-group">
      <label class="form-label">Topic Name</label>
      <input type="text" class="form-input" id="e-name" value="${esc(topic.topic_name || '')}" />
    </div>
    <div class="form-row">
      <div class="form-group">
        <label class="form-label">Type</label>
        <select class="form-select" id="e-type">
          ${['concept','command','tool','architecture','process'].map(v => `<option value="${v}" ${topic.topic_type===v?'selected':''}>${v}</option>`).join('')}
        </select>
      </div>
      <div class="form-group">
        <label class="form-label">Difficulty</label>
        <select class="form-select" id="e-diff">
          ${['Beginner','Intermediate','Advanced'].map(v => `<option value="${v}" ${topic.difficulty_level===v?'selected':''}>${v}</option>`).join('')}
        </select>
      </div>
    </div>
    <div class="form-group">
      <label class="form-label">Keywords (comma-separated)</label>
      <input type="text" class="form-input" id="e-keywords" value="${esc((topic.keywords || []).join(', '))}" />
    </div>
    <div class="form-actions">
      <button class="btn btn-primary" id="btn-save-edit">Save Changes</button>
    </div>
  `;
  applyCustomSelects(fields);

  $('#btn-save-edit').addEventListener('click', async () => {
    const chapter = $('#e-chapter').value.trim();
    const name    = $('#e-name').value.trim();
    const type    = $('#e-type').value;
    const diff    = $('#e-diff').value;
    const kw      = $('#e-keywords').value.trim();
    const keywords = kw ? kw.split(',').map(k => k.trim()).filter(Boolean) : [];

    const ok = await updateTopic(topic.id, {
      chapter, topic_name: name, topic_type: type, difficulty_level: diff, keywords,
    });
    if (ok) { await fetchTopics(); renderTopics(); }
  });
}

function renderTopicRemove(container) {
  const selId = state.selectedRemoveTopicId;
  const topic = state.topics.find(t => t.id === selId);

  container.innerHTML = `
    <div class="max-w-form">
      <div class="form-group">
        <label class="form-label">Select Topic to Remove</label>
        <select class="form-select" id="remove-topic-select">
          ${buildTopicOptions(selId)}
        </select>
      </div>
      <div id="remove-confirm-area"></div>
    </div>
  `;

  $('#remove-topic-select').addEventListener('change', (e) => {
    state.selectedRemoveTopicId = e.target.value || null;
    renderTopics();
  });

  if (!topic) return;
  const area = $('#remove-confirm-area');
  area.innerHTML = `
    <div class="confirm-box">
      <p>Remove <strong>${esc(topicLabel(topic))}</strong>? This action cannot be undone.</p>
      <div class="form-actions">
        <button class="btn btn-danger" id="btn-confirm-remove">Remove Topic</button>
        <button class="btn btn-secondary" id="btn-cancel-remove">Cancel</button>
      </div>
    </div>
  `;

  $('#btn-confirm-remove').addEventListener('click', async () => {
    const ok = await deleteTopic(topic.id);
    if (ok) {
      state.selectedRemoveTopicId = null;
      await fetchTopics();
      renderTopics();
    }
  });
  $('#btn-cancel-remove').addEventListener('click', () => {
    state.selectedRemoveTopicId = null;
    renderTopics();
  });
}
