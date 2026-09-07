// FactLens Web Application Controller
document.addEventListener('DOMContentLoaded', () => {
  let appState = {
    activeTab: 'showcase',
    documents: [],
    facts: [],
    comparisons: [],
    failures: [],
    showcaseCases: [],
    currentDatasetFilter: 'all',
    currentRelFilter: 'all'
  };

  // --- Element Selectors ---
  const navTabs = document.querySelectorAll('.nav-tab');
  const tabPanes = document.querySelectorAll('.tab-pane');
  
  const engineStatusPill = document.getElementById('engineStatusPill');
  const engineStatusText = document.getElementById('engineStatusText');
  const cacheStatusPill = document.getElementById('cacheStatusPill');
  const cacheStatusText = document.getElementById('cacheStatusText');
  const btnSettings = document.getElementById('btnSettings');
  const settingsModal = document.getElementById('settingsModal');
  const btnCloseSettings = document.getElementById('btnCloseSettings');
  const btnCancelSettings = document.getElementById('btnCancelSettings');
  const btnSaveSettings = document.getElementById('btnSaveSettings');
  const inputApiKey = document.getElementById('inputApiKey');

  const evidenceModal = document.getElementById('evidenceModal');
  const btnCloseEvidence = document.getElementById('btnCloseEvidence');
  const evidenceModalTitle = document.getElementById('evidenceModalTitle');
  const evidenceModalBody = document.getElementById('evidenceModalBody');

  const docCount = document.getElementById('docCount');
  const factCount = document.getElementById('factCount');
  const cmpCount = document.getElementById('cmpCount');
  const failCount = document.getElementById('failCount');

  const showcaseList = document.getElementById('showcaseList');
  const dropZone = document.getElementById('dropZone');
  const fileInput = document.getElementById('fileInput');
  const docTableBody = document.getElementById('docTableBody');
  const btnRunPipeline = document.getElementById('btnRunPipeline');
  const jobStatusBanner = document.getElementById('jobStatusBanner');
  const jobSpinner = document.getElementById('jobSpinner');
  const jobBannerText = document.getElementById('jobBannerText');
  const jobProgressBar = document.getElementById('jobProgressBar');
  const duplicateAlertBanner = document.getElementById('duplicateAlertBanner');
  const duplicateAlertText = document.getElementById('duplicateAlertText');

  const factsList = document.getElementById('factsList');
  const factSearchInput = document.getElementById('factSearchInput');
  const factEntityFilter = document.getElementById('factEntityFilter');
  const factMetricFilter = document.getElementById('factMetricFilter');
  const btnResetFactFilters = document.getElementById('btnResetFactFilters');

  const comparisonsList = document.getElementById('comparisonsList');
  const failuresList = document.getElementById('failuresList');

  // --- Tab Navigation ---
  navTabs.forEach(tab => {
    tab.addEventListener('click', () => {
      const targetTab = tab.dataset.tab;
      switchTab(targetTab);
    });
  });

  function switchTab(tabId) {
    appState.activeTab = tabId;
    navTabs.forEach(t => t.classList.toggle('active', t.dataset.tab === tabId));
    tabPanes.forEach(p => p.classList.toggle('active', p.id === `pane-${tabId}`));
  }

  // --- API Health & Initial Load ---
  async function checkHealth() {
    try {
      const res = await fetch('/api/health');
      const data = await res.json();
      if (data.has_gemini_key) {
        engineStatusText.textContent = 'Gemini 2.5 Live Mode';
        engineStatusPill.querySelector('.status-dot').style.backgroundColor = '#6366f1';
      } else {
        engineStatusText.textContent = 'Offline Deterministic Mode';
        engineStatusPill.querySelector('.status-dot').style.backgroundColor = '#10b981';
      }

      if (cacheStatusPill && cacheStatusText) {
        if (data.redis_connected) {
          cacheStatusText.textContent = 'Redis: Connected';
          cacheStatusPill.querySelector('.status-dot').style.backgroundColor = '#10b981';
        } else {
          cacheStatusText.textContent = 'Cache: In-Memory Safe Fallback';
          cacheStatusPill.querySelector('.status-dot').style.backgroundColor = '#f59e0b';
        }
      }
    } catch (e) {
      engineStatusText.textContent = 'Connection Error';
      engineStatusPill.querySelector('.status-dot').style.backgroundColor = '#ef4444';
      if (cacheStatusText) cacheStatusText.textContent = 'Cache Offline';
    }
  }

  async function loadAllData() {
    await checkHealth();
    
    // Seed starter cases if needed
    try {
      await fetch('/api/seed_starter_cases', { method: 'POST' });
    } catch (e) {
      console.warn('Seed starter cases error:', e);
    }

    await Promise.all([
      loadShowcaseCases(),
      loadDocuments(),
      loadFacts(),
      loadComparisons(),
      loadFailures()
    ]);
  }

  // --- Showcase Cases ---
  async function loadShowcaseCases() {
    try {
      const res = await fetch('/api/cases');
      appState.showcaseCases = await res.json();
      renderShowcase();
    } catch (e) {
      showcaseList.innerHTML = `<p class="text-secondary">Failed to load showcase cases: ${e.message}</p>`;
    }
  }

  function renderShowcase() {
    const filtered = appState.showcaseCases.filter(c => {
      if (appState.currentDatasetFilter === 'all') return true;
      return c.dataset === appState.currentDatasetFilter;
    });

    if (filtered.length === 0) {
      showcaseList.innerHTML = `<p class="text-secondary">No showcase cases found.</p>`;
      return;
    }

    showcaseList.innerHTML = filtered.map(c => {
      const badgeClass = getCategoryBadgeClass(c.case_category);
      const datasetBadge = c.dataset === 'delhivery' ? 'Delhivery Dataset' : 'India Macroeconomy';

      let comparisonHtml = '';
      if (c.comparison) {
        const cmp = c.comparison;
        comparisonHtml = `
          <div class="compare-box">
            <div class="compare-fact">
              <span class="compare-doc-title" title="${cmp.fact_a.document_name}">${cmp.fact_a.document_name} (p.${cmp.fact_a.page_number})</span>
              <span class="compare-val">${cmp.fact_a.value_raw}</span>
              <span class="compare-quote">"${escapeHtml(cmp.fact_a.evidence_text)}"</span>
            </div>
            <div class="compare-fact">
              <span class="compare-doc-title" title="${cmp.fact_b.document_name}">${cmp.fact_b.document_name} (p.${cmp.fact_b.page_number})</span>
              <span class="compare-val">${cmp.fact_b.value_raw}</span>
              <span class="compare-quote">"${escapeHtml(cmp.fact_b.evidence_text)}"</span>
            </div>
          </div>
          <div class="compare-explanation">
            <strong>System Reasoning:</strong> ${escapeHtml(cmp.explanation)}
          </div>
        `;
      } else if (c.failure) {
        const fail = c.failure;
        comparisonHtml = `
          <div class="failure-raw">
            Snippet: "${escapeHtml(fail.raw_snippet)}"
          </div>
          <div class="compare-explanation" style="border-color: rgba(168, 85, 247, 0.3); background: rgba(168, 85, 247, 0.08);">
            <strong>Reasoning & Safeguard:</strong> ${escapeHtml(fail.explanation)}
          </div>
        `;
      }

      return `
        <div class="showcase-card">
          <div class="showcase-card-header">
            <div class="showcase-badge-container">
              <span class="badge ${badgeClass}">${formatCategory(c.case_category)}</span>
              <span class="badge badge-dataset">${datasetBadge}</span>
            </div>
          </div>
          <h3 class="showcase-title">${escapeHtml(c.title)}</h3>
          <p class="showcase-desc">${escapeHtml(c.description)}</p>
          ${comparisonHtml}
          <div class="compare-why">
            <strong>Significance:</strong> ${escapeHtml(c.why_it_matters)}
          </div>
        </div>
      `;
    }).join('');
  }

  // Dataset filter buttons on showcase pane
  document.querySelectorAll('#pane-showcase .filter-group button').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('#pane-showcase .filter-group button').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      appState.currentDatasetFilter = btn.dataset.dataset;
      renderShowcase();
    });
  });

  // --- Document Upload & List ---
  async function loadDocuments() {
    try {
      const res = await fetch('/api/documents');
      appState.documents = await res.json();
      docCount.textContent = appState.documents.length;
      renderDocTable();
    } catch (e) {
      console.error('Failed to load documents:', e);
    }
  }

  function getScanBadge(status, result) {
    const title = result ? `title="${escapeHtml(result)}"` : '';
    if (status === 'clean') {
      return `<span class="badge badge-corroboration" ${title}>🛡️ Clean</span>`;
    } else if (status === 'mock_scanned') {
      return `<span class="badge badge-contextual" ${title}>🛡️ Dev Mock</span>`;
    } else if (status === 'infected') {
      return `<span class="badge badge-contradiction" ${title}>☣️ Infected</span>`;
    } else {
      return `<span class="badge badge-dataset" ${title}>${escapeHtml(status || 'pending')}</span>`;
    }
  }

  function renderDocTable() {
    if (appState.documents.length === 0) {
      docTableBody.innerHTML = `<tr><td colspan="6" style="text-align:center; color: var(--text-muted);">No documents uploaded yet. Drag and drop PDFs above to start.</td></tr>`;
      return;
    }

    docTableBody.innerHTML = appState.documents.map(d => `
      <tr>
        <td><strong>${escapeHtml(d.original_name)}</strong></td>
        <td><span class="page-tag">${d.page_count} pages</span></td>
        <td>${(d.file_size_bytes / (1024*1024)).toFixed(2)} MB</td>
        <td><code style="font-size:0.75rem; color: var(--text-muted);" title="${d.sha256_hash}">${d.sha256_hash.slice(0, 16)}...</code></td>
        <td>${getScanBadge(d.scan_status, d.scan_result)}</td>
        <td><span class="badge ${d.status === 'processed' ? 'badge-corroboration' : (d.status === 'queued' ? 'badge-dataset' : 'badge-contextual')}">${d.status}</span></td>
      </tr>
    `).join('');
  }

  // Upload dropzone interactions
  dropZone.addEventListener('click', () => fileInput.click());
  dropZone.addEventListener('dragover', (e) => { e.preventDefault(); dropZone.classList.add('dragover'); });
  dropZone.addEventListener('dragleave', () => dropZone.classList.remove('dragover'));
  dropZone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropZone.classList.remove('dragover');
    if (e.dataTransfer.files.length) handleFilesUpload(e.dataTransfer.files);
  });
  fileInput.addEventListener('change', () => {
    if (fileInput.files.length) handleFilesUpload(fileInput.files);
  });

  async function handleFilesUpload(files) {
    const formData = new FormData();
    for (let f of files) {
      formData.append('files', f);
    }

    dropZone.querySelector('.dropzone-title').textContent = 'Validating and uploading securely...';
    try {
      const res = await fetch('/api/upload', {
        method: 'POST',
        body: formData
      });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || 'Upload failed');
      }
      const uploadItems = await res.json();
      await loadDocuments();

      let hasActiveJobs = false;
      let hasDuplicates = false;

      for (const item of uploadItems) {
        if (item.is_duplicate) {
          hasDuplicates = true;
          if (duplicateAlertBanner && duplicateAlertText) {
            duplicateAlertText.textContent = item.message;
            duplicateAlertBanner.style.display = 'flex';
            setTimeout(() => { duplicateAlertBanner.style.display = 'none'; }, 7000);
          }
        }
        if (item.job_id && !item.is_duplicate) {
          hasActiveJobs = true;
          pollJobProgress(item.job_id);
        }
      }

      if (!hasActiveJobs && !hasDuplicates) {
        await loadAllData();
      }

      dropZone.querySelector('.dropzone-title').innerHTML = `Upload received! Drag more, or <span class="text-accent">browse</span>`;
    } catch (e) {
      alert(`Upload rejected: ${e.message}`);
      dropZone.querySelector('.dropzone-title').innerHTML = `Drag & drop PDF documents here, or <span class="text-accent">browse</span>`;
    }
  }

  function pollJobProgress(jobId) {
    if (!jobStatusBanner) return;
    jobStatusBanner.style.display = 'flex';
    jobStatusBanner.className = 'alert-banner alert-info';
    jobSpinner.style.display = 'block';
    jobBannerText.textContent = `Job ${jobId}: Processing document in background...`;
    jobProgressBar.style.width = '15%';

    const pollTimer = setInterval(async () => {
      try {
        const res = await fetch(`/api/jobs/${jobId}`);
        if (!res.ok) return;
        const job = await res.json();

        const pct = Math.round((job.progress || 0) * 100);
        jobProgressBar.style.width = `${Math.max(15, pct)}%`;

        if (job.status === 'completed') {
          clearInterval(pollTimer);
          jobStatusBanner.className = 'alert-banner alert-success';
          jobSpinner.style.display = 'none';
          jobProgressBar.style.width = '100%';
          jobBannerText.textContent = `Document processing complete! Facts and reconciliation updated.`;
          await loadAllData();
          setTimeout(() => { jobStatusBanner.style.display = 'none'; }, 4000);
        } else if (job.status === 'failed') {
          clearInterval(pollTimer);
          jobStatusBanner.className = 'alert-banner alert-warning';
          jobSpinner.style.display = 'none';
          jobBannerText.textContent = `Processing failed: ${job.error_message || 'Unknown error'}`;
          await loadDocuments();
        } else if (job.retry_count > 0) {
          jobBannerText.textContent = `Job ${jobId}: Retrying (attempt ${job.retry_count}/${job.max_retries})...`;
        }
      } catch (e) {
        console.warn('Error checking job:', e);
      }
    }, 1000);
  }

  // Run Pipeline
  btnRunPipeline.addEventListener('click', async () => {
    btnRunPipeline.disabled = true;
    btnRunPipeline.innerHTML = `<span>Processing Pipeline...</span>`;
    try {
      const res = await fetch('/api/process', { method: 'POST' });
      const data = await res.json();
      alert(`Pipeline Complete!\nDocuments: ${data.processed_documents}\nFacts Extracted: ${data.facts_extracted}\nComparisons: ${data.comparisons_found}\nFailures Logged: ${data.failures_recorded}`);
      await loadAllData();
      switchTab('facts');
    } catch (e) {
      alert(`Processing error: ${e.message}`);
    } finally {
      btnRunPipeline.disabled = false;
      btnRunPipeline.innerHTML = `
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <polygon points="5 3 19 12 5 21 5 3"></polygon>
        </svg>
        <span>Extract & Reconcile All</span>
      `;
    }
  });

  // --- Facts Matrix ---
  async function loadFacts() {
    try {
      const res = await fetch('/api/facts');
      appState.facts = await res.json();
      factCount.textContent = appState.facts.length;
      populateFactFilters();
      renderFacts();
    } catch (e) {
      console.error('Failed to load facts:', e);
    }
  }

  function populateFactFilters() {
    const entities = [...new Set(appState.facts.map(f => f.entity))].sort();
    const metrics = [...new Set(appState.facts.map(f => f.metric))].sort();

    factEntityFilter.innerHTML = `<option value="">All Entities (${entities.length})</option>` +
      entities.map(e => `<option value="${escapeHtml(e)}">${escapeHtml(e)}</option>`).join('');

    factMetricFilter.innerHTML = `<option value="">All Metrics (${metrics.length})</option>` +
      metrics.map(m => `<option value="${escapeHtml(m)}">${escapeHtml(m)}</option>`).join('');
  }

  function renderFacts() {
    const search = factSearchInput.value.toLowerCase().trim();
    const entFilter = factEntityFilter.value;
    const metFilter = factMetricFilter.value;

    const filtered = appState.facts.filter(f => {
      if (entFilter && f.entity !== entFilter) return false;
      if (metFilter && f.metric !== metFilter) return false;
      if (search) {
        const text = `${f.entity} ${f.metric} ${f.value_raw} ${f.evidence_text} ${f.period}`.toLowerCase();
        if (!text.includes(search)) return false;
      }
      return true;
    });

    if (filtered.length === 0) {
      factsList.innerHTML = `<p class="text-secondary" style="grid-column: 1/-1;">No matching facts found.</p>`;
      return;
    }

    factsList.innerHTML = filtered.map(f => `
      <div class="fact-card" data-fact-id="${f.id}">
        <div class="fact-card-top">
          <span class="fact-entity">${escapeHtml(f.entity)}</span>
          <span class="page-tag">p.${f.page_number}</span>
        </div>
        <div class="fact-metric">${escapeHtml(f.metric)}</div>
        <div class="fact-val">${escapeHtml(f.value_raw)}</div>
        <div class="fact-period">${f.period ? escapeHtml(f.period) : 'Scope: ' + (f.scope || 'Standard')}</div>
        <div class="fact-quote-preview">"${escapeHtml(f.evidence_text)}"</div>
      </div>
    `).join('');

    // Attach click for evidence modal
    document.querySelectorAll('.fact-card').forEach(card => {
      card.addEventListener('click', () => {
        const fact = appState.facts.find(f => f.id === card.dataset.factId);
        if (fact) openEvidenceModal(fact);
      });
    });
  }

  factSearchInput.addEventListener('input', renderFacts);
  factEntityFilter.addEventListener('change', renderFacts);
  factMetricFilter.addEventListener('change', renderFacts);
  btnResetFactFilters.addEventListener('click', () => {
    factSearchInput.value = '';
    factEntityFilter.value = '';
    factMetricFilter.value = '';
    renderFacts();
  });

  function openEvidenceModal(fact) {
    evidenceModalTitle.textContent = `${fact.entity} — ${fact.metric}`;
    evidenceModalBody.innerHTML = `
      <div style="display: flex; flex-direction: column; gap: 1rem;">
        <div style="display: flex; gap: 0.75rem; align-items: center; flex-wrap: wrap;">
          <span class="badge badge-dataset">${escapeHtml(fact.document_name)}</span>
          <span class="page-tag">Page ${fact.page_number}</span>
          <span class="badge badge-corroboration">Confidence: ${(fact.confidence * 100).toFixed(0)}%</span>
          <span class="badge badge-dataset">Method: ${fact.extraction_method}</span>
        </div>
        
        <div>
          <h4 style="font-size: 0.85rem; color: var(--text-secondary); margin-bottom: 0.35rem;">Extracted Value</h4>
          <div style="font-family: var(--font-mono); font-size: 1.5rem; font-weight: 700; color: #fff;">
            ${escapeHtml(fact.value_raw)}
            ${fact.value_numeric !== null ? `<span style="font-size:0.9rem; color: var(--text-secondary); font-weight: 400;">(Canonical: ${fact.value_numeric.toLocaleString()} ${fact.unit || ''})</span>` : ''}
          </div>
        </div>

        <div>
          <h4 style="font-size: 0.85rem; color: var(--text-secondary); margin-bottom: 0.35rem;">Exact Grounded Evidence Quote</h4>
          <div style="background: var(--bg-base); padding: 0.85rem; border-radius: var(--radius-sm); border-left: 3px solid var(--accent); font-style: italic; color: #e2e8f0;">
            "${escapeHtml(fact.evidence_text)}"
          </div>
        </div>

        ${fact.evidence_context ? `
          <div>
            <h4 style="font-size: 0.85rem; color: var(--text-secondary); margin-bottom: 0.35rem;">Surrounding Page Context</h4>
            <div style="background: var(--bg-base); padding: 0.85rem; border-radius: var(--radius-sm); font-size: 0.82rem; color: var(--text-muted); line-height: 1.5;">
              ${escapeHtml(fact.evidence_context)}
            </div>
          </div>
        ` : ''}

        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 0.75rem; font-size: 0.82rem; background: var(--bg-base); padding: 0.75rem; border-radius: var(--radius-sm);">
          <div><span style="color: var(--text-secondary);">Temporal Period:</span> ${fact.period || 'Not specified'}</div>
          <div><span style="color: var(--text-secondary);">As-Of Date:</span> ${fact.as_of_date || 'N/A'}</div>
          <div><span style="color: var(--text-secondary);">Period Start:</span> ${fact.period_start || 'N/A'}</div>
          <div><span style="color: var(--text-secondary);">Period End:</span> ${fact.period_end || 'N/A'}</div>
        </div>
      </div>
    `;
    evidenceModal.classList.add('open');
  }

  // --- Comparisons View ---
  async function loadComparisons() {
    try {
      const res = await fetch('/api/comparisons');
      appState.comparisons = await res.json();
      cmpCount.textContent = appState.comparisons.length;
      renderComparisons();
    } catch (e) {
      console.error('Failed to load comparisons:', e);
    }
  }

  function renderComparisons() {
    const filtered = appState.comparisons.filter(c => {
      if (appState.currentRelFilter === 'all') return true;
      return c.relationship === appState.currentRelFilter;
    });

    if (filtered.length === 0) {
      comparisonsList.innerHTML = `<p class="text-secondary">No comparisons found for the selected filter.</p>`;
      return;
    }

    comparisonsList.innerHTML = filtered.map(c => {
      const badgeClass = getCategoryBadgeClass(c.relationship);
      return `
        <div class="comparison-card">
          <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 0.5rem;">
            <div style="display: flex; gap: 0.5rem; align-items: center;">
              <span class="badge ${badgeClass}">${formatCategory(c.relationship)}</span>
              ${c.difference_type !== 'none' ? `<span class="badge badge-dataset">Difference: ${c.difference_type.toUpperCase()}</span>` : ''}
              <span class="badge badge-dataset">Confidence: ${(c.confidence * 100).toFixed(0)}%</span>
            </div>
            <span style="font-size: 0.85rem; font-weight: 600; color: var(--accent-cyan);">${escapeHtml(c.fact_a.entity)} — ${escapeHtml(c.fact_a.metric)}</span>
          </div>

          <div class="compare-box">
            <div class="compare-fact">
              <span class="compare-doc-title" title="${c.fact_a.document_name}">${escapeHtml(c.fact_a.document_name)} (p.${c.fact_a.page_number})</span>
              <span class="compare-val">${escapeHtml(c.fact_a.value_raw)}</span>
              <span class="compare-quote">"${escapeHtml(c.fact_a.evidence_text)}"</span>
            </div>
            <div class="compare-fact">
              <span class="compare-doc-title" title="${c.fact_b.document_name}">${escapeHtml(c.fact_b.document_name)} (p.${c.fact_b.page_number})</span>
              <span class="compare-val">${escapeHtml(c.fact_b.value_raw)}</span>
              <span class="compare-quote">"${escapeHtml(c.fact_b.evidence_text)}"</span>
            </div>
          </div>

          <div class="compare-explanation">
            <strong>Reconciliation Reasoning:</strong> ${escapeHtml(c.explanation)}
          </div>
        </div>
      `;
    }).join('');
  }

  // Relationship filter buttons
  document.querySelectorAll('#pane-comparisons .filter-group button').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('#pane-comparisons .filter-group button').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      appState.currentRelFilter = btn.dataset.rel;
      renderComparisons();
    });
  });

  // --- Failures View ---
  async function loadFailures() {
    try {
      const res = await fetch('/api/failures');
      appState.failures = await res.json();
      failCount.textContent = appState.failures.length;
      renderFailures();
    } catch (e) {
      console.error('Failed to load failures:', e);
    }
  }

  function renderFailures() {
    if (appState.failures.length === 0) {
      failuresList.innerHTML = `<p class="text-secondary">No extraction failures or ungrounded claims recorded.</p>`;
      return;
    }

    failuresList.innerHTML = appState.failures.map(f => `
      <div class="failure-card">
        <div style="display: flex; justify-content: space-between; align-items: center;">
          <span class="badge badge-failure">${escapeHtml(f.failure_type.toUpperCase())}</span>
          <span style="font-size: 0.78rem; color: var(--text-muted);">${escapeHtml(f.document_name)} (p.${f.page_number})</span>
        </div>
        ${f.raw_snippet ? `<div class="failure-raw">Snippet: "${escapeHtml(f.raw_snippet)}"</div>` : ''}
        <div class="failure-expl"><strong>Handling / Safeguard:</strong> ${escapeHtml(f.explanation)}</div>
      </div>
    `).join('');
  }

  // --- Settings Modal Handling ---
  btnSettings.addEventListener('click', () => settingsModal.classList.add('open'));
  btnCloseSettings.addEventListener('click', () => settingsModal.classList.remove('open'));
  btnCancelSettings.addEventListener('click', () => settingsModal.classList.remove('open'));
  btnSaveSettings.addEventListener('click', async () => {
    const key = inputApiKey.value.trim();
    try {
      const res = await fetch('/api/settings/api_key', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ api_key: key })
      });
      const data = await res.json();
      settingsModal.classList.remove('open');
      await checkHealth();
      alert(`Settings updated: Engine running in ${data.llm_mode}`);
    } catch (e) {
      alert(`Failed to save settings: ${e.message}`);
    }
  });

  btnCloseEvidence.addEventListener('click', () => evidenceModal.classList.remove('open'));
  window.addEventListener('click', (e) => {
    if (e.target === settingsModal) settingsModal.classList.remove('open');
    if (e.target === evidenceModal) evidenceModal.classList.remove('open');
  });

  // --- Helpers ---
  function getCategoryBadgeClass(cat) {
    if (cat === 'corroboration') return 'badge-corroboration';
    if (cat === 'genuine_contradiction') return 'badge-contradiction';
    if (cat === 'contextual_difference') return 'badge-context';
    return 'badge-failure';
  }

  function formatCategory(cat) {
    return cat.replace('_', ' ');
  }

  function escapeHtml(str) {
    if (!str) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  // Initial Load
  loadAllData();
});
