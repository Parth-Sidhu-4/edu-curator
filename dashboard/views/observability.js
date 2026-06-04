// ═══════════════════════════════════════════════════════════════
// views/observability.js
// ═══════════════════════════════════════════════════════════════

import { state, db } from '../state.js';
import { fetchTraceStats, fetchTraces } from '../api.js';
import { $, $$, esc, formatCost, formatTs } from '../utils.js';

export async function renderObservability() {
  const mainContent = $('#main-content');
  if (!mainContent) return;

  const [allStats, recentTraces] = await Promise.all([fetchTraceStats(), fetchTraces()]);

  let totalCalls = allStats.length;
  let totalTokens = 0, promptTokens = 0, completionTokens = 0;
  const byStage = {};
  const byModel = {};
  const byTopic = {};

  for (const t of allStats) {
    const tok   = t.total_tokens   || 0;
    const ptok  = t.prompt_tokens  || 0;
    const ctok  = t.completion_tokens || 0;
    totalTokens += tok;
    promptTokens += ptok;
    completionTokens += ctok;

    const stg = t.stage || 'unknown';
    if (!byStage[stg]) byStage[stg] = { calls: 0, prompt: 0, completion: 0, total: 0 };
    byStage[stg].calls++;
    byStage[stg].prompt += ptok;
    byStage[stg].completion += ctok;
    byStage[stg].total += tok;

    const mdl = t.model || 'unknown';
    if (!byModel[mdl]) byModel[mdl] = { calls: 0, total: 0 };
    byModel[mdl].calls++;
    byModel[mdl].total += tok;

    const sn = t.topic_sn != null ? t.topic_sn : '—';
    if (!byTopic[sn]) byTopic[sn] = { calls: 0, total: 0 };
    byTopic[sn].calls++;
    byTopic[sn].total += tok;
  }

  const traces = recentTraces;

  mainContent.innerHTML = `
    <h1 class="page-title">Observability</h1>
    <p class="page-subtitle">LLM usage and trace analytics &mdash; metrics computed across all ${totalCalls.toLocaleString()} recorded traces</p>

    <div class="metrics-row">
      <div class="metric-item">
        <div class="metric-value">${totalCalls}</div>
        <div class="metric-label">Total API Calls</div>
      </div>
      <div class="metric-item">
        <div class="metric-value">${totalTokens.toLocaleString()}</div>
        <div class="metric-label">Total Tokens</div>
      </div>
      <div class="metric-item">
        <div class="metric-value">${promptTokens.toLocaleString()} / ${completionTokens.toLocaleString()}</div>
        <div class="metric-label">Prompt / Completion</div>
      </div>
      <div class="metric-item">
        <div class="metric-value">${formatCost(totalTokens)}</div>
        <div class="metric-label">Est. Cost</div>
      </div>
    </div>

    <h2 class="section-heading">By Stage</h2>
    <div class="table-wrap">
      <table>
        <thead><tr><th>Stage</th><th>Calls</th><th>Prompt Tokens</th><th>Completion Tokens</th><th>Total</th><th>Est. Cost</th></tr></thead>
        <tbody>
          ${Object.entries(byStage).map(([k, v]) => `
            <tr>
              <td>${esc(k)}</td>
              <td>${v.calls}</td>
              <td>${v.prompt.toLocaleString()}</td>
              <td>${v.completion.toLocaleString()}</td>
              <td>${v.total.toLocaleString()}</td>
              <td>${formatCost(v.total)}</td>
            </tr>
          `).join('')}
          ${Object.keys(byStage).length === 0 ? `<tr><td colspan="6" class="text-muted" style="text-align:center;padding:24px;">No data</td></tr>` : ''}
        </tbody>
      </table>
    </div>

    <hr class="section-divider" />

    <div class="two-col">
      <div>
        <h2 class="section-heading">By Model</h2>
        <div class="table-wrap">
          <table>
            <thead><tr><th>Model</th><th>Calls</th><th>Total Tokens</th></tr></thead>
            <tbody>
              ${Object.entries(byModel).map(([k, v]) => `
                <tr><td>${esc(k)}</td><td>${v.calls}</td><td>${v.total.toLocaleString()}</td></tr>
              `).join('')}
              ${Object.keys(byModel).length === 0 ? `<tr><td colspan="3" class="text-muted" style="text-align:center;padding:24px;">No data</td></tr>` : ''}
            </tbody>
          </table>
        </div>
      </div>
      <div>
        <h2 class="section-heading">By Topic SN</h2>
        <div class="table-wrap">
          <table>
            <thead><tr><th>SN</th><th>Calls</th><th>Total Tokens</th></tr></thead>
            <tbody>
              ${Object.entries(byTopic).map(([k, v]) => `
                <tr><td>${esc(k)}</td><td>${v.calls}</td><td>${v.total.toLocaleString()}</td></tr>
              `).join('')}
              ${Object.keys(byTopic).length === 0 ? `<tr><td colspan="3" class="text-muted" style="text-align:center;padding:24px;">No data</td></tr>` : ''}
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <hr class="section-divider" />

    <h2 class="section-heading">Recent Traces <span class="text-muted" style="font-size:0.75rem;font-weight:400;">(latest ${traces.length} of ${totalCalls.toLocaleString()} total)</span></h2>
    <div class="table-wrap" id="traces-table-area">
      <table>
        <thead>
          <tr>
            <th>ID</th>
            <th>Time</th>
            <th>Stage</th>
            <th>Topic SN</th>
            <th>Model</th>
            <th>Latency</th>
            <th>Tokens</th>
          </tr>
        </thead>
        <tbody>
          ${traces.length === 0
            ? `<tr><td colspan="7" class="text-muted" style="text-align:center;padding:24px;">No traces found</td></tr>`
            : traces.slice(0, 50).map(t => `
              <tr class="trace-row-expandable" data-trace-id="${t.id}">
                <td>${esc(String(t.id).slice(0, 8))}</td>
                <td>${formatTs(t.ts)}</td>
                <td>${esc(t.stage)}</td>
                <td>${t.topic_sn != null ? t.topic_sn : '—'}</td>
                <td>${esc(t.model)}</td>
                <td>${t.latency_ms != null ? t.latency_ms + 'ms' : '—'}</td>
                <td>${(t.total_tokens || 0).toLocaleString()}</td>
              </tr>
              ${state.expandedTraceId === t.id ? renderTraceDetail(t) : ''}
            `).join('')}
        </tbody>
      </table>
    </div>
  `;

  $$('.trace-row-expandable').forEach(row => {
    row.addEventListener('click', async () => {
      const id = row.dataset.traceId;
      if (state.expandedTraceId === id) {
        state.expandedTraceId = null;
        renderObservability();
      } else {
        state.expandedTraceId = id;
        renderObservability();

        const trace = state.traces.find(x => String(x.id) === id);
        if (trace && trace.prompt === undefined) {
          try {
            const { data, error } = await db.from('llm_traces').select('prompt, response').eq('id', id).single();
            if (!error && data) {
              trace.prompt = data.prompt;
              trace.response = data.response;
              if (state.expandedTraceId === id) {
                renderObservability();
              }
            }
          } catch (err) {
            console.error('Failed to lazy load trace detail:', err);
          }
        }
      }
    });
  });
}

function renderTraceDetail(t) {
  if (t.prompt === undefined) {
    return `
      <tr>
        <td colspan="7" style="padding:16px;text-align:center;color:var(--text-muted);">
          <div class="spinner-small" style="display:inline-block;margin-right:8px;"></div> Loading trace details...
        </td>
      </tr>
    `;
  }

  let promptStr = '';
  try {
    const msgs = typeof t.prompt === 'string' ? JSON.parse(t.prompt) : t.prompt;
    if (Array.isArray(msgs)) {
      promptStr = msgs.map(m => `[${m.role}]\n${m.content}`).join('\n\n');
    } else {
      promptStr = JSON.stringify(t.prompt, null, 2);
    }
  } catch {
    promptStr = String(t.prompt || '');
  }

  return `
    <tr>
      <td colspan="7" style="padding:0;border-bottom:1px solid var(--border);">
        <div class="trace-detail">
          <h4>Prompt</h4>
          <pre class="code-block">${esc(promptStr)}</pre>
        </div>
        <div class="trace-detail">
          <h4>Response</h4>
          <pre class="code-block">${esc(t.response || '—')}</pre>
        </div>
      </td>
    </tr>
  `;
}
