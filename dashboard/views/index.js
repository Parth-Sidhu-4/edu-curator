// ═══════════════════════════════════════════════════════════════
// views/index.js
// ═══════════════════════════════════════════════════════════════

import { state, setReRenderListener } from '../state.js';
import { renderOverview } from './overview.js';
import { renderContent } from './content.js';
import { renderTopics } from './topics.js';
import { renderSources } from './sources.js';
import { renderObservability } from './observability.js';
import { renderEvaluation } from './evaluation.js';
import { $, applyCustomSelects, stagger, renderMath } from '../utils.js';

let lastRenderedView = null;

function hasCacheForView(view) {
  switch (view) {
    case 'overview':
      return state.topics && state.topics.length > 0 && state.sources && state.sources.length > 0;
    case 'content':
      return state.topics && state.topics.length > 0 && state.content && state.content.length > 0;
    case 'topics':
      return state.topics && state.topics.length > 0;
    case 'sources':
      return state.sources && state.sources.length > 0;
    case 'observability':
      return state.traces && state.traces.length > 0;
    case 'evaluation':
      return state.topics && state.topics.length > 0;
    default:
      return false;
  }
}

export async function renderView(forceLoading = false) {
  const mainContent = $('#main-content');
  if (!mainContent) return;

  const isNewView = state.view !== lastRenderedView;
  lastRenderedView = state.view;

  if (forceLoading || !hasCacheForView(state.view)) {
    mainContent.innerHTML = '<p class="loading-text">Loading...</p>';
  }
  
  switch (state.view) {
    case 'overview':      await renderOverview(); break;
    case 'content':       await renderContent(); break;
    case 'topics':        await renderTopics(); break;
    case 'sources':       await renderSources(); break;
    case 'observability': await renderObservability(); break;
    case 'evaluation':    await renderEvaluation(); break;
  }
  applyCustomSelects(mainContent);
  
  if (isNewView) {
    stagger(mainContent);
  } else {
    mainContent.classList.remove('view-entering');
  }
  
  renderMath(mainContent);
}

// Register background re-render handler
setReRenderListener(() => {
  // Do not re-render silently if user is actively interacting with an input/form
  const active = document.activeElement;
  if (active && (
    active.tagName === 'INPUT' || 
    active.tagName === 'TEXTAREA' || 
    active.tagName === 'SELECT' || 
    active.closest('.edit-curriculum-field')
  )) {
    return;
  }
  renderView(false);
});
