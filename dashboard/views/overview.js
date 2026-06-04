// ═══════════════════════════════════════════════════════════════
// views/overview.js
// ═══════════════════════════════════════════════════════════════

import {
  fetchTopics, fetchSources, fetchFactCount, fetchContentCount,
  fetchJobs, fetchEvalJobs, fetchTraceStats
} from '../api.js';
import { $, esc, formatCost, typePill, statusPill } from '../utils.js';

export async function renderOverview() {
  const mainContent = $('#main-content');
  if (!mainContent) return;

  const [topics, sources] = await Promise.all([fetchTopics(), fetchSources()]);
  const [factCount, contentCount, curationJobs, evaluationJobs, traceStats] = await Promise.all([
    fetchFactCount(),
    fetchContentCount(),
    fetchJobs(),
    fetchEvalJobs(),
    fetchTraceStats(),
  ]);
  const activeSources = sources.filter(s => s.is_active !== false).length;
  const retiredSources = sources.filter(s => s.is_active === false).length;
  const allJobs = [...curationJobs, ...evaluationJobs];
  const completedJobs = allJobs.filter(j => j.status === 'completed').length;
  const failedJobs = allJobs.filter(j => j.status === 'failed').length;
  const openJobs = allJobs.filter(j => ['pending', 'running', 'processing'].includes(j.status)).length;
  const totalTokens = traceStats.reduce((sum, t) => sum + (t.total_tokens || 0), 0);

  mainContent.innerHTML = `
    <h1 class="page-title">Overview</h1>
    <p class="page-subtitle">Pipeline status at a glance</p>

    <div class="metrics-row">
      <div class="metric-item">
        <div class="metric-value">${topics.length}</div>
        <div class="metric-label">Total Topics</div>
      </div>
      <div class="metric-item">
        <div class="metric-value">${sources.length}</div>
        <div class="metric-label">Total Sources</div>
      </div>
      <div class="metric-item">
        <div class="metric-value">${factCount}</div>
        <div class="metric-label">Facts Extracted</div>
      </div>
      <div class="metric-item">
        <div class="metric-value">${contentCount}</div>
        <div class="metric-label">Content Generated</div>
      </div>
    </div>

    <div class="metrics-row">
      <div class="metric-item">
        <div class="metric-value">${activeSources} / ${retiredSources}</div>
        <div class="metric-label">Active / Retired Sources</div>
      </div>
      <div class="metric-item">
        <div class="metric-value">${completedJobs} / ${failedJobs} / ${openJobs}</div>
        <div class="metric-label">Done / Failed / Open Jobs</div>
      </div>
      <div class="metric-item">
        <div class="metric-value">${traceStats.length}</div>
        <div class="metric-label">LLM Calls</div>
      </div>
      <div class="metric-item">
        <div class="metric-value">${formatCost(totalTokens)}</div>
        <div class="metric-label">Est. LLM Cost</div>
      </div>
    </div>

    <h2 class="section-heading">All Topics</h2>
    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Chapter</th>
            <th>Topic Name</th>
            <th>Type</th>
            <th>Status</th>
            <th>Difficulty</th>
          </tr>
        </thead>
        <tbody>
          ${topics.length === 0
            ? `<tr><td colspan="5" class="text-muted" style="text-align:center;padding:32px;">No topics found</td></tr>`
            : topics.map(t => `
              <tr>
                <td>${esc(t.chapter)}</td>
                <td>${esc(t.topic_name)}</td>
                <td>${typePill(t.topic_type)}</td>
                <td>${statusPill(t.status)}</td>
                <td>${esc(t.difficulty_level || '—')}</td>
              </tr>
            `).join('')}
        </tbody>
      </table>
    </div>
  `;
}
