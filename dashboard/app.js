// ???????????????????????????????????????????????????????????????
// EDU-CURATOR DASHBOARD — app.js (ES6 Orchestrator)
// ???????????????????????????????????????????????????????????????

import { state, initSupabase, setViewChangeListener, navigate } from './state.js';
import { initAuth, initAuthBindings } from './auth.js';
import { renderView } from './views/index.js';
import { $, $$, esc, toast } from './utils.js';

// ?? Custom Marked Renderer Configuration ??????????????????????????
if (window.marked) {
  const renderer = new window.marked.Renderer();
  
  // Custom terminal-style renderer for block code snippets
  renderer.code = function(firstArg, secondArg) {
    let codeText = '';
    let lang = 'text';
    if (typeof firstArg === 'object' && firstArg !== null) {
      codeText = firstArg.text || '';
      lang = firstArg.lang || 'text';
    } else {
      codeText = firstArg || '';
      lang = secondArg || 'text';
    }
    const cleanCode = esc(codeText);
    const base64Code = btoa(unescape(encodeURIComponent(codeText)));
    return `
      <div class="terminal-block">
        <div class="terminal-header">
          <div class="terminal-dots">
            <span class="dot red"></span>
            <span class="dot yellow"></span>
            <span class="dot green"></span>
          </div>
          <span class="terminal-lang">${esc(lang)}</span>
          <button class="terminal-copy-btn" data-code="${base64Code}">
            <i class="ph-light ph-copy"></i>
            <span>Copy</span>
          </button>
        </div>
        <pre><code class="language-${esc(lang)}">${cleanCode}</code></pre>
      </div>
    `;
  };

  // Custom renderer for inline code snippets
  renderer.codespan = function(tokenOrText) {
    const text = typeof tokenOrText === 'object' ? tokenOrText.text : tokenOrText;
    return `<code class="inline-code">${esc(text)}</code>`;
  };

  // Custom image renderer to securely resolve media URLs
  renderer.image = function(href, title, text) {
    let url = typeof href === 'object' && href !== null ? href.href : href;
    let caption = typeof href === 'object' && href !== null ? href.text : text;
    let titleStr = typeof href === 'object' && href !== null ? href.title : title;
    
    url = url || '';
    caption = caption || '';
    
    // Resolve Supabase path
    if (url.startsWith('supabase://uploads/')) {
      const filename = url.substring('supabase://uploads/'.length);
      const supabaseUrl = window.__SUPABASE_URL__ || '';
      url = `${supabaseUrl}/storage/v1/object/public/uploads/${filename}`;
    }
    // Resolve local data path
    else if (url.startsWith('data/uploads/')) {
      url = '/' + url;
    }
    
    const cleanUrl = esc(url);
    const cleanCaption = esc(caption);
    const cleanTitle = titleStr ? ` title="${esc(titleStr)}"` : '';
    
    let html = `<img src="${cleanUrl}" alt="${cleanCaption}"${cleanTitle}>`;
    if (caption) {
      html += `\n<em>${cleanCaption}</em>`;
    }
    return html;
  };

  window.marked.use({ renderer });
  window.marked.setOptions({
    breaks: true,
    gfm: true
  });
}

// ?? Sidebar UI Updates ???????????????????????????????????????????
function moveIndicator() {
  const sidebarNav = $('#sidebar-nav');
  const indicator = $('#sidebar-indicator');
  if (!sidebarNav || !indicator) return;
  const active = $(`.sidebar-nav-item[data-view="${state.view}"]`, sidebarNav);
  if (!active) return;
  const navRect = sidebarNav.getBoundingClientRect();
  const itemRect = active.getBoundingClientRect();
  const offset = itemRect.top - navRect.top;
  indicator.style.transform = `translateY(${offset}px)`;
}

function updateSidebarUI(view) {
  const sidebarNav = $('#sidebar-nav');
  if (!sidebarNav) return;
  $$('.sidebar-nav-item', sidebarNav).forEach(item => {
    item.classList.toggle('active', item.dataset.view === view);
  });
  moveIndicator();
}

// ?? Setup View Change Observer ??????????????????????????????????
setViewChangeListener((view) => {
  updateSidebarUI(view);
  renderView();
});

// ?? Global Copy Event Delegation ????????????????????????????????
document.addEventListener('click', async (e) => {
  const btn = e.target.closest('.terminal-copy-btn');
  if (!btn) return;
  
  e.stopPropagation();
  const base64 = btn.dataset.code;
  if (!base64) return;
  
  try {
    const code = decodeURIComponent(escape(atob(base64)));
    await navigator.clipboard.writeText(code);
    
    const span = btn.querySelector('span');
    const icon = btn.querySelector('i');
    const oldText = span.textContent;
    
    span.textContent = 'Copied!';
    if (icon) {
      icon.className = 'ph-light ph-check';
    }
    btn.classList.add('copied');
    
    setTimeout(() => {
      span.textContent = oldText;
      if (icon) {
        icon.className = 'ph-light ph-copy';
      }
      btn.classList.remove('copied');
    }, 2000);
    
    toast('Code copied to clipboard', 'success');
  } catch (err) {
    console.error('Failed to copy text: ', err);
    toast('Failed to copy code', 'error');
  }
});

// ?? Outside Click Handlers ???????????????????????????????????????
document.addEventListener('click', () => {
  $$('.multi-select-dropdown.open').forEach(d => d.classList.remove('open'));
});

// ?? Kickoff App Boot & Auth ??????????????????????????????????????
const sidebarNav = $('#sidebar-nav');
if (sidebarNav) {
  $$('.sidebar-nav-item', sidebarNav).forEach(item => {
    item.addEventListener('click', () => navigate(item.dataset.view));
  });
}

initSupabase(window.__SUPABASE_URL__, window.__SUPABASE_KEY__);
initAuth();
initAuthBindings();

// ?? Sandbox Curation Simulator logic ??????????????????????????????
const SCENARIOS = {
  cicd: {
    name: 'DevOps CI/CD',
    steps: [
      {
        log: '[Ingest] Parsing 2 uploaded sources:\n  -> Source A: "DevOps Handbook 2025" (verified signature)\n  -> Source B: "Enterprise CI/CD Standard v1.2" (verified signature)',
        duration: 800
      },
      {
        log: '[Fact Mining] Extracted relevant curriculum nodes:\n  -> Topic: Continuous Integration\n  -> Source A Fact: CI is a practice of weekly commits.\n  -> Source B Fact: CI requires daily commits.',
        duration: 900
      },
      {
        log: '[Resolve Conflicts] Warning: conflicting definitions found for "commit frequency".\n  -> Resolving via Source Trust heuristics...\n  -> Source B has higher trust rating (Standard > General Handbook).\n  -> Resolved Canonical: Continuous Integration requires developers to integrate code daily.',
        duration: 1200
      },
      {
        log: '[Synthesize] Assembling markdown chapter structure...\n  -> Incorporating LaTeX equation...\n  -> Verification: Faithfulness: 9.8/10, Completeness: 9.5/10.\n  -> Compilation complete!',
        duration: 800
      }
    ],
    outcome: `
      <div class="sim-curriculum-summary">
        This chapter introduces Continuous Integration (CI) as a foundational engineering practice that drives software delivery performance and automation.
      </div>
      <div class="sim-curriculum-body">
        <p><strong>Continuous Integration (CI)</strong> is the practice of automating the integration of code changes from multiple contributors into a single software project multiple times a day. By committing code daily, developers minimize integration friction, isolate changes to locate defects rapidly, and maintain a functional main branch.</p>
        <div class="sim-curriculum-latex">
          \\[ \\text{Feedback Loop Time} = \\mathcal{O}(\\Delta t_{\\text{commit}} + \\Delta t_{\\text{build}} + \\Delta t_{\\text{test}}) \\]
        </div>
        <p>Modern CI pipelines run automated unit and integration tests upon every check-in, providing instant feedback on whether the codebase remains stable.</p>
      </div>
    `
  },
  weights: {
    name: 'NN Weights',
    steps: [
      {
        log: '[Ingest] Reading multi-source machine learning documents:\n  -> Ingesting "Deep Learning Lecture Notes 2026.pdf"\n  -> Ingesting "Backpropagation Mechanics Guide.txt"',
        duration: 800
      },
      {
        log: '[Fact Mining] Mining neural network initialization techniques...\n  -> Source A Fact: Initialize weights to small random values to break symmetry.\n  -> Source B Fact: Zero initialization is fine for deep network grids.',
        duration: 900
      },
      {
        log: '[Resolve Conflicts] Conflict detected: zero vs random distribution.\n  -> Resolving: Zero initialization causes hidden units to calculate identical gradients (symmetry issue).\n  -> Override decision: Random initialization is mathematically required.',
        duration: 1200
      },
      {
        log: '[Synthesize] Formatting LaTeX weights matrix...\n  -> Compiling textbook page with mathematical proofs.\n  -> Curation complete!',
        duration: 800
      }
    ],
    outcome: `
      <div class="sim-curriculum-summary">
        We examine the critical role of weights initialization in breaking network symmetry and allowing gradient descent to optimize neural layers.
      </div>
      <div class="sim-curriculum-body">
        <p><strong>Neural Network Weight Initialization</strong> is a fundamental step in designing deep learning systems. Initializing all weights to zero causes each neuron in a hidden layer to compute the exact same output, which results in symmetric gradients during backpropagation.</p>
        <div class="sim-curriculum-latex">
          \\[ W^{[l]}_{ij} \\sim \\mathcal{N}\\left(0, \,\\frac{2}{n^{[l-1]}}\\right) \\quad \\text{(He Initialization)} \\]
        </div>
        <p>To ensure neurons learn distinct features, weights must be initialized to small random values, often sampled from a normal distribution scaled by the input dimensionality (e.g., Xavier or He normal distributions).</p>
      </div>
    `
  },
  hnsw: {
    name: 'Vector Indices',
    steps: [
      {
        log: '[Ingest] Parsing files in "Vector Retrieval Papers/"...\n  -> Source A: "Hierarchical Navigable Small World Graphs.pdf"\n  -> Source B: "Approximation Nearest Neighbors Methods Survey.docx"',
        duration: 800
      },
      {
        log: '[Fact Mining] Extracting graph search attributes...\n  -> Source A Fact: HNSW searches scale with logarithmic complexity O(log N).\n  -> Source B Fact: HNSW establishes multi-layer graphs to achieve high-recall approximate nearest neighbor vector searches.',
        duration: 900
      },
      {
        log: '[Resolve Conflicts] Complementary sources found: combining complex graph structure and lookup performance properties.\n  -> Consolidating into canonical vector search definition.',
        duration: 1200
      },
      {
        log: '[Synthesize] Drafting vector indexing chapter...\n  -> Compiling markdown descriptions.\n  -> Ready!',
        duration: 800
      }
    ],
    outcome: `
      <div class="sim-curriculum-summary">
        Understanding Hierarchical Navigable Small World (HNSW) graphs, a state-of-the-art approximate nearest neighbors (ANN) index.
      </div>
      <div class="sim-curriculum-body">
        <p><strong>HNSW (Hierarchical Navigable Small World)</strong> is a graph-based indexing algorithm designed for high-recall approximate nearest neighbor vector searches. It organizes vector elements into a multi-layer graph, where lower layers contain detailed local links and upper layers have sparse, long-range connections.</p>
        <div class="sim-curriculum-latex">
          \\[ \\text{Average Search Complexity} = \\mathcal{O}(\\log N) \\]
        </div>
        <p>Search begins at the top layers to locate the general neighborhood, then navigates downward to execute precise local searches, achieving sub-millisecond retrieval speeds across millions of vectors.</p>
      </div>
    `
  }
};

function initSimulator() {
  const btnRunSim = document.getElementById('btn-run-sim');
  const simTerminal = document.getElementById('sim-terminal-output');
  const previewArea = document.getElementById('sim-preview-area');
  const previewContent = document.getElementById('sim-preview-content');
  const statusIndicator = document.getElementById('sim-status-indicator');
  const scenarioButtons = document.querySelectorAll('.btn-scenario');
  
  if (!btnRunSim || !simTerminal) return;
  
  let currentScenario = 'cicd';
  let isSimulating = false;
  
  // Handle Scenario Button clicks
  scenarioButtons.forEach(btn => {
    btn.addEventListener('click', (e) => {
      if (isSimulating) return;
      
      scenarioButtons.forEach(b => {
        b.classList.remove('active');
        b.setAttribute('aria-checked', 'false');
      });
      
      btn.classList.add('active');
      btn.setAttribute('aria-checked', 'true');
      currentScenario = btn.dataset.scenario;
      
      // Reset simulator states
      simTerminal.innerHTML = `<div class="terminal-line system-msg">[SYSTEM] Ready. Scenario "\${SCENARIOS[currentScenario].name}" selected.</div>`;
      previewArea.style.display = 'none';
      
      // Reset tracker states
      document.querySelectorAll('.sim-step').forEach(step => {
        step.classList.remove('active', 'completed');
      });
      
      // Reset status indicator
      statusIndicator.querySelector('.status-dot').style.backgroundColor = 'var(--text-tertiary)';
      statusIndicator.querySelector('.status-lbl').textContent = 'Idle';
    });
  });
  
  // Run simulation
  btnRunSim.addEventListener('click', async () => {
    if (isSimulating) return;
    isSimulating = true;
    btnRunSim.disabled = true;
    btnRunSim.innerHTML = `<i class="spinner-mini" aria-hidden="true"></i> Processing...`;
    
    // Set status to running
    statusIndicator.querySelector('.status-dot').style.backgroundColor = 'var(--warning)';
    statusIndicator.querySelector('.status-lbl').textContent = 'Running';
    
    // Clear display
    simTerminal.innerHTML = '';
    previewArea.style.display = 'none';
    
    const steps = SCENARIOS[currentScenario].steps;
    const trackerSteps = document.querySelectorAll('.sim-step');
    
    // Reset tracker steps
    trackerSteps.forEach(step => step.classList.remove('active', 'completed'));
    
    for (let i = 0; i < steps.length; i++) {
      const step = steps[i];
      const stepIndex = i + 1;
      
      // Mark step active in UI
      trackerSteps.forEach((st, idx) => {
        if (idx === i) {
          st.classList.add('active');
          st.classList.remove('completed');
        } else if (idx < i) {
          st.classList.add('completed');
          st.classList.remove('active');
        } else {
          st.classList.remove('active', 'completed');
        }
      });
      
      // Add log
      const logLine = document.createElement('div');
      logLine.className = 'terminal-line';
      if (step.log.startsWith('[Ingest]')) logLine.className = 'info-msg';
      else if (step.log.startsWith('[Fact Mining]')) logLine.className = 'info-msg';
      else if (step.log.startsWith('[Resolve Conflicts]')) logLine.classList.add('warn-msg');
      else if (step.log.startsWith('[Synthesize]')) logLine.classList.add('success-msg');
      
      logLine.textContent = step.log;
      simTerminal.appendChild(logLine);
      simTerminal.scrollTop = simTerminal.scrollHeight;
      
      await new Promise(resolve => setTimeout(resolve, step.duration));
    }
    
    // Complete last step
    trackerSteps.forEach(st => {
      st.classList.remove('active');
      st.classList.add('completed');
    });
    
    // Set status to completed
    statusIndicator.querySelector('.status-dot').style.backgroundColor = 'var(--success)';
    statusIndicator.querySelector('.status-lbl').textContent = 'Success';
    
    // Render outcome textbook page
    previewContent.innerHTML = SCENARIOS[currentScenario].outcome;
    previewArea.style.display = 'block';
    
    // Render mathematical formulas in outcome using KaTeX
    if (window.renderMathInElement) {
      window.renderMathInElement(previewContent, {
        delimiters: [
          { left: '$$', right: '$$', display: true },
          { left: '\\(', right: '\\)', display: false },
          { left: '\\[', right: '\\]', display: true },
          { left: '\\\\(', right: '\\\\)', display: false }
        ],
        throwOnError: false
      });
    }
    
    isSimulating = false;
    btnRunSim.disabled = false;
    btnRunSim.innerHTML = `<i class="ph-light ph-play-circle" aria-hidden="true"></i> Run Simulation`;
  });
}

// Boot simulator when DOM loads
document.addEventListener('DOMContentLoaded', () => {
  initSimulator();
});
