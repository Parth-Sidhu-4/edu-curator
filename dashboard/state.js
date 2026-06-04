// ═══════════════════════════════════════════════════════════════
// state.js
// ═══════════════════════════════════════════════════════════════

export let db = null;
export let currentUser = null;

export const state = {
  view: 'overview',
  topicsSubView: 'add',
  sourcesSubView: 'add',
  selectedTopicId: null,
  selectedEditTopicId: null,
  selectedRemoveTopicId: null,
  selectedEvalTopicId: null,
  expandedTraceId: null,
  sourceMode: 'url',
  selectedSourceTopicIds: new Set(),
  selectedFile: null,
  // Cache
  topics: [],
  sources: [],
  content: [],
  jobs: [],
  traces: [],
  evalData: null,
};

let viewChangeListener = null;
let reRenderListener = null;

export function initSupabase(url, key) {
  try {
    db = window.supabase.createClient(url, key);
  } catch (e) {
    console.error('Failed to initialize Supabase client:', e);
  }
}

export function setCurrentUser(user) {
  currentUser = user;
}

export function setViewChangeListener(listener) {
  viewChangeListener = listener;
}

export function setReRenderListener(listener) {
  reRenderListener = listener;
}

export function triggerReRender() {
  if (reRenderListener) {
    reRenderListener();
  }
}

export function navigate(view) {
  state.view = view;
  if (state._jobPollTimer) {
    clearInterval(state._jobPollTimer);
    state._jobPollTimer = null;
  }
  if (state._evalJobPollTimer) {
    clearInterval(state._evalJobPollTimer);
    state._evalJobPollTimer = null;
  }
  if (state._sourceIngestTimer) {
    clearInterval(state._sourceIngestTimer);
    state._sourceIngestTimer = null;
  }
  state.selectedFile = null;
  if (viewChangeListener) {
    viewChangeListener(view);
  }
}

// ── RISK CATEGORIES ───────────────────────────────────────────────

export const RISK_LABELS = {
  1: '⚠️ [Conflict]',
  2: '🔍 [Review <75%]',
  3: '📄 [Single Source]',
  4: '⚡ [Med Conf]',
  5: '✅ [High Conf]',
  6: '💤 [No Knowledge]'
};

export function getTopicRiskCategory(topic, knowledgeRecord) {
  if (!knowledgeRecord) {
    return 6;
  }
  const knowledge = typeof knowledgeRecord.knowledge === 'string'
    ? JSON.parse(knowledgeRecord.knowledge)
    : knowledgeRecord.knowledge;

  const confidence = knowledgeRecord.confidence != null ? Number(knowledgeRecord.confidence) : null;
  const sourcesUsed = Array.isArray(knowledgeRecord.sources_used) ? knowledgeRecord.sources_used : [];

  let hasConflict = false;
  let hasNeedsReview = false;
  let hasLowConfidenceField = false;

  if (knowledge) {
    Object.values(knowledge).forEach(field => {
      if (field && typeof field === 'object' && !Array.isArray(field) && 'canonical_value' in field) {
        if (field.status === 'conflict_detected') {
          hasConflict = true;
        }
        if (field.status === 'needs_review') {
          hasNeedsReview = true;
        }
        if (field.confidence != null && field.confidence < 75) {
          hasLowConfidenceField = true;
        }
      }
    });
  }

  if (hasConflict) {
    return 1;
  }
  if (hasNeedsReview || (confidence != null && confidence < 75) || hasLowConfidenceField) {
    return 2;
  }
  if (sourcesUsed.length === 1) {
    return 3;
  }
  if (confidence != null && confidence >= 75 && confidence < 90) {
    return 4;
  }
  if (confidence != null && confidence >= 90) {
    return 5;
  }
  return 6;
}
