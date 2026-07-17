(() => {
  'use strict';

  const PAGE_SIZE = 25;
  const FILTER_NAMES = [
    'formula', 'functional', 'tags', 'bandgap_min', 'lattice_max',
    'min_energy', 'max_energy', 'converged_only', 'provenance'
  ];
  const state = {
    filters: {},
    offset: 0,
    hasMore: false,
    overview: null,
    lastHash: null,
    requestId: 0,
    detailRequestId: 0,
    closeTimer: null,
    previousFocus: null,
  };

  const $ = (selector) => document.querySelector(selector);
  const els = {
    status: $('#status-region'),
    metrics: $('#metrics'),
    families: $('#formula-families'),
    signals: $('#quality-signals'),
    filters: $('#filters'),
    catalogState: $('#catalog-state'),
    catalogBody: $('#catalog-body'),
    catalogCount: $('#catalog-count'),
    previous: $('#previous-page'),
    next: $('#next-page'),
    pageStatus: $('#page-status'),
    clear: $('#clear-filters'),
    drawer: $('#detail-drawer'),
    backdrop: $('#drawer-backdrop'),
    drawerTitle: $('#drawer-title'),
    drawerContent: $('#drawer-content'),
    closeDrawer: $('#close-drawer'),
    lastRead: $('#last-read'),
  };

  const esc = (value) => String(value ?? '—')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');

  const display = (value, fallback = '—') => (
    value === null || value === undefined || value === '' ? fallback : String(value)
  );
  const number = (value, digits = 4) => {
    if (value === null || value === undefined || value === '' || Number.isNaN(Number(value))) return '—';
    return Number(value).toLocaleString(undefined, { maximumFractionDigits: digits });
  };
  const count = (value) => Number(value || 0).toLocaleString();
  const date = (value) => {
    if (!value) return '—';
    const parsed = new Date(Number(value) * 1000);
    return Number.isNaN(parsed.getTime()) ? display(value) : parsed.toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' });
  };
  const percent = (part, whole) => whole ? `${Math.round((Number(part || 0) / Number(whole)) * 100)}%` : '0%';

  function parseUrlState() {
    const params = new URLSearchParams(window.location.search);
    state.filters = {};
    FILTER_NAMES.forEach((name) => {
      const value = params.get(name);
      if (value !== null && value !== '') state.filters[name] = value;
    });
    if (!state.filters.provenance) state.filters.provenance = 'canonical';
    const offset = Number.parseInt(params.get('offset') || '0', 10);
    state.offset = Number.isFinite(offset) && offset >= 0 ? offset : 0;
  }

  function writeUrlState() {
    const params = new URLSearchParams();
    Object.entries(state.filters).forEach(([name, value]) => {
      if (value !== null && value !== undefined && value !== '') params.set(name, value);
    });
    if (state.offset) params.set('offset', String(state.offset));
    const query = params.toString();
    window.history.replaceState({}, '', `${window.location.pathname}${query ? `?${query}` : ''}`);
  }

  function syncControls() {
    FILTER_NAMES.forEach((name) => {
      const input = els.filters.elements.namedItem(name);
      if (input) input.value = state.filters[name] || '';
    });
  }

  function readFilterControls() {
    state.filters = {};
    FILTER_NAMES.forEach((name) => {
      const input = els.filters.elements.namedItem(name);
      const value = input ? input.value.trim() : '';
      if (value) state.filters[name] = value;
    });
    if (!state.filters.provenance) state.filters.provenance = 'canonical';
  }

  function setStatus(message, tone = 'neutral') {
    els.status.innerHTML = message ? `<div class="status status--${esc(tone)}"><span class="status__mark" aria-hidden="true">${tone === 'error' ? '!' : 'i'}</span><span>${esc(message)}</span></div>` : '';
  }

  function renderMetrics(data) {
    const entries = Number(data.entries || 0);
    const metrics = [
      { label: 'entries', value: count(data.entries), note: 'stored metadata records' },
      { label: 'formulas', value: count(data.formulas), note: 'distinct families' },
      { label: 'energy coverage', value: percent(data.with_energy, entries), note: `${count(data.with_energy)} with energy` },
      { label: 'convergence coverage', value: percent(data.converged, entries), note: `${count(data.converged)} marked converged` },
    ];
    els.metrics.innerHTML = metrics.map((metric, index) => `
      <article class="metric" style="--metric-delay:${index * 70}ms">
        <p class="metric__label">${esc(metric.label)}</p>
        <p class="metric__value mono">${esc(metric.value)}</p>
        <p class="metric__note">${esc(metric.note)}</p>
      </article>`).join('');
  }

  function renderFamilies(items) {
    if (!items || !items.length) {
      els.families.innerHTML = '<p class="muted">No formula families have been indexed yet.</p>';
      return;
    }
    els.families.innerHTML = items.map((item, index) => `
      <button class="family-row" type="button" data-formula="${esc(item.formula)}" style="--family-delay:${index * 35}ms">
        <span class="family-row__rank mono">${String(index + 1).padStart(2, '0')}</span>
        <span class="family-row__formula">${esc(item.formula)}</span>
        <span class="family-row__count mono">${count(item.entries)}</span>
        <span class="family-row__arrow" aria-hidden="true">↗</span>
      </button>`).join('');
    els.families.querySelectorAll('[data-formula]').forEach((button) => {
      button.addEventListener('click', () => {
        readFilterControls();
        handleFilterChange.cancel();
        state.filters.formula = button.dataset.formula;
        state.offset = 0;
        syncControls();
        writeUrlState();
        loadEntries();
      });
    });
  }

  function renderSignals(data) {
    const generations = data.key_generations || {};
    const legacy = Object.entries(generations).some(([key, value]) => Number(key) <= 4 && Number(value) > 0);
    const unknown = Number((data.provenance || {}).unknown || 0);
    const signals = [];
    if (legacy) signals.push({ tone: 'warning', text: 'legacy generation detected' });
    if (unknown > 0) signals.push({ tone: 'warning', text: `provenance coverage incomplete · ${count(unknown)} unknown` });
    if (!Number(data.with_bandgap || 0)) signals.push({ tone: 'warning', text: 'bandgap unavailable in stored metadata' });
    if (data.storage_scan === false) signals.push({ tone: 'neutral', text: 'storage scan not run' });
    if (!signals.length) signals.push({ tone: 'good', text: 'No coverage warnings in this metadata summary.' });
    els.signals.innerHTML = signals.map((signal) => `<li class="signal signal--${esc(signal.tone)}"><span class="signal__dot" aria-hidden="true"></span>${esc(signal.text)}</li>`).join('');
  }

  function setCatalogState(message, tone = 'neutral') {
    els.catalogState.innerHTML = message ? `<div class="catalog-state__message catalog-state__message--${esc(tone)}">${esc(message)}</div>` : '';
  }

  function rowMarkup(row) {
    const provenance = display(row.provenance, 'unknown');
    const provenanceSource = display(row.provenance_source, 'legacy');
    const converged = row.converged === true ? 'converged' : row.converged === false ? 'not converged' : 'not recorded';
    const tone = row.converged === true ? 'good' : row.converged === false ? 'warning' : 'neutral';
    return `<tr class="catalog-row" data-hash="${esc(row.content_hash)}" tabindex="0" role="button" aria-label="Open ${esc(row.formula || 'calculation')} detail">
      <td><span class="formula-cell">${esc(display(row.formula))}</span><span class="sub-cell mono">${esc(display(row.content_hash, 'no hash'))}</span></td>
      <td><span class="task-cell">${esc(display(row.task_name, 'unnamed task'))}</span><span class="sub-cell">${esc(provenance)} · ${esc(provenanceSource)}</span></td>
      <td class="mono">${esc(number(row.total_energy))}</td>
      <td><span class="state-pill state-pill--${tone}">${esc(converged)}</span></td>
      <td class="mono">${esc(display(row.nsites))}</td>
      <td class="mono muted">${esc(date(row.cached_at))}</td>
    </tr>`;
  }

  function renderRows(rows, limit) {
    if (!rows.length) {
      els.catalogBody.innerHTML = '';
      const active = Object.entries(state.filters).filter(([, value]) => value).map(([key, value]) => `${key}: ${value}`).join(' · ');
      setCatalogState(active ? `No records match ${active}. Clear a filter to return to the atlas.` : 'No calculation records are available yet.', 'empty');
      els.catalogCount.textContent = '0 records';
      return;
    }
    setCatalogState('');
    els.catalogBody.innerHTML = rows.map(rowMarkup).join('');
    els.catalogBody.querySelectorAll('.catalog-row').forEach((row) => {
      row.addEventListener('click', () => openDrawer(row.dataset.hash));
      row.addEventListener('keydown', (event) => {
        if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); openDrawer(row.dataset.hash); }
      });
    });
    els.catalogCount.textContent = `${count(rows.length)} shown · offset ${count(state.offset)}`;
  }

  function updatePagination(limit) {
    els.previous.disabled = state.offset <= 0;
    els.next.disabled = !state.hasMore;
    els.pageStatus.textContent = `PAGE ${Math.floor(state.offset / limit) + 1}`;
  }

  function queryForEntries() {
    const params = new URLSearchParams();
    Object.entries(state.filters).forEach(([name, value]) => { if (value) params.set(name, value); });
    params.set('limit', String(PAGE_SIZE));
    params.set('offset', String(state.offset));
    return params.toString();
  }

  async function loadEntries() {
    const requestId = ++state.requestId;
    setCatalogState('Loading records…');
    try {
      const response = await fetch(`/api/entries?${queryForEntries()}`, { headers: { Accept: 'application/json' } });
      if (!response.ok) throw new Error(`Entries request failed (${response.status})`);
      const payload = await response.json();
      if (requestId !== state.requestId) return;
      state.hasMore = Boolean(payload.has_more);
      renderRows(payload.rows || [], payload.limit || PAGE_SIZE);
      updatePagination(payload.limit || PAGE_SIZE);
      els.lastRead.textContent = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    } catch (error) {
      if (requestId !== state.requestId) return;
      els.catalogBody.innerHTML = '';
      setCatalogState(error.message || 'Unable to load records.', 'error');
      els.catalogCount.textContent = 'catalog unavailable';
      state.hasMore = false;
      updatePagination(PAGE_SIZE);
    }
  }

  async function loadOverview() {
    try {
      const response = await fetch('/api/overview?top_formulas=8', { headers: { Accept: 'application/json' } });
      if (!response.ok) throw new Error(`Overview request failed (${response.status})`);
      state.overview = await response.json();
      renderMetrics(state.overview);
      renderFamilies(state.overview.top_formulas || []);
      renderSignals(state.overview);
      setStatus('Metadata view ready · no storage scan was run.', 'neutral');
    } catch (error) {
      els.metrics.innerHTML = '<div class="metric metric--error">Overview unavailable</div>';
      els.families.innerHTML = '<p class="muted">Formula index unavailable.</p>';
      setStatus(error.message || 'Unable to load overview.', 'error');
    }
  }

  const debounce = (fn, delay) => {
    let timer;
    const debounced = (...args) => {
      window.clearTimeout(timer);
      timer = window.setTimeout(() => { timer = null; fn(...args); }, delay);
    };
    debounced.flush = () => {
      if (timer !== null && timer !== undefined) window.clearTimeout(timer);
      timer = null;
      fn();
    };
    debounced.cancel = () => {
      if (timer !== null && timer !== undefined) window.clearTimeout(timer);
      timer = null;
    };
    return debounced;
  };

  const handleFilterChange = debounce(() => {
    readFilterControls();
    state.offset = 0;
    writeUrlState();
    loadEntries();
  }, 280);

  function renderObjectList(objects) {
    const values = Object.entries(objects || {});
    if (!values.length) return '<p class="muted">No logical objects recorded.</p>';
    return `<ul class="object-list">${values.map(([name, object]) => `
      <li class="object-row"><div><strong>${esc(name)}</strong><span class="sub-cell mono">${esc(display(object.digest))}</span></div><div class="object-row__meta"><span class="state-pill state-pill--${object.present ? 'good' : 'warning'}">${object.present ? 'present' : 'missing'}</span><span class="mono">${object.size === null || object.size === undefined ? '—' : `${count(object.size)} B`}</span></div></li>`).join('')}</ul>`;
  }

  function detailMarkup(detail) {
    const hash = display(detail.content_hash);
    const source = display(detail.source_dir);
    const convergence = detail.converged === true ? 'converged' : detail.converged === false ? 'not converged' : 'not recorded';
    return `<div class="detail-intro"><p class="formula-cell">${esc(display(detail.formula))}</p><p class="detail-task">${esc(display(detail.task_name, 'unnamed task'))}</p></div>
      <div class="detail-grid">
        <div><dt>total energy</dt><dd class="mono">${esc(number(detail.total_energy))}</dd></div>
        <div><dt>convergence</dt><dd>${esc(convergence)}</dd></div>
        <div><dt>nsites</dt><dd class="mono">${esc(display(detail.nsites))}</dd></div>
        <div><dt>lattice maximum</dt><dd class="mono">${esc(number(detail.max_abc))}</dd></div>
        <div><dt>provenance</dt><dd>${esc(display(detail.provenance))} <span class="muted">(${esc(display(detail.provenance_source))})</span></dd></div>
        <div><dt>cached</dt><dd class="mono">${esc(date(detail.cached_at))}</dd></div>
      </div>
      <section class="detail-section"><h3>Identity</h3><dl class="fact-list">
        <div><dt>content hash</dt><dd class="copy-line"><code>${esc(hash)}</code><button class="copy-button" type="button" data-copy="${esc(hash)}">Copy</button></dd></div>
        <div><dt>key generation</dt><dd class="mono">${esc(display(detail.key_generation))}</dd></div>
        <div><dt>profile ID</dt><dd class="mono">${esc(display(detail.profile_id))}</dd></div>
        <div><dt>mapping digest</dt><dd class="mono breakable">${esc(display(detail.mapping_digest))}</dd></div>
      </dl></section>
      <section class="detail-section"><h3>Source</h3><div class="source-block"><code>${esc(source)}</code><button class="copy-button" type="button" data-copy="${esc(source)}">Copy path</button></div><p class="detail-caution">Text only. The source directory is never opened or linked by this dashboard.</p></section>
      <section class="detail-section"><div class="detail-section__heading"><h3>Stored objects</h3><span class="eyebrow">metadata facts</span></div>${renderObjectList(detail.objects)}</section>
      <section class="detail-section storage-action"><p><strong>Need a storage inventory?</strong><br><span class="muted">This can be slower and is never run automatically.</span></p><button id="run-storage-scan" class="button button--outline" type="button">Run storage scan</button><div id="storage-scan-result" class="scan-result" aria-live="polite"></div></section>`;
  }

  async function openDrawer(hash) {
    if (!hash) return;
    if (state.closeTimer !== null) {
      window.clearTimeout(state.closeTimer);
      state.closeTimer = null;
    }
    const detailRequestId = ++state.detailRequestId;
    if (els.drawer.hidden) state.previousFocus = document.activeElement;
    els.drawerTitle.textContent = 'Loading record…';
    els.drawerContent.innerHTML = '<div class="drawer-state"><span class="spinner"></span> Fetching normalized detail…</div>';
    els.drawer.hidden = false;
    els.backdrop.hidden = false;
    requestAnimationFrame(() => els.drawer.classList.add('is-open'));
    els.drawer.setAttribute('aria-hidden', 'false');
    els.drawer.focus();
    try {
      const response = await fetch(`/api/entry/${encodeURIComponent(hash)}`, { headers: { Accept: 'application/json' } });
      if (!response.ok) throw new Error(`Detail request failed (${response.status})`);
      const detail = await response.json();
      if (detailRequestId !== state.detailRequestId) return;
      state.lastHash = hash;
      els.drawerTitle.textContent = display(detail.formula, 'Calculation detail');
      els.drawerContent.innerHTML = detailMarkup(detail);
      els.drawerContent.querySelectorAll('[data-copy]').forEach((button) => button.addEventListener('click', () => copyValue(button)));
      $('#run-storage-scan')?.addEventListener('click', runStorageScan);
    } catch (error) {
      if (detailRequestId !== state.detailRequestId) return;
      els.drawerTitle.textContent = 'Record unavailable';
      els.drawerContent.innerHTML = `<div class="drawer-state drawer-state--error">${esc(error.message || 'Unable to load detail.')}</div>`;
    }
  }

  function trapDrawerFocus(event) {
    if (event.key !== 'Tab' || els.drawer.hidden || els.drawer.getAttribute('aria-hidden') !== 'false') return;
    const focusables = [...els.drawer.querySelectorAll('a[href], area[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])')]
      .filter((element) => element.getClientRects().length > 0);
    if (!focusables.length) {
      event.preventDefault();
      els.drawer.focus();
      return;
    }
    const first = focusables[0];
    const last = focusables[focusables.length - 1];
    if (event.shiftKey && (document.activeElement === first || document.activeElement === els.drawer || !els.drawer.contains(document.activeElement))) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && (document.activeElement === last || !els.drawer.contains(document.activeElement))) {
      event.preventDefault();
      first.focus();
    }
  }

  function closeDrawer() {
    state.detailRequestId += 1;
    els.drawer.classList.remove('is-open');
    els.drawer.setAttribute('aria-hidden', 'true');
    if (state.closeTimer !== null) window.clearTimeout(state.closeTimer);
    const timer = window.setTimeout(() => {
      if (state.closeTimer !== timer) return;
      state.closeTimer = null;
      els.drawer.hidden = true;
      els.backdrop.hidden = true;
    }, 220);
    state.closeTimer = timer;
    if (state.previousFocus && typeof state.previousFocus.focus === 'function') state.previousFocus.focus();
  }


  async function copyValue(button) {
    const value = button.dataset.copy || '';
    let copied = false;
    try {
      if (navigator.clipboard?.writeText) { await navigator.clipboard.writeText(value); copied = true; }
    } catch (_) { copied = false; }
    if (!copied) {
      const textarea = document.createElement('textarea');
      textarea.value = value; textarea.setAttribute('readonly', ''); textarea.style.position = 'fixed'; textarea.style.opacity = '0';
      document.body.appendChild(textarea); textarea.select();
      try { copied = document.execCommand('copy'); } catch (_) { copied = false; }
      textarea.remove();
    }
    const original = button.textContent;
    button.textContent = copied ? 'Copied' : 'Select manually';
    window.setTimeout(() => { button.textContent = original; }, 1600);
  }

  async function runStorageScan() {
    const button = $('#run-storage-scan');
    const result = $('#storage-scan-result');
    if (!button || !result) return;
    button.disabled = true; button.textContent = 'Scanning…';
    result.textContent = 'Checking physical CAS objects; this may take a moment.';
    try {
      const response = await fetch('/api/objects?orphans_only=false', { headers: { Accept: 'application/json' } });
      if (!response.ok) throw new Error(`Storage scan failed (${response.status})`);
      const payload = await response.json();
      result.textContent = `${count((payload.rows || []).length)} object records returned. This is an inventory, not a scientific validity judgment.`;
    } catch (error) {
      result.textContent = error.message || 'Storage scan unavailable.';
    } finally {
      button.disabled = false; button.textContent = 'Run storage scan';
    }
  }

  els.filters.addEventListener('input', handleFilterChange);
  els.filters.addEventListener('change', handleFilterChange);
  els.filters.addEventListener('submit', (event) => {
    event.preventDefault();
    handleFilterChange.flush();
  });
  els.clear.addEventListener('click', () => {
    handleFilterChange.cancel();
    state.filters = { provenance: 'canonical' }; state.offset = 0; syncControls(); writeUrlState(); loadEntries();
  });
  els.previous.addEventListener('click', () => {
    readFilterControls();
    handleFilterChange.cancel();
    if (state.offset <= 0) return;
    state.offset = Math.max(0, state.offset - PAGE_SIZE); writeUrlState(); loadEntries();
  });
  els.next.addEventListener('click', () => {
    readFilterControls();
    handleFilterChange.cancel();
    if (!state.hasMore) return;
    state.offset += PAGE_SIZE; writeUrlState(); loadEntries();
  });
  els.closeDrawer.addEventListener('click', closeDrawer);
  els.backdrop.addEventListener('click', closeDrawer);
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && !els.drawer.hidden) closeDrawer();
    trapDrawerFocus(event);
  });

  parseUrlState();
  syncControls();
  loadOverview();
  loadEntries();
})();
