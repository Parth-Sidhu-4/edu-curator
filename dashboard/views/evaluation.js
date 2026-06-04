// ═══════════════════════════════════════════════════════════════
// views/evaluation.js
// ═══════════════════════════════════════════════════════════════

import { state } from '../state.js';
import { fetchTopics, fetchEval, fetchEvalJobs, apiFetch, resetJob } from '../api.js';
import {
  $, esc, statusPill, toast, applyCustomSelects, renderMath,
  buildTopicOptions, mapSupabaseError, safeMarkdown
} from '../utils.js';

export async function renderEvaluation() {
  const mainContent = $('#main-content');
  if (!mainContent) return;

  await fetchTopics();

  const selId = state.selectedEvalTopicId;
  let evalHtml = '';
  let jobHtml = '';
  let activeJob = null;

  if (selId) {
    const evalData = await fetchEval(selId);
    if (evalData) {
      const faith = evalData.faithfulness_score ?? evalData.faithfulness ?? null;
      const compl = evalData.completeness_score ?? evalData.completeness ?? null;
      const fReason = evalData.faithfulness_reasoning || '';
      const cReason = evalData.completeness_reasoning || '';

      const scoreClass = (v) => {
        if (v == null) return '';
        if (v >= 0.7) return 'good';
        if (v >= 0.4) return 'mid';
        return 'low';
      };

      evalHtml = `
        <div class="eval-scores">
          <div class="eval-score-item">
            <div class="eval-score-value ${scoreClass(faith)}">${faith != null ? (typeof faith === 'number' ? faith.toFixed(2) : faith) : '—'}</div>
            <div class="eval-score-label">Faithfulness</div>
            ${fReason ? `<div class="eval-reasoning text-sm text-muted mt-8">${safeMarkdown(fReason)}</div>` : ''}
          </div>
          <div class="eval-score-item">
            <div class="eval-score-value ${scoreClass(compl)}">${compl != null ? (typeof compl === 'number' ? compl.toFixed(2) : compl) : '—'}</div>
            <div class="eval-score-label">Completeness</div>
            ${cReason ? `<div class="eval-reasoning text-sm text-muted mt-8">${safeMarkdown(cReason)}</div>` : ''}
          </div>
        </div>
      `;
    } else {
      evalHtml = `
        <div class="empty-state">
          <p>No evaluation results for this topic.</p>
        </div>
      `;
    }

    const evalJobs = await fetchEvalJobs(selId);
    activeJob = evalJobs.find(j => j.status === 'running' || j.status === 'processing');
    if (!activeJob) {
      activeJob = evalJobs.find(j => j.status === 'pending');
    }
    if (!activeJob && evalJobs.length > 0) {
      activeJob = evalJobs[0];
    }

    const showJobBox = activeJob && (activeJob.status === 'running' || activeJob.status === 'processing' || activeJob.status === 'pending' || activeJob.status === 'failed');
    if (showJobBox) {
      const isFailed = activeJob.status === 'failed';
      const errorMsgHtml = isFailed && activeJob.error_message ? `<p class="text-sm text-error mt-4" style="color: var(--error);">Error: ${esc(activeJob.error_message)}</p>` : '';
      jobHtml = `
        <div class="mt-16 mb-24">
          <div class="flex-between align-center">
            <p class="text-sm text-muted">Job Status: <span id="eval-job-status-container">${statusPill(activeJob.status)}</span></p>
            <div style="display: flex; gap: 8px;">
              <button class="btn btn-secondary btn-sm" id="btn-copy-eval-log">Copy Logs</button>
              ${isFailed ? '' : `<button class="btn btn-danger btn-sm" id="btn-eval-force-reset" data-job-id="${activeJob.id}">Force Reset Stuck Job</button>`}
            </div>
          </div>
          ${errorMsgHtml}
          <pre class="code-block mt-8" id="eval-job-log-box" style="min-height: 120px; max-height: 350px; overflow-y: auto; white-space: pre-wrap; font-family: monospace;">${esc(activeJob.logs || `[System] Job is ${activeJob.status}. Waiting for worker to start streaming logs...`)}</pre>
        </div>
      `;

      if (activeJob.status !== 'failed') {
        if (!state._evalJobPollTimer) {
          state._evalJobPollTimer = setInterval(async () => {
            if (state.view === 'evaluation' && state.selectedEvalTopicId === selId) {
              const jobs = await fetchEvalJobs(selId);
              let updatedActive = jobs.find(j => j.status === 'running' || j.status === 'processing');
              if (!updatedActive) {
                updatedActive = jobs.find(j => j.status === 'pending');
              }
              if (!updatedActive) {
                updatedActive = jobs[0];
              }

              if (!updatedActive || (updatedActive.status !== 'running' && updatedActive.status !== 'processing' && updatedActive.status !== 'pending')) {
                clearInterval(state._evalJobPollTimer);
                state._evalJobPollTimer = null;
                toast('Evaluation completed!', 'success');
                renderEvaluation();
                return;
              }

              const logBox = document.getElementById('eval-job-log-box');
              const statusContainer = document.getElementById('eval-job-status-container');
              if (logBox) {
                logBox.textContent = updatedActive.logs || `[System] Job is ${updatedActive.status}. Waiting for worker to start streaming logs...`;
                logBox.scrollTop = logBox.scrollHeight;
              }
              if (statusContainer) {
                statusContainer.innerHTML = statusPill(updatedActive.status);
              }
            } else {
              clearInterval(state._evalJobPollTimer);
              state._evalJobPollTimer = null;
            }
          }, 2000);
        }
      }
    } else {
      if (state._evalJobPollTimer) {
        clearInterval(state._evalJobPollTimer);
        state._evalJobPollTimer = null;
      }
    }
  }

  const hasActiveJob = activeJob && (activeJob.status === 'running' || activeJob.status === 'processing' || activeJob.status === 'pending');
  const runBtnText = hasActiveJob ? 'Running Evaluation...' : 'Run Evaluation';
  const isRunBtnDisabled = !selId || hasActiveJob;

  mainContent.innerHTML = `
    <h1 class="page-title">Evaluation</h1>
    <p class="page-subtitle">RAG quality assessment</p>

    <div class="max-w-form">
      <div class="form-group">
        <label class="form-label">Select Topic</label>
        <select class="form-select" id="eval-topic-select">
          ${buildTopicOptions(selId)}
        </select>
      </div>
    </div>

    <div class="form-actions mb-24">
      <button class="btn btn-secondary" id="btn-run-eval" ${isRunBtnDisabled ? 'disabled' : ''}>${runBtnText}</button>
    </div>

    ${jobHtml}
    ${evalHtml}
  `;

  applyCustomSelects(mainContent);

  $('#eval-topic-select').addEventListener('change', (e) => {
    state.selectedEvalTopicId = e.target.value || null;
    renderEvaluation();
  });

  const runBtn = $('#btn-run-eval');
  if (runBtn) {
    runBtn.addEventListener('click', async () => {
      if (!state.selectedEvalTopicId) return;
      const topicId = state.selectedEvalTopicId;
      runBtn.disabled = true;
      runBtn.textContent = 'Running Evaluation...';

      try {
        const res = await apiFetch('/api/evaluate', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({ topic_id: topicId })
        });
        const data = await res.json();
        if (res.ok && data.status === 'processing') {
          toast('Evaluation started in background...', 'success');
          renderEvaluation();
        } else {
          toast(data.error || 'Evaluation trigger failed', 'error');
          renderEvaluation();
        }
      } catch (e) {
        toast('Failed to reach evaluation API', 'error');
        renderEvaluation();
      }
    });
  }

  const resetBtn = $('#btn-eval-force-reset');
  if (resetBtn) {
    resetBtn.addEventListener('click', async () => {
      const jobId = resetBtn.dataset.jobId;
      resetBtn.disabled = true;
      resetBtn.textContent = 'Resetting...';
      try {
        await resetJob('evaluation_jobs', jobId);
        toast('Job reset successfully', 'success');
      } catch (error) {
        toast(`Reset failed: ${mapSupabaseError(error)}`, 'error');
      }
      renderEvaluation();
    });
  }

  const copyLogBtn = $('#btn-copy-eval-log');
  if (copyLogBtn) {
    copyLogBtn.addEventListener('click', () => {
      const logBox = $('#eval-job-log-box');
      if (logBox) {
        navigator.clipboard.writeText(logBox.textContent);
        toast('Logs copied to clipboard', 'success');
      }
    });
  }
}
