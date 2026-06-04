// ═══════════════════════════════════════════════════════════════
// api.js
// ═══════════════════════════════════════════════════════════════

import { db, currentUser, state, triggerReRender } from './state.js';
import { toast, mapSupabaseError, compareTopicNumbers } from './utils.js';

export async function apiFetch(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (currentUser && currentUser.access_token) {
    headers['Authorization'] = `Bearer ${currentUser.access_token}`;
  }
  return fetch(path, { ...options, headers });
}

export async function apiPost(path, payload) {
  const res = await apiFetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload || {})
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(data.error || `Request failed with ${res.status}`);
  }
  return data;
}

const fetchMeta = {
  topics: { inflight: false, lastFetched: 0 },
  sources: { inflight: false, lastFetched: 0 },
  content: { inflight: false, lastFetched: 0 },
  factCount: { inflight: false, lastFetched: 0 },
  contentCount: { inflight: false, lastFetched: 0 },
  jobs: { inflight: false, lastFetched: 0 },
  traces: { inflight: false, lastFetched: 0 },
  traceStats: { inflight: false, lastFetched: 0 },
};
const COOLDOWN_MS = 15000; // 15 seconds

export async function fetchTopics(force = false) {
  const now = Date.now();
  const meta = fetchMeta.topics;
  if (state.topics.length > 0 && !force) {
    if (!meta.inflight && (now - meta.lastFetched > COOLDOWN_MS)) {
      meta.inflight = true;
      db.from('syllabus_topics').select('*').order('created_at').then(({ data, error }) => {
        meta.inflight = false;
        if (!error && data) {
          meta.lastFetched = Date.now();
          const changed = JSON.stringify(state.topics) !== JSON.stringify(data);
          if (changed) {
            state.topics = data;
            state.topics.sort(compareTopicNumbers);
            triggerReRender();
          }
        }
      }).catch(() => { meta.inflight = false; });
    }
    return state.topics;
  }
  meta.inflight = true;
  const { data, error } = await db.from('syllabus_topics').select('*').order('created_at');
  meta.inflight = false;
  if (error) { toast('Failed to fetch topics', 'error'); return []; }
  meta.lastFetched = Date.now();
  state.topics = data || [];
  state.topics.sort(compareTopicNumbers);
  return state.topics;
}

export async function fetchSources(force = false) {
  const now = Date.now();
  const meta = fetchMeta.sources;
  if (state.sources.length > 0 && !force) {
    if (!meta.inflight && (now - meta.lastFetched > COOLDOWN_MS)) {
      meta.inflight = true;
      db.from('sources').select('*').order('created_at', { ascending: false }).then(({ data, error }) => {
        meta.inflight = false;
        if (!error && data) {
          meta.lastFetched = Date.now();
          const changed = JSON.stringify(state.sources) !== JSON.stringify(data);
          if (changed) {
            state.sources = data;
            triggerReRender();
          }
        }
      }).catch(() => { meta.inflight = false; });
    }
    return state.sources;
  }
  meta.inflight = true;
  const { data, error } = await db.from('sources').select('*').order('created_at', { ascending: false });
  meta.inflight = false;
  if (error) { toast('Failed to fetch sources', 'error'); return []; }
  meta.lastFetched = Date.now();
  state.sources = data || [];
  return state.sources;
}

export async function fetchContent(force = false) {
  const now = Date.now();
  const meta = fetchMeta.content;
  if (state.content.length > 0 && !force) {
    if (!meta.inflight && (now - meta.lastFetched > COOLDOWN_MS)) {
      meta.inflight = true;
      db.from('topic_content').select('*').then(({ data, error }) => {
        meta.inflight = false;
        if (!error && data) {
          meta.lastFetched = Date.now();
          const changed = JSON.stringify(state.content) !== JSON.stringify(data);
          if (changed) {
            state.content = data;
            triggerReRender();
          }
        }
      }).catch(() => { meta.inflight = false; });
    }
    return state.content;
  }
  meta.inflight = true;
  const { data, error } = await db.from('topic_content').select('*');
  meta.inflight = false;
  if (error) { toast('Failed to fetch content', 'error'); return []; }
  meta.lastFetched = Date.now();
  state.content = data || [];
  return state.content;
}

export async function fetchLatestKnowledge(topicId) {
  if (!topicId) return null;
  const { data, error } = await db
    .from('topic_knowledge')
    .select('*')
    .eq('topic_id', topicId)
    .order('updated_at', { ascending: false })
    .limit(1);
  if (error) return null;
  return data && data.length ? data[0] : null;
}

export async function fetchFacts() {
  const { data, error } = await db.from('fact_extractions').select('id', { count: 'exact', head: true });
  if (error) return 0;
  return data ? data.length : 0;
}

export async function fetchFactCount(force = false) {
  const now = Date.now();
  const meta = fetchMeta.factCount;
  if (state.factCount != null && !force) {
    if (!meta.inflight && (now - meta.lastFetched > COOLDOWN_MS)) {
      meta.inflight = true;
      db.from('fact_extractions').select('*', { count: 'exact', head: true }).then(({ count, error }) => {
        meta.inflight = false;
        if (!error && count != null) {
          meta.lastFetched = Date.now();
          if (state.factCount !== count) {
            state.factCount = count;
            triggerReRender();
          }
        }
      }).catch(() => { meta.inflight = false; });
    }
    return state.factCount;
  }
  meta.inflight = true;
  const { count, error } = await db.from('fact_extractions').select('*', { count: 'exact', head: true });
  meta.inflight = false;
  if (error) return 0;
  meta.lastFetched = Date.now();
  state.factCount = count || 0;
  return state.factCount;
}

export async function fetchContentCount(force = false) {
  const now = Date.now();
  const meta = fetchMeta.contentCount;
  if (state.contentCount != null && !force) {
    if (!meta.inflight && (now - meta.lastFetched > COOLDOWN_MS)) {
      meta.inflight = true;
      db.from('topic_content').select('*', { count: 'exact', head: true }).then(({ count, error }) => {
        meta.inflight = false;
        if (!error && count != null) {
          meta.lastFetched = Date.now();
          if (state.contentCount !== count) {
            state.contentCount = count;
            triggerReRender();
          }
        }
      }).catch(() => { meta.inflight = false; });
    }
    return state.contentCount;
  }
  meta.inflight = true;
  const { count, error } = await db.from('topic_content').select('*', { count: 'exact', head: true });
  meta.inflight = false;
  if (error) return 0;
  meta.lastFetched = Date.now();
  state.contentCount = count || 0;
  return state.contentCount;
}

export async function fetchJobs(topicId, force = false) {
  const now = Date.now();
  const meta = fetchMeta.jobs;
  if (!topicId && state.jobs.length > 0 && !force) {
    if (!meta.inflight && (now - meta.lastFetched > COOLDOWN_MS)) {
      meta.inflight = true;
      db.from('curation_jobs').select('*').order('created_at', { ascending: false }).then(({ data, error }) => {
        meta.inflight = false;
        if (!error && data) {
          meta.lastFetched = Date.now();
          const changed = JSON.stringify(state.jobs) !== JSON.stringify(data);
          if (changed) {
            state.jobs = data;
            triggerReRender();
          }
        }
      }).catch(() => { meta.inflight = false; });
    }
    return state.jobs;
  }
  if (!topicId) meta.inflight = true;
  const q = db.from('curation_jobs').select('*').order('created_at', { ascending: false });
  if (topicId) q.eq('topic_id', topicId);
  const { data, error } = await q;
  if (!topicId) {
    meta.inflight = false;
    meta.lastFetched = Date.now();
    state.jobs = data || [];
  }
  if (error) return [];
  return data || [];
}

export async function fetchEvalJobs(topicId) {
  const q = db.from('evaluation_jobs').select('*').order('created_at', { ascending: false });
  if (topicId) q.eq('topic_id', topicId);
  const { data, error } = await q;
  if (error) return [];
  return data || [];
}

export async function fetchTraces(force = false) {
  const now = Date.now();
  const meta = fetchMeta.traces;
  if (state.traces.length > 0 && !force) {
    if (!meta.inflight && (now - meta.lastFetched > COOLDOWN_MS)) {
      meta.inflight = true;
      db.from('llm_traces').select('id, ts, stage, topic_sn, model, latency_ms, total_tokens').order('ts', { ascending: false }).limit(100).then(({ data, error }) => {
        meta.inflight = false;
        if (!error && data) {
          meta.lastFetched = Date.now();
          const changed = JSON.stringify(state.traces) !== JSON.stringify(data);
          if (changed) {
            state.traces = data;
            triggerReRender();
          }
        }
      }).catch(() => { meta.inflight = false; });
    }
    return state.traces;
  }
  meta.inflight = true;
  const { data, error } = await db.from('llm_traces').select('id, ts, stage, topic_sn, model, latency_ms, total_tokens').order('ts', { ascending: false }).limit(100);
  meta.inflight = false;
  if (error) { toast('Failed to fetch traces', 'error'); return []; }
  meta.lastFetched = Date.now();
  state.traces = data || [];
  return state.traces;
}

export async function fetchTraceStats(force = false) {
  const now = Date.now();
  const meta = fetchMeta.traceStats;
  if (state.traceStats != null && !force) {
    if (!meta.inflight && (now - meta.lastFetched > COOLDOWN_MS)) {
      meta.inflight = true;
      db.from('llm_traces').select('id, stage, model, topic_sn, prompt_tokens, completion_tokens, total_tokens, latency_ms, ts').order('ts', { ascending: false }).then(({ data, error }) => {
        meta.inflight = false;
        if (!error && data) {
          meta.lastFetched = Date.now();
          const changed = JSON.stringify(state.traceStats) !== JSON.stringify(data);
          if (changed) {
            state.traceStats = data;
            triggerReRender();
          }
        }
      }).catch(() => { meta.inflight = false; });
    }
    return state.traceStats;
  }
  meta.inflight = true;
  const { data, error } = await db
    .from('llm_traces')
    .select('id, stage, model, topic_sn, prompt_tokens, completion_tokens, total_tokens, latency_ms, ts')
    .order('ts', { ascending: false });
  meta.inflight = false;
  if (error) { toast('Failed to fetch trace stats', 'error'); return []; }
  meta.lastFetched = Date.now();
  state.traceStats = data || [];
  return state.traceStats;
}

export async function fetchEval(topicId) {
  const { data, error } = await db.from('evaluation_results').select('*').eq('topic_id', topicId).order('created_at', { ascending: false }).limit(1);
  if (error) return null;
  return data && data.length ? data[0] : null;
}

export async function insertTopic(topic) {
  try {
    await apiPost('/api/topic', { action: 'insert', topic });
    toast('Topic added', 'success');
    return true;
  } catch (error) {
    toast(`Insert failed: ${mapSupabaseError(error)}`, 'error');
    return false;
  }
}

export async function updateTopic(id, fields) {
  try {
    await apiPost('/api/topic', { action: 'update', id, fields });
    toast('Topic updated', 'success');
    return true;
  } catch (error) {
    toast(`Update failed: ${mapSupabaseError(error)}`, 'error');
    return false;
  }
}

export async function deleteTopic(id) {
  try {
    await apiPost('/api/topic', { action: 'delete', id });
    toast('Topic removed', 'success');
    return true;
  } catch (error) {
    toast(`Delete failed: ${mapSupabaseError(error)}`, 'error');
    return false;
  }
}

export async function insertSource(src) {
  try {
    await apiPost('/api/source', { source: src });
    toast('Source added', 'success');
    return true;
  } catch (error) {
    toast(`Insert failed: ${mapSupabaseError(error)}`, 'error');
    return false;
  }
}

export async function insertJob(topicId) {
  try {
    const res = await apiPost('/api/job', {
      action: 'insert',
      table: 'curation_jobs',
      topic_id: topicId
    });
    toast('Curation job queued', 'success');
    return res.data ? res.data[0] : null;
  } catch (error) {
    toast(`Job creation failed: ${mapSupabaseError(error)}`, 'error');
    return null;
  }
}

export async function resetJob(table, jobId) {
  return apiPost('/api/job', { action: 'reset', table, job_id: jobId });
}

export async function submitReviewAction(contentId, topicId, reviewStatus, contentJson, notesValue, version) {
  return apiPost('/api/review', {
    content_id: contentId,
    topic_id: topicId,
    review_status: reviewStatus,
    content_json: contentJson,
    review_notes: notesValue,
    reviewer_id: 'human_editor',
    version: version
  });
}
