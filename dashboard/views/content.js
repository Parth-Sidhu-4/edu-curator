// ═══════════════════════════════════════════════════════════════
// views/content.js
// ═══════════════════════════════════════════════════════════════

import { state, db, getTopicRiskCategory, currentUser } from '../state.js';
import {
  fetchTopics, fetchContent, fetchJobs, insertJob, resetJob,
  submitReviewAction, fetchLatestKnowledge
} from '../api.js';
import {
  $, $$, toast, esc, statusPill, typePill, formatKnowledgeValue,
  sourceTitle, humanizeFieldName, humanizeFieldNameWithTopic, safeMarkdown, safeMarkdownInline,
  applyCustomSelects, renderMath, buildTopicOptions, mapSupabaseError,
  compareTopicNumbers
} from '../utils.js';

function renderKnowledgeReviewSignals(knowledgeRecord, topic) {
  if (!knowledgeRecord || !knowledgeRecord.knowledge) return '';

  const knowledge = typeof knowledgeRecord.knowledge === 'string'
    ? JSON.parse(knowledgeRecord.knowledge)
    : knowledgeRecord.knowledge;

  const signals = Object.entries(knowledge)
    .filter(([, value]) => value && typeof value === 'object' && !Array.isArray(value) && 'canonical_value' in value)
    .map(([fieldName, field]) => {
      const confidence = field.confidence != null ? Number(field.confidence) : null;
      let status = field.status || 'resolved';
      if (status === 'resolved' && confidence != null && confidence < 75) {
        status = 'needs_review';
      }
      return { fieldName, field, confidence, status };
    });

  if (!signals.length) return '';

  const riskRank = {
    conflict_detected: 0,
    needs_review: 1,
    missing: 2,
    resolved: 3,
  };

  signals.sort((a, b) => {
    const ar = riskRank[a.status] ?? 4;
    const br = riskRank[b.status] ?? 4;
    if (ar !== br) return ar - br;
    const ac = a.confidence == null ? 101 : a.confidence;
    const bc = b.confidence == null ? 101 : b.confidence;
    return ac - bc;
  });

  const conflictCount = signals.filter(s => s.status === 'conflict_detected').length;
  const reviewCount = signals.filter(s => s.status === 'needs_review').length;
  const missingCount = signals.filter(s => s.status === 'missing').length;
  const resolvedCount = signals.filter(s => s.status === 'resolved').length;
  const topicConfidence = knowledgeRecord.confidence != null ? `${Number(knowledgeRecord.confidence).toFixed(1)}%` : 'N/A';

  const riskCategory = topic ? topic._riskCategory : getTopicRiskCategory(null, knowledgeRecord);
  let overallRiskBadgeHtml = '';
  if (riskCategory !== undefined && riskCategory !== null) {
    const config = {
      1: { cls: 'pill-error', text: '⚠️ Conflict' },
      2: { cls: 'pill-warning', text: '🔍 Needs Review' },
      3: { cls: 'pill-accent', text: '📄 Single Source' },
      4: { cls: 'pill-accent', text: '💡 Med Conf' },
      5: { cls: 'pill-success', text: '✅ High Conf' },
      6: { cls: 'pill-neutral', text: 'No Resolved Knowledge' }
    };
    const cfg = config[riskCategory];
    if (cfg) {
      overallRiskBadgeHtml = `<span class="pill ${cfg.cls}" style="font-size:0.7rem;padding:2px 8px;margin-left:6px;font-weight:600;vertical-align:middle;">${esc(cfg.text)}</span>`;
    }
  }

  const signalRows = signals.map(({ fieldName, field, confidence, status }) => {
    const alternatives = Array.isArray(field.alternative_values) ? field.alternative_values : [];
    const sources = Array.isArray(field.sources) ? field.sources : [];
    const canonical = formatKnowledgeValue(field.canonical_value);
    const confidenceLabel = confidence == null ? 'N/A' : `${confidence.toFixed(1)}%`;
    const sourceLabels = sources.length
      ? sources.map(sourceId => esc(sourceTitle(sourceId))).join(', ')
      : 'No source recorded';

    return `
      <div class="review-signal-item review-signal-${esc(status)}">
        <div class="review-signal-head">
          <div>
            <h3>${esc(humanizeFieldNameWithTopic(fieldName, topic))}</h3>
            <p>${esc(field.resolution_reason || 'No resolution reason recorded')}</p>
          </div>
          <div class="review-signal-badges">
            ${statusPill(status)}
            <span class="pill pill-accent">${esc(confidenceLabel)}</span>
          </div>
        </div>
        <div class="review-signal-body">
          <div>
            <span class="review-signal-label">Canonical</span>
            <p>${esc(canonical)}</p>
          </div>
          <div>
            <span class="review-signal-label">Sources</span>
            <p>${sourceLabels}</p>
          </div>
          ${alternatives.length ? `
            <div class="review-signal-alternatives">
              <span class="review-signal-label">Alternatives</span>
              <ul>
                ${alternatives.map(alt => `
                  <li>
                    ${esc(formatKnowledgeValue(alt.value))}
                    ${alt.source ? `<span>${esc(sourceTitle(alt.source))}</span>` : ''}
                  </li>
                `).join('')}
              </ul>
            </div>
          ` : ''}
        </div>
      </div>
    `;
  }).join('');

  return `
    <hr class="section-divider" />
    <div class="collapsible-section mt-24" id="signals-collapsible">
      <button class="collapsible-header" id="signals-toggle" aria-expanded="false" aria-controls="signals-body">
        <span class="collapsible-title">
          <i class="ph-light ph-shield-warning"></i>
          Knowledge Review Signals
          <span class="pill pill-neutral" style="font-size:0.7rem;padding:2px 8px;margin-left:6px;">${signals.length}</span>
          ${overallRiskBadgeHtml}
        </span>
        <i class="ph-light ph-caret-down collapsible-chevron"></i>
      </button>
      <div class="collapsible-body" id="signals-body" hidden>
        <section class="knowledge-review-panel" style="margin-top: 16px; padding-top: 0;">
          <div class="flex-between align-center">
            <h2 class="section-heading" style="font-size: 1.1rem; margin-bottom: 0;">Signals Overview</h2>
            <div style="display: flex; gap: 8px; align-items: center;">
              ${overallRiskBadgeHtml}
              <span class="pill pill-neutral">Topic confidence ${esc(topicConfidence)}</span>
            </div>
          </div>
          <div class="review-signal-summary">
            <span>${statusPill('conflict_detected')} <strong>${conflictCount}</strong></span>
            <span>${statusPill('needs_review')} <strong>${reviewCount}</strong></span>
            <span>${statusPill('missing')} <strong>${missingCount}</strong></span>
            <span>${statusPill('resolved')} <strong>${resolvedCount}</strong></span>
          </div>
          <div class="review-signal-list">
            ${signalRows}
          </div>
        </section>
      </div>
    </div>
  `;
}

export async function renderContent() {
  const mainContent = $('#main-content');
  if (!mainContent) return;

  const [topics, contentRes, knowledgeRes] = await Promise.all([
    fetchTopics(),
    fetchContent(),
    db.from('topic_knowledge').select('topic_id, confidence, sources_used, knowledge')
  ]);

  const knowledgeMap = {};
  if (knowledgeRes.data) {
    knowledgeRes.data.forEach(k => {
      knowledgeMap[k.topic_id] = k;
    });
  }

  state.topics.forEach(t => {
    t._riskCategory = getTopicRiskCategory(t, knowledgeMap[t.id]);
    t._confidence = knowledgeMap[t.id] ? (knowledgeMap[t.id].confidence ?? 0) : 0;
  });

  state.topics.sort(compareTopicNumbers);

  const selectedId = state.selectedTopicId;
  const topic = state.topics.find(t => t.id === selectedId);
  const content = state.content.find(c => c.topic_id === selectedId);

  let jobHtml = '';
  let contentHtml = '';

  if (selectedId) {
    const jobs = await fetchJobs(selectedId);
    let latestJob = jobs.find(j => j.status === 'running' || j.status === 'processing');
    if (!latestJob) {
      latestJob = jobs.find(j => j.status === 'pending');
    }
    if (!latestJob) {
      latestJob = jobs[0];
    }
    const hasActiveJob = latestJob && (latestJob.status === 'processing' || latestJob.status === 'pending' || latestJob.status === 'running');
    jobHtml = `
      <div class="mt-24 flex-between">
        <button class="btn btn-primary" id="btn-generate" ${hasActiveJob ? 'disabled' : ''}>
          ${hasActiveJob ? 'Generating Content...' : (content ? 'Re-generate Content' : 'Generate Content')}
        </button>
      </div>
    `;

    const showJobBox = latestJob && (latestJob.status === 'processing' || latestJob.status === 'pending' || latestJob.status === 'running' || latestJob.status === 'failed');
    if (showJobBox) {
      const isFailed = latestJob.status === 'failed';
      const errorMsgHtml = isFailed && latestJob.error_message ? `<p class="text-sm text-error mt-4" style="color: var(--error);">Error: ${esc(latestJob.error_message)}</p>` : '';
      jobHtml += `
        <div class="mt-16">
          <div class="flex-between align-center">
            <p class="text-sm text-muted">Job Status: <span id="job-status-container">${statusPill(latestJob.status)}</span></p>
            <div style="display: flex; gap: 8px;">
              <button class="btn btn-secondary btn-sm" id="btn-copy-job-log">Copy Logs</button>
              ${isFailed ? '' : `<button class="btn btn-danger btn-sm" id="btn-force-reset" data-job-id="${latestJob.id}">Force Reset Stuck Job</button>`}
            </div>
          </div>
          ${errorMsgHtml}
          <pre class="code-block mt-8" id="job-log-box" style="min-height: 120px; max-height: 350px; overflow-y: auto; white-space: pre-wrap; font-family: monospace;">${esc(latestJob.logs || `[System] Job is ${latestJob.status}. Waiting for worker to start streaming logs...`)}</pre>
        </div>
      `;

      if (latestJob.status !== 'failed') {
        if (!state._jobPollTimer) {
          state._jobPollTimer = setInterval(async () => {
            if (state.view === 'content' && state.selectedTopicId === selectedId) {
              const jobs = await fetchJobs(selectedId);
              let activeJob = jobs.find(j => j.status === 'running' || j.status === 'processing');
              if (!activeJob) {
                activeJob = jobs.find(j => j.status === 'pending');
              }
              if (!activeJob) {
                activeJob = jobs[0];
              }

              if (!activeJob || (activeJob.status !== 'running' && activeJob.status !== 'processing' && activeJob.status !== 'pending')) {
                clearInterval(state._jobPollTimer);
                state._jobPollTimer = null;
                renderContent();
                return;
              }

              const logBox = document.getElementById('job-log-box');
              const statusContainer = document.getElementById('job-status-container');
              if (logBox) {
                logBox.textContent = activeJob.logs || `[System] Job is ${activeJob.status}. Waiting for worker to start streaming logs...`;
                logBox.scrollTop = logBox.scrollHeight;
              }
              if (statusContainer) {
                statusContainer.innerHTML = statusPill(activeJob.status);
              }
            } else {
              clearInterval(state._jobPollTimer);
              state._jobPollTimer = null;
            }
          }, 2000);
        }
      }
    } else {
      if (state._jobPollTimer) {
        clearInterval(state._jobPollTimer);
        state._jobPollTimer = null;
      }
    }

    const knowledgeRecord = await fetchLatestKnowledge(selectedId);

    const { data: overridesData } = await db
      .from('knowledge_overrides')
      .select('*')
      .eq('topic_id', selectedId)
      .eq('is_active', true);
    const overrides = overridesData || [];

    let factsHtml = '';
    const { data: factsData } = await db.from('fact_extractions').select('*').eq('topic_id', selectedId);
    if (factsData && factsData.length > 0) {
      const factRows = factsData.map(f => {
        let valStr = '';
        if (f.field_value != null) {
          if (typeof f.field_value === 'object') {
            if (Array.isArray(f.field_value)) {
              valStr = f.field_value.join(', ');
            } else if (f.field_value.value !== undefined) {
              valStr = f.field_value.value;
            } else {
              valStr = JSON.stringify(f.field_value);
            }
          } else {
            valStr = String(f.field_value);
          }
        }
        const conf = f.extraction_confidence != null ? f.extraction_confidence.toFixed(2) : '—';
        return `
          <tr>
            <td><strong>${esc(f.field_name)}</strong></td>
            <td>${esc(valStr)}</td>
            <td><span class="pill pill-accent">${esc(conf)}</span></td>
            <td><span class="text-sm text-muted">${esc(f.source_id || '—')}</span></td>
          </tr>
        `;
      }).join('');

      factsHtml = `
        <div class="collapsible-section mt-24" id="facts-collapsible">
          <button class="collapsible-header" id="facts-toggle" aria-expanded="false" aria-controls="facts-body">
            <span class="collapsible-title">
              <i class="ph-light ph-list-bullets"></i>
              Extracted Facts
              <span class="pill pill-neutral" style="font-size:0.7rem;padding:2px 8px;margin-left:6px;">${factsData.length}</span>
            </span>
            <i class="ph-light ph-caret-down collapsible-chevron"></i>
          </button>
          <div class="collapsible-body" id="facts-body" hidden>
            <div class="table-wrap mb-8">
              <table>
                <thead>
                  <tr>
                    <th>Field Name</th>
                    <th>Value</th>
                    <th>Confidence</th>
                    <th>Source ID</th>
                  </tr>
                </thead>
                <tbody>${factRows}</tbody>
              </table>
            </div>
          </div>
        </div>
      `;
    }

    if (content) {
      const cur = typeof content.content_json === 'string' ? JSON.parse(content.content_json) : (content.content_json || {});
      contentHtml = factsHtml + renderKnowledgeReviewSignals(knowledgeRecord, topic) + renderCurriculum(content, cur, topic, overrides, knowledgeRecord);
    } else {
      contentHtml = factsHtml + renderKnowledgeReviewSignals(knowledgeRecord, topic) + `
        <div class="empty-state mt-24">
          <p>No content generated for this topic yet.</p>
        </div>
      `;
    }
  }

  mainContent.innerHTML = `
    <h1 class="page-title">Content Viewer</h1>
    <p class="page-subtitle">Review, edit, and approve generated curriculum pages</p>

    <div class="max-w-form">
      <div class="form-group">
        <label class="form-label">Select Topic</label>
        <select class="form-select" id="content-topic-select">
          ${buildTopicOptions(selectedId)}
        </select>
      </div>
    </div>
    ${selectedId ? '' : `
      <div class="empty-state mt-24">
        <p>Select a topic from the dropdown to view content.</p>
      </div>
    `}
    ${jobHtml}
    ${contentHtml}
  `;

  const sel = $('#content-topic-select');
  if (sel) {
    sel.addEventListener('change', () => {
      state.selectedTopicId = sel.value || null;
      renderContent();
    });
  }

  if (selectedId) {
    const genBtn = $('#btn-generate');
    if (genBtn) {
      genBtn.addEventListener('click', async () => {
        if (!state.selectedTopicId) return;
        genBtn.disabled = true;
        genBtn.textContent = 'Queuing...';
        await insertJob(state.selectedTopicId);
        renderContent();
      });
    }

    const resetBtn = $('#btn-force-reset');
    if (resetBtn) {
      resetBtn.addEventListener('click', async () => {
        const jobId = resetBtn.dataset.jobId;
        resetBtn.disabled = true;
        resetBtn.textContent = 'Resetting...';
        try {
          await resetJob('curation_jobs', jobId);
          toast('Job reset successfully', 'success');
        } catch (error) {
          toast(`Reset failed: ${mapSupabaseError(error)}`, 'error');
        }
        renderContent();
      });
    }

    const copyLogBtn = $('#btn-copy-job-log');
    if (copyLogBtn) {
      copyLogBtn.addEventListener('click', () => {
        const logBox = $('#job-log-box');
        if (logBox) {
          navigator.clipboard.writeText(logBox.textContent);
          toast('Logs copied to clipboard', 'success');
        }
      });
    }

    const factsToggle = $('#facts-toggle');
    if (factsToggle) {
      factsToggle.addEventListener('click', () => {
        const body = $('#facts-body');
        const isOpen = factsToggle.getAttribute('aria-expanded') === 'true';
        factsToggle.setAttribute('aria-expanded', String(!isOpen));
        if (isOpen) {
          body.hidden = true;
        } else {
          body.hidden = false;
        }
      });
    }

    const signalsToggle = $('#signals-toggle');
    if (signalsToggle) {
      signalsToggle.addEventListener('click', () => {
        const body = $('#signals-body');
        const isOpen = signalsToggle.getAttribute('aria-expanded') === 'true';
        signalsToggle.setAttribute('aria-expanded', String(!isOpen));
        if (isOpen) {
          body.hidden = true;
        } else {
          body.hidden = false;
        }
      });
    }

    $$('.subtopic-toggle').forEach(btn => {
      btn.addEventListener('click', () => {
        const bodyId = btn.getAttribute('aria-controls');
        const body = $(`#${bodyId}`);
        if (!body) return;
        const isOpen = btn.getAttribute('aria-expanded') === 'true';
        btn.setAttribute('aria-expanded', String(!isOpen));
        body.hidden = isOpen;
      });
    });
  }

  applyCustomSelects(mainContent);
  renderMath(mainContent);
}

function renderCurriculum(content, cur, topic, overrides = [], knowledgeRecord = null) {
  // Deep clone cur to prevent mutating original state directly
  cur = JSON.parse(JSON.stringify(cur || {}));

  // Apply active overrides to cur so that the viewer and markdown preview reflect saved changes immediately
  if (overrides && overrides.length > 0) {
    const subtopicsOverride = overrides.find(o => o.field_name === 'subtopics');
    if (subtopicsOverride && subtopicsOverride.corrected_value) {
      const parsedSub = typeof subtopicsOverride.corrected_value === 'string'
        ? JSON.parse(subtopicsOverride.corrected_value)
        : subtopicsOverride.corrected_value;
      cur.subtopics = parsedSub;
    }
    overrides.forEach(o => {
      if (o.field_name !== 'subtopics' && o.corrected_value !== undefined) {
        let parsedVal = o.corrected_value;
        if (typeof parsedVal === 'string' && (parsedVal.startsWith('[') || parsedVal.startsWith('{'))) {
          try {
            parsedVal = JSON.parse(parsedVal);
          } catch (e) {}
        }
        cur[o.field_name] = parsedVal;
      }
    });
  }

  const confidence = content.confidence_score != null ? content.confidence_score : '—';
  const consistency = content.consistency_check_status != null ? (content.consistency_check_status ? 'Passed' : 'Failed') : '—';
  const reviewStatus = content.review_status || 'needs_review';

  const hasSubtopics = cur && Array.isArray(cur.subtopics);
  let sections = [
    { key: 'summary',             title: 'Summary',             rows: 3 },
    { key: 'definition',          title: 'Definition',          rows: 3 },
    { key: 'purpose',             title: 'Purpose',             rows: 3 },
    { key: 'key_properties',      title: 'Key Properties',      rows: 4, array: true },
    { key: 'benefits',            title: 'Benefits',            rows: 4, array: true },
    { key: 'limitations',         title: 'Limitations',         rows: 4, array: true },
    { key: 'common_misconceptions', title: 'Common Misconceptions', rows: 4, array: true },
    { key: 'related_topics',      title: 'Related Topics',      rows: 3, array: true },
  ];

  if (hasSubtopics && cur.subtopics.length > 0) {
    const subkeys = Object.keys(cur.subtopics[0]).filter(k => k !== 'subtopic_name');
    const isCustom = subkeys.some(k => !['summary', 'definition', 'purpose', 'key_properties', 'benefits', 'limitations', 'common_misconceptions', 'related_topics'].includes(k));
    if (isCustom) {
      sections = subkeys.map(k => {
        const title = k.split('_').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');
        const isArray = Array.isArray(cur.subtopics[0][k]);
        return { key: k, title: title, rows: isArray ? 4 : 3, array: isArray };
      });
    }
  } else if (cur) {
    const topkeys = Object.keys(cur).filter(k => !['topic_name', 'subtopics', 'faq'].includes(k));
    const isCustom = topkeys.some(k => !['summary', 'definition', 'purpose', 'key_properties', 'benefits', 'limitations', 'common_misconceptions', 'related_topics'].includes(k));
    if (isCustom) {
      sections = topkeys.map(k => {
        const title = k.split('_').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');
        const isArray = Array.isArray(cur[k]);
        return { key: k, title: title, rows: isArray ? 4 : 3, array: isArray };
      });
    }
  }

  let triggers = {};
  if (knowledgeRecord && knowledgeRecord.knowledge) {
    const knowledge = typeof knowledgeRecord.knowledge === 'string'
      ? JSON.parse(knowledgeRecord.knowledge)
      : knowledgeRecord.knowledge;
    if (knowledge && knowledge._review_triggers) {
      triggers = knowledge._review_triggers;
    }
  }

  let triggerBadgesHtml = '';
  if (triggers.is_single_source) {
    triggerBadgesHtml += `<span class="pill pill-warning" style="font-size:0.75rem;font-weight:600;padding:2px 8px;">⚠️ Single Source</span>`;
  }
  if (triggers.is_contradictory) {
    const details = Array.isArray(triggers.contradictory_details) ? triggers.contradictory_details.join('; ') : '';
    const titleAttr = details ? ` title="${esc(details)}"` : '';
    triggerBadgesHtml += `
      <div style="display:flex; flex-direction:column; gap:2px;">
        <span class="pill pill-error" style="font-size:0.75rem;font-weight:600;padding:2px 8px;width:fit-content;"${titleAttr}>⚠️ Contradiction</span>
        ${details ? `<span style="font-size:0.7rem; color:var(--error); margin-left:4px; font-style:italic;">${esc(details)}</span>` : ''}
      </div>
    `;
  }
  if (triggers.critical_field_missing) {
    const details = Array.isArray(triggers.missing_details) ? triggers.missing_details.join('; ') : '';
    const titleAttr = details ? ` title="${esc(details)}"` : '';
    triggerBadgesHtml += `
      <div style="display:flex; flex-direction:column; gap:2px;">
        <span class="pill pill-error" style="font-size:0.75rem;font-weight:600;padding:2px 8px;width:fit-content;"${titleAttr}>⚠️ Critical Field Missing</span>
        ${details ? `<span style="font-size:0.7rem; color:var(--error); margin-left:4px; font-style:italic;">${esc(details)}</span>` : ''}
      </div>
    `;
  }

  let html = `
    <hr class="section-divider" />
    <div class="content-meta" style="display:flex; flex-wrap:wrap; align-items:center; gap:24px;">
      <span>Confidence: <strong>${esc(String(confidence))}</strong></span>
      <span>Consistency: <strong>${esc(consistency)}</strong></span>
      ${triggerBadgesHtml ? `<div style="display:flex; gap:16px; align-items:center; flex-wrap:wrap;">${triggerBadgesHtml}</div>` : ''}
    </div>
  `;

  // hasSubtopics defined above

  if (hasSubtopics) {
    cur.subtopics.forEach((sub, subIdx) => {
      const subtopicName = sub.subtopic_name || '';
      const baseNumMatch = topic && topic.topic_name ? topic.topic_name.match(/^\s*(\d+(?:\.\d+)*)/) : null;
      const baseNum = baseNumMatch ? baseNumMatch[1] : '';
      const subtopicNumber = baseNum ? `${baseNum}.${subIdx + 1}` : `${subIdx + 1}`;
      
      const cleanSubName = subtopicName.replace(/^\s*\d+(?:\.\d+)*\s*[-.:]?\s*/, '').trim();
      const formattedSubHeading = `${subtopicNumber} ${cleanSubName}`;

      html += `
        <div class="collapsible-section mt-24 mb-24" id="subtopic-${subIdx}-collapsible">
          <button class="collapsible-header subtopic-toggle" id="subtopic-${subIdx}-toggle" aria-expanded="false" aria-controls="subtopic-${subIdx}-body">
            <span class="collapsible-title" style="font-family: var(--font-sans); font-size: 0.9rem; font-weight: 700; text-transform: none; letter-spacing: normal;">
              <i class="ph-light ph-book-open" style="vertical-align:middle; margin-right:8px; font-style: normal; font-size: 1.15rem; color: var(--accent);"></i>
              ${esc(formattedSubHeading)}
            </span>
            <i class="ph-light ph-caret-down collapsible-chevron"></i>
          </button>
          <div class="collapsible-body" id="subtopic-${subIdx}-body" hidden style="padding: 16px 18px 18px 18px; border-top: 1px solid var(--border);">
      `;

      let secIndex = 1;
      sections.forEach(s => {
        const val = sub[s.key];
        if (val == null) return;
        if (Array.isArray(val) && val.length === 0) return;
        if (typeof val === 'string' && val.trim() === '') return;

        const extraClass = s.key === 'summary' ? 'curriculum-summary' : '';
        html += `<div class="curriculum-section ${extraClass}" style="margin-bottom: 20px;">`;
        html += `<h3 style="font-size:1.05rem; font-weight:600;"><span class="section-symbol">§${subtopicNumber}.${secIndex}</span> ${s.title}</h3>`;
        secIndex++;
        if (s.array && Array.isArray(val)) {
          html += `<ul>${val.map(v => `<li>${safeMarkdownInline(v)}</li>`).join('')}</ul>`;
        } else if (typeof val === 'object' && !Array.isArray(val)) {
          html += `<p>${esc(JSON.stringify(val))}</p>`;
        } else {
          html += `<div class="markdown-body">${safeMarkdown(val)}</div>`;
        }
        html += `</div>`;
      });
      html += `
          </div>
        </div>
      `;
    });
  } else {
    let sectionIndex = 1;
    for (const s of sections) {
      const val = cur[s.key];
      if (val == null) continue;
      if (Array.isArray(val) && val.length === 0) continue;
      if (typeof val === 'string' && val.trim() === '') continue;

      const extraClass = s.key === 'summary' ? 'curriculum-summary' : '';
      html += `<div class="curriculum-section ${extraClass}">`;
      html += `<h3><span class="section-symbol">§${sectionIndex}</span> ${s.title}</h3>`;
      sectionIndex++;
      if (s.array && Array.isArray(val)) {
        html += `<ul>${val.map(v => `<li>${safeMarkdownInline(v)}</li>`).join('')}</ul>`;
      } else if (typeof val === 'object' && !Array.isArray(val)) {
        html += `<p>${esc(JSON.stringify(val))}</p>`;
      } else {
        html += `<div class="markdown-body">${safeMarkdown(val)}</div>`;
      }
      html += `</div>`;
    }
  }

  if (content.sources_used && content.sources_used.length) {
    const usedSources = state.sources.length
      ? state.sources.filter(s => content.sources_used.includes(s.id))
      : [];
    html += `
      <hr class="section-divider" />
      <div class="curriculum-section">
        <h3><span class="section-symbol">§</span> References</h3>
        ${usedSources.length
          ? `<ul>${usedSources.map(s => `<li><a href="${esc(s.url || '#')}" target="_blank" rel="noopener">${esc(s.title)}</a></li>`).join('')}</ul>`
          : `<p class="text-muted">Source IDs: ${esc(content.sources_used.join(', '))}</p>`
        }
      </div>
    `;
  }

  if (cur.faq && Array.isArray(cur.faq) && cur.faq.length > 0) {
    let faqItemsHtml = cur.faq.map((item, faqIdx) => {
      const q = item.question || '';
      const a = item.answer || '';
      if (!q && !a) return '';
      return `
        <div class="faq-item" id="faq-item-${faqIdx}">
          <button class="faq-question" data-target="faq-answer-${faqIdx}">
            <span>${esc(q)}</span>
            <i class="ph-light ph-caret-down"></i>
          </button>
          <div class="faq-answer" id="faq-answer-${faqIdx}">
            <div class="markdown-body">${safeMarkdown(a)}</div>
          </div>
        </div>
      `;
    }).join('');
    
    html += `
      <hr class="section-divider" />
      <div class="faq-section">
        <h2 class="faq-heading"><i class="ph-light ph-question" style="vertical-align:middle; margin-right:8px; color: var(--accent);"></i>Frequently Asked Questions</h2>
        <div class="faq-list">
          ${faqItemsHtml}
        </div>
      </div>
    `;
  }

  let md = `# ${topic ? topic.topic_name : 'Curriculum'}\n\n`;
  if (hasSubtopics) {
    cur.subtopics.forEach((sub, subIdx) => {
      const subtopicName = sub.subtopic_name || '';
      const baseNumMatch = topic && topic.topic_name ? topic.topic_name.match(/^\s*(\d+(?:\.\d+)*)/) : null;
      const baseNum = baseNumMatch ? baseNumMatch[1] : '';
      const subtopicNumber = baseNum ? `${baseNum}.${subIdx + 1}` : `${subIdx + 1}`;
      
      const cleanSubName = subtopicName.replace(/^\s*\d+(?:\.\d+)*\s*[-.:]?\s*/, '').trim();
      const formattedSubHeading = `${subtopicNumber} ${cleanSubName}`;

      md += `## ${formattedSubHeading}\n\n`;
      let secIndex = 1;
      sections.forEach(s => {
        const val = sub[s.key];
        if (val == null) return;
        md += `### ${subtopicNumber}.${secIndex} ${s.title}\n`;
        secIndex++;
        if (s.array && Array.isArray(val)) {
          md += val.map(v => `- ${v}`).join('\n') + '\n\n';
        } else {
          md += `${val}\n\n`;
        }
      });
    });
  } else {
    for (const s of sections) {
      const val = cur[s.key];
      if (val == null) continue;
      md += `## ${s.title}\n`;
      if (s.array && Array.isArray(val)) {
        md += val.map(v => `- ${v}`).join('\n') + '\n\n';
      } else {
        md += `${val}\n\n`;
      }
    }
  }

  if (cur.faq && Array.isArray(cur.faq) && cur.faq.length > 0) {
    md += `## Frequently Asked Questions\n\n`;
    cur.faq.forEach(item => {
      const q = item.question || '';
      const a = item.answer || '';
      if (q || a) {
        md += `### ${q}\n${a}\n\n`;
      }
    });
  }

  html += `
    <hr class="section-divider" />
    <div class="curriculum-section">
      <div class="flex-between">
        <h3><span class="section-symbol">§</span> Full Textbook Page</h3>
        <button class="btn btn-secondary btn-sm" id="btn-copy-md">Copy Markdown</button>
      </div>
      <pre class="code-block mt-8" id="markdown-preview" style="white-space: pre-wrap; font-family: monospace;">${esc(md)}</pre>
    </div>
  `;

  let reviewFormHtml = `
    <hr class="section-divider" />
    <h2 class="section-heading">Human Review & Edit Curation</h2>
    <p class="mb-16">Status: ${statusPill(reviewStatus)}</p>
    <div class="max-w-form" id="review-form-area">
  `;

  if (hasSubtopics) {
    const subtopicsOverride = overrides.find(o => o.field_name === 'subtopics');
    const hasSubtopicsOverride = !!subtopicsOverride;
    const rawSubtopics = hasSubtopicsOverride && subtopicsOverride.original_value 
      ? (typeof subtopicsOverride.original_value === 'string' ? JSON.parse(subtopicsOverride.original_value) : subtopicsOverride.original_value)
      : cur.subtopics;

    cur.subtopics.forEach((sub, subIdx) => {
      const subtopicName = sub.subtopic_name || '';
      const rawSub = rawSubtopics[subIdx] || {};

      reviewFormHtml += `
        <div class="subtopic-edit-group mb-24 p-16 border rounded" style="border: 1px solid var(--border); padding: 16px; border-radius: 8px; margin-bottom: 24px; background: var(--bg-card);">
          <h3 class="mb-12" style="font-size: 1.1rem; color: var(--accent); border-bottom: 1px solid var(--border); padding-bottom: 8px;"><i class="ph-light ph-book-open" style="vertical-align:middle; margin-right:6px;"></i>Subtopic ${subIdx + 1}: ${esc(subtopicName)}</h3>
      `;

      sections.forEach(s => {
        const rawVal = rawSub[s.key];
        let rawValStr = '';
        if (rawVal != null) {
          rawValStr = Array.isArray(rawVal) ? rawVal.join('\n') : String(rawVal);
        }

        const currVal = sub[s.key];
        let currValStr = '';
        if (currVal != null) {
          currValStr = Array.isArray(currVal) ? currVal.join('\n') : String(currVal);
        }

        const isFieldOverridden = hasSubtopicsOverride && (rawValStr.trim() !== currValStr.trim());
        const oBadge = isFieldOverridden 
          ? `<span class="override-badge active-override-badge">Override Active</span>` 
          : `<span class="override-badge pending-override-badge" style="display:none">Pending Override</span>`;
        const oClass = isFieldOverridden ? 'field-overridden' : '';
        const oHelp = isFieldOverridden ? `
          <div class="original-value-help">
            <strong>Original Raw LLM Content:</strong>
            <pre>${esc(rawValStr)}</pre>
          </div>
        ` : '';

        reviewFormHtml += `
          <div class="form-group override-group">
            <div class="flex-between align-center mb-8">
              <label class="form-label mb-0">${esc(s.title)}</label>
              <div style="display: flex; gap: 8px; align-items: center;">
                <button class="btn btn-secondary btn-sm btn-insert-image" type="button" data-target="edit-subtopic-${subIdx}-${s.key}"><i class="ph-light ph-image"></i> Insert Image</button>
                ${oBadge}
              </div>
            </div>
            <textarea class="form-textarea edit-curriculum-field ${oClass}" 
                      id="edit-subtopic-${subIdx}-${s.key}" 
                      data-subtopic-index="${subIdx}"
                      data-key="${s.key}" 
                      data-array="${s.array ? 'true' : 'false'}" 
                      data-original="${esc(rawValStr)}" 
                      rows="${s.rows}">${esc(currValStr)}</textarea>
            ${oHelp}
          </div>
        `;
      });

      reviewFormHtml += `</div>`;
    });
  } else {
    for (const s of sections) {
      const rawVal = content.content_json ? content.content_json[s.key] : null;
      let rawValStr = '';
      if (rawVal != null) {
        if (Array.isArray(rawVal)) {
          rawValStr = rawVal.join('\n');
        } else {
          rawValStr = String(rawVal);
        }
      }

      const override = overrides.find(o => o.field_name === s.key);
      const hasOverride = !!override;
      
      let displayValStr = rawValStr;
      let origValStr = rawValStr;
      if (hasOverride) {
        const corrVal = override.corrected_value;
        if (corrVal != null) {
          displayValStr = Array.isArray(corrVal) ? corrVal.join('\n') : String(corrVal);
        }
        const origVal = override.original_value;
        if (origVal != null) {
          origValStr = Array.isArray(origVal) ? origVal.join('\n') : String(origVal);
        }
      }

      const oBadge = hasOverride 
        ? `<span class="override-badge active-override-badge">Override Active</span>` 
        : `<span class="override-badge pending-override-badge" style="display:none">Pending Override</span>`;
      const oClass = hasOverride ? 'field-overridden' : '';
      const oHelp = hasOverride ? `
        <div class="original-value-help">
          <strong>Original Raw LLM Content:</strong>
          <pre>${esc(origValStr)}</pre>
        </div>
      ` : '';

      reviewFormHtml += `
        <div class="form-group override-group">
          <div class="flex-between align-center mb-8">
            <label class="form-label mb-0">${esc(s.title)}</label>
            <div style="display: flex; gap: 8px; align-items: center;">
              <button class="btn btn-secondary btn-sm btn-insert-image" type="button" data-target="edit-${s.key}"><i class="ph-light ph-image"></i> Insert Image</button>
              ${oBadge}
            </div>
          </div>
          <textarea class="form-textarea edit-curriculum-field ${oClass}" 
                    id="edit-${s.key}" 
                    data-key="${s.key}" 
                    data-array="${s.array ? 'true' : 'false'}" 
                    data-original="${esc(origValStr)}" 
                    rows="${s.rows}">${esc(displayValStr)}</textarea>
          ${oHelp}
        </div>
      `;
    }
  }

  // Render FAQ editor list
  const faqs = cur.faq || [];
  let faqEditorItemsHtml = '';
  faqs.forEach((item, faqIdx) => {
    faqEditorItemsHtml += `
      <div class="faq-editor-item" data-faq-index="${faqIdx}">
        <button class="btn btn-danger btn-sm btn-remove-faq" type="button" data-index="${faqIdx}">Remove</button>
        <div class="form-group mb-12">
          <label class="form-label" style="font-size: 10px;">Question ${faqIdx + 1}</label>
          <input type="text" class="form-input edit-faq-question" value="${esc(item.question || '')}" placeholder="Question" />
        </div>
        <div class="form-group mb-0">
          <label class="form-label" style="font-size: 10px;">Answer ${faqIdx + 1}</label>
          <textarea class="form-textarea edit-faq-answer" rows="3" placeholder="Answer">${esc(item.answer || '')}</textarea>
        </div>
      </div>
    `;
  });

  reviewFormHtml += `
    <div class="faq-editor-container">
      <div class="flex-between align-center mb-16">
        <h3 class="faq-editor-title mb-0"><i class="ph-light ph-question" style="vertical-align:middle; margin-right:6px;"></i>Edit Frequently Asked Questions</h3>
        <button class="btn btn-secondary btn-sm" id="btn-add-faq" type="button"><i class="ph-light ph-plus"></i> Add FAQ</button>
      </div>
      <div id="faq-editor-list" style="margin-bottom: 24px;">
        ${faqEditorItemsHtml}
      </div>
    </div>
    
    <div class="form-group">
      <label class="form-label">Review Notes</label>
        <textarea class="form-textarea" id="review-notes" rows="3" placeholder="Add review notes...">${esc(content.review_notes || '')}</textarea>
      </div>
      <div class="form-actions">
        <button class="btn btn-primary" id="btn-approve">Approve</button>
        <button class="btn btn-secondary" id="btn-save-review">Save Changes</button>
        <button class="btn btn-secondary" id="btn-regenerate">Regenerate</button>
        <button class="btn btn-danger" id="btn-reject">Reject</button>
      </div>
    </div>
  `;

  html += reviewFormHtml;

  setTimeout(() => bindReviewButtons(content.id, content.version, cur, topic), 0);

  return html;
}

function bindReviewButtons(contentId, version, cur, topic) {
  const approve = $('#btn-approve');
  const save    = $('#btn-save-review');
  const regen   = $('#btn-regenerate');
  const reject  = $('#btn-reject');
  const notes   = $('#review-notes');
  if (!approve) return;

  // ── Bind FAQ Accordion clicks ────────────────────────────────
  $$('.faq-question').forEach(btn => {
    btn.addEventListener('click', () => {
      const targetId = btn.dataset.target;
      const panel = document.getElementById(targetId);
      const item = btn.closest('.faq-item');
      if (!panel || !item) return;
      
      const isOpen = item.classList.contains('open');
      if (isOpen) {
        item.classList.remove('open');
        panel.style.maxHeight = null;
      } else {
        // Close other open panels first (standard single-expand accordion)
        $$('.faq-item.open').forEach(openItem => {
          openItem.classList.remove('open');
          const openPanel = openItem.querySelector('.faq-answer');
          if (openPanel) openPanel.style.maxHeight = null;
        });
        
        item.classList.add('open');
        panel.style.maxHeight = panel.scrollHeight + 'px';
      }
    });
  });

  // ── Bind FAQ Editor Add/Remove Buttons ───────────────────────
  const addFaqBtn = $('#btn-add-faq');
  const faqEditorList = $('#faq-editor-list');
  if (addFaqBtn && faqEditorList) {
    addFaqBtn.addEventListener('click', () => {
      const newIdx = faqEditorList.querySelectorAll('.faq-editor-item').length;
      const newItem = document.createElement('div');
      newItem.className = 'faq-editor-item';
      newItem.dataset.faqIndex = newIdx;
      newItem.innerHTML = `
        <button class="btn btn-danger btn-sm btn-remove-faq" type="button" data-index="${newIdx}">Remove</button>
        <div class="form-group mb-12">
          <label class="form-label" style="font-size: 10px;">Question ${newIdx + 1}</label>
          <input type="text" class="form-input edit-faq-question" value="" placeholder="Question" />
        </div>
        <div class="form-group mb-0">
          <label class="form-label" style="font-size: 10px;">Answer ${newIdx + 1}</label>
          <textarea class="form-textarea edit-faq-answer" rows="3" placeholder="Answer"></textarea>
        </div>
      `;
      
      newItem.querySelector('.btn-remove-faq').addEventListener('click', () => {
        newItem.remove();
        reindexFaqEditor();
      });
      
      faqEditorList.appendChild(newItem);
    });
  }

  $$('.btn-remove-faq').forEach(btn => {
    btn.addEventListener('click', () => {
      const item = btn.closest('.faq-editor-item');
      if (item) {
        item.remove();
        reindexFaqEditor();
      }
    });
  });

  function reindexFaqEditor() {
    if (!faqEditorList) return;
    const items = faqEditorList.querySelectorAll('.faq-editor-item');
    items.forEach((item, idx) => {
      item.dataset.faqIndex = idx;
      const titleQ = item.querySelector('.form-group:nth-of-type(1) .form-label');
      const titleA = item.querySelector('.form-group:nth-of-type(2) .form-label');
      if (titleQ) titleQ.textContent = `Question ${idx + 1}`;
      if (titleA) titleA.textContent = `Answer ${idx + 1}`;
      const rmBtn = item.querySelector('.btn-remove-faq');
      if (rmBtn) rmBtn.dataset.index = idx;
    });
  }

  // ── Bind Image Insertion triggers ────────────────────────────
  $$('.btn-insert-image').forEach(btn => {
    btn.addEventListener('click', () => {
      const targetId = btn.dataset.target;
      const textarea = document.getElementById(targetId);
      if (!textarea) return;
      
      const fileInput = document.createElement('input');
      fileInput.type = 'file';
      fileInput.accept = 'image/*';
      fileInput.style.display = 'none';
      document.body.appendChild(fileInput);
      
      fileInput.addEventListener('change', async () => {
        const file = fileInput.files[0];
        if (!file) {
          fileInput.remove();
          return;
        }
        
        btn.disabled = true;
        btn.innerHTML = `<i class="ph-light ph-spinner-gap" style="animation: spin 1.5s linear infinite; display: inline-block;"></i> Uploading...`;
        
        try {
          const token = currentUser ? currentUser.access_token : '';
          const headers = {};
          if (token) {
            headers['Authorization'] = `Bearer ${token}`;
          }
          
          const fileBytes = await file.arrayBuffer();
          const uploadUrl = `/api/upload?filename=${encodeURIComponent(file.name)}`;
          const res = await fetch(uploadUrl, {
            method: 'POST',
            headers: headers,
            body: fileBytes
          });
          
          if (!res.ok) {
            const errText = await res.text();
            throw new Error(errText || 'Upload failed');
          }
          
          const data = await res.json();
          const localPath = data.local_path;
          
          const caption = prompt('Enter a caption for the image (optional):', '') || '';
          
          const startPos = textarea.selectionStart;
          const endPos = textarea.selectionEnd;
          const text = textarea.value;
          const imageMarkdown = `\n![${caption}](${localPath})\n`;
          
          textarea.value = text.substring(0, startPos) + imageMarkdown + text.substring(endPos);
          textarea.selectionStart = textarea.selectionEnd = startPos + imageMarkdown.length;
          textarea.focus();
          
          textarea.dispatchEvent(new Event('input'));
          toast('Image uploaded and inserted successfully!', 'success');
        } catch (error) {
          toast(`Upload failed: ${error.message}`, 'error');
        } finally {
          btn.disabled = false;
          btn.innerHTML = `<i class="ph-light ph-image"></i> Insert Image`;
          fileInput.remove();
        }
      });
      
      fileInput.click();
    });
  });

  const hasSubtopics = cur && Array.isArray(cur.subtopics);
  let sections = [
    { key: 'summary',             array: false },
    { key: 'definition',          array: false },
    { key: 'purpose',             array: false },
    { key: 'key_properties',      array: true },
    { key: 'benefits',            array: true },
    { key: 'limitations',         array: true },
    { key: 'common_misconceptions', array: true },
    { key: 'related_topics',      array: true },
  ];

  if (hasSubtopics && cur.subtopics.length > 0) {
    const subkeys = Object.keys(cur.subtopics[0]).filter(k => k !== 'subtopic_name');
    const isCustom = subkeys.some(k => !['summary', 'definition', 'purpose', 'key_properties', 'benefits', 'limitations', 'common_misconceptions', 'related_topics'].includes(k));
    if (isCustom) {
      sections = subkeys.map(k => {
        const isArray = Array.isArray(cur.subtopics[0][k]);
        return { key: k, array: isArray };
      });
    }
  } else if (cur) {
    const topkeys = Object.keys(cur).filter(k => !['topic_name', 'subtopics', 'faq'].includes(k));
    const isCustom = topkeys.some(k => !['summary', 'definition', 'purpose', 'key_properties', 'benefits', 'limitations', 'common_misconceptions', 'related_topics'].includes(k));
    if (isCustom) {
      sections = topkeys.map(k => {
        const isArray = Array.isArray(cur[k]);
        return { key: k, array: isArray };
      });
    }
  }

  $$('.edit-curriculum-field').forEach(ta => {
    ta.addEventListener('input', () => {
      const orig = (ta.dataset.original || '').trim();
      const curr = ta.value.trim();
      const parent = ta.closest('.form-group');
      const badgePending = parent.querySelector('.pending-override-badge');
      const badgeActive = parent.querySelector('.active-override-badge');
      
      if (curr !== orig) {
        ta.classList.add('field-modified');
        if (badgeActive) {
          badgeActive.textContent = 'Modified Override';
          badgeActive.className = 'override-badge modified-override-badge';
        } else {
          if (badgePending) badgePending.style.display = 'inline-block';
        }
      } else {
        ta.classList.remove('field-modified');
        if (badgeActive) {
          badgeActive.textContent = 'Override Active';
          badgeActive.className = 'override-badge active-override-badge';
        } else {
          if (badgePending) badgePending.style.display = 'none';
        }
      }
    });
  });

  const getUpdatedContentJson = () => {
    // Extract FAQs from Editor List
    const updatedFaqs = [];
    const faqItems = document.querySelectorAll('.faq-editor-item');
    faqItems.forEach(item => {
      const qInput = item.querySelector('.edit-faq-question');
      const aInput = item.querySelector('.edit-faq-answer');
      if (qInput && aInput) {
        const question = qInput.value.trim();
        const answer = aInput.value.trim();
        if (question || answer) {
          updatedFaqs.push({ question, answer });
        }
      }
    });

    if (hasSubtopics) {
      const subtopics = [];
      cur.subtopics.forEach((sub, subIdx) => {
        const subtopicName = sub.subtopic_name || '';
        const subtopicObj = { subtopic_name: subtopicName };

        sections.forEach(s => {
          const ta = document.getElementById(`edit-subtopic-${subIdx}-${s.key}`);
          if (ta) {
            const isArray = s.array;
            const val = ta.value.trim();
            if (isArray) {
              subtopicObj[s.key] = val ? val.split('\n').map(item => item.trim()).filter(Boolean) : [];
            } else {
              subtopicObj[s.key] = val;
            }
          } else {
            subtopicObj[s.key] = sub[s.key];
          }
        });
        subtopics.push(subtopicObj);
      });

      return {
        topic_name: cur.topic_name || (topic ? topic.topic_name : ''),
        subtopics: subtopics,
        faq: updatedFaqs
      };
    } else {
      const updated = {
        topic_name: cur.topic_name || (topic ? topic.topic_name : ''),
        faq: updatedFaqs
      };
      $$('.edit-curriculum-field').forEach(ta => {
        const key = ta.dataset.key;
        const isArray = ta.dataset.array === 'true';
        const val = ta.value.trim();
        if (isArray) {
          updated[key] = val ? val.split('\n').map(item => item.trim()).filter(Boolean) : [];
        } else {
          updated[key] = val;
        }
      });
      return updated;
    }
  };

  const updateLocalContent = (res) => {
    if (res && res.data && res.data.length > 0) {
      const idx = state.content.findIndex(c => c.id === contentId);
      if (idx !== -1) {
        state.content[idx] = res.data[0];
      } else {
        state.content.push(res.data[0]);
      }
    }
  };

  approve.addEventListener('click', async () => {
    const contentJson = getUpdatedContentJson();
    try {
      const res = await submitReviewAction(contentId, state.selectedTopicId, 'approved', contentJson, notes.value, version);
      updateLocalContent(res);
      toast('Content approved', 'success');
    } catch (error) {
      toast(`Approval failed: ${mapSupabaseError(error)}`, 'error');
    }
    renderContent();
  });

  save.addEventListener('click', async () => {
    const contentJson = getUpdatedContentJson();
    try {
      const res = await submitReviewAction(contentId, state.selectedTopicId, 'pending', contentJson, notes.value, version);
      updateLocalContent(res);
      toast('Changes saved', 'success');
    } catch (error) {
      toast(`Save failed: ${mapSupabaseError(error)}`, 'error');
    }
    renderContent();
  });

  const copyBtn = $('#btn-copy-md');
  if (copyBtn) {
    copyBtn.addEventListener('click', () => {
      const mdText = $('#markdown-preview').textContent;
      navigator.clipboard.writeText(mdText);
      toast('Markdown copied to clipboard', 'success');
    });
  }

  regen.addEventListener('click', async () => {
    const contentJson = getUpdatedContentJson();
    try {
      const res = await submitReviewAction(contentId, state.selectedTopicId, 'needs_regeneration', contentJson, notes.value, version);
      updateLocalContent(res);
      toast('Regeneration queued', 'success');
    } catch (error) {
      toast(`Regeneration failed: ${mapSupabaseError(error)}`, 'error');
    }
    renderContent();
  });

  reject.addEventListener('click', async () => {
    const contentJson = getUpdatedContentJson();
    try {
      const res = await submitReviewAction(contentId, state.selectedTopicId, 'rejected', contentJson, notes.value, version);
      updateLocalContent(res);
      toast('Content rejected', 'error');
    } catch (error) {
      toast(`Reject failed: ${mapSupabaseError(error)}`, 'error');
    }
    renderContent();
  });
}
