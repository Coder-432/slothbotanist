/* SlothBotanist front end: plain JavaScript, no build step. Talks to the FastAPI backend. */
(() => {
  'use strict';

  /* ============ helpers ============ */
  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
  const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const safeUrl = (u) => (/^https?:\/\//i.test(String(u || '')) ? String(u) : '');
  const stepNo = (n) => String(n);

  const ENGINE_LABEL = {
    google: 'Web',
    google_scholar: 'Research',
    google_books: 'Old books',
    google_patents: 'Old methods',
    google_news: 'News and safety',
    youtube: 'Videos',
    google_trends_trending_now: 'Trending',
    google_trends: 'Seasons',
    duckduckgo: 'Second opinion',
    google_images: 'Pictures',
  };
  const engineLabel = (e) => ENGINE_LABEL[e] || e;

  const store = {
    get(key, fallback) {
      try {
        const raw = localStorage.getItem('sloth.' + key);
        return raw == null ? fallback : JSON.parse(raw);
      } catch { return fallback; }
    },
    set(key, value) { try { localStorage.setItem('sloth.' + key, JSON.stringify(value)); } catch { /* storage blocked */ } },
    clearAll() {
      try {
        Object.keys(localStorage).filter((k) => k.startsWith('sloth.')).forEach((k) => localStorage.removeItem(k));
      } catch { /* storage blocked */ }
    },
  };

  const cleanList = (v) => (Array.isArray(v) ? v.filter((x) => typeof x === 'string' && x.trim()).slice(0, 40) : []);

  const DEFAULT_LOC = { location: 'United States', gl: 'us', hl: 'en', google_domain: 'google.com' };
  const state = {
    pantry: cleanList(store.get('pantry', [])),
    identified: cleanList(store.get('identified', [])),
    allergies: cleanList(store.get('allergies', [])),
    goal: String(store.get('goal', '') || ''),
    loc: Object.assign({}, DEFAULT_LOC, store.get('loc', {})),
  };

  /* ============ API ============ */
  class ApiError extends Error {
    constructor(status, message) { super(message); this.status = status; }
  }

  function describeDetail(d) {
    if (!d) return '';
    if (typeof d === 'string') return d;
    if (Array.isArray(d)) return d.map((x) => x.msg || JSON.stringify(x)).join('; ');
    if (d.error) {
      const left = Array.isArray(d.blocked_items) && d.blocked_items.length
        ? ' Left out: ' + d.blocked_items.map((b) => `${b.item} (${b.allergy})`).join(', ') + '.' : '';
      return d.error + left;
    }
    return JSON.stringify(d);
  }

  async function api(path, opts = {}) {
    let res;
    if (location.protocol === 'file:' && !window.__SLOTH_DEMO__) {
      throw new ApiError(0, 'This page was opened as a file. Start the server with: uvicorn main:app, then open http://localhost:8000');
    }
    try {
      res = await fetch(path, opts);
    } catch (e) {
      if (e && e.name === 'AbortError') throw e;
      throw new ApiError(0, 'Could not reach the SlothBotanist server. Is it running?');
    }
    let data = null;
    try { data = await res.json(); } catch { /* body was not JSON */ }
    if (!res.ok) {
      const detail = data && data.detail !== undefined ? data.detail : data;
      throw new ApiError(res.status, describeDetail(detail) || `The server answered ${res.status}.`);
    }
    return data;
  }

  async function copyText(text) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch {
      const ta = document.createElement('textarea');
      ta.value = text;
      ta.style.position = 'fixed';
      ta.style.opacity = '0';
      document.body.appendChild(ta);
      ta.select();
      let ok = false;
      try { ok = document.execCommand('copy'); } catch { ok = false; }
      ta.remove();
      return ok;
    }
  }

  /* ============ navigation ============ */
  const VIEWS = ['brew', 'identify', 'pages', 'ledger', 'settings'];

  function show(view, { scroll = true } = {}) {
    if (!VIEWS.includes(view)) view = 'brew';
    VIEWS.forEach((v) => { $('#view-' + v).hidden = v !== view; });
    $$('.nav button').forEach((b) => {
      if (b.dataset.view === view) b.setAttribute('aria-current', 'page');
      else b.removeAttribute('aria-current');
    });
    try {
      if (location.hash !== '#' + view) history.replaceState(null, '', '#' + view);
    } catch { /* sandboxed preview frames forbid changing the URL; navigation still works */ }
    if (scroll) window.scrollTo(0, 0);
    if (view === 'ledger') loadLedger();
    if (view === 'settings') fillSettings();
  }

  $$('.nav button').forEach((b) => b.addEventListener('click', () => show(b.dataset.view)));
  window.addEventListener('hashchange', () => show(location.hash.slice(1)));

  /* ============ chips (shelf and allergies) ============ */
  const MAX_ITEMS = 40;
  const parseItems = (text) => String(text).split(/[,\n;]+/)
    .map((s) => s.trim().replace(/\s+/g, ' ').slice(0, 60)).filter(Boolean);

  function addItems(list, text) {
    const seen = new Set(list.map((x) => x.toLowerCase()));
    for (const item of parseItems(text)) {
      if (list.length >= MAX_ITEMS) break;
      if (!seen.has(item.toLowerCase())) { list.push(item); seen.add(item.toLowerCase()); }
    }
  }

  function chipHtml(text, index, group, extra = '') {
    return `<span class="chip ${extra}">${esc(text)}<button type="button" class="x" data-group="${group}" data-i="${index}" aria-label="Remove ${esc(text)}">×</button></span>`;
  }

  function renderShelf() {
    const found = state.identified.map((t, i) => chipHtml(t + ' (found)', i, 'identified', 'found'));
    const mine = state.pantry.map((t, i) => chipHtml(t, i, 'pantry'));
    $('#pantryChips').innerHTML = mine.concat(found).join('');
  }
  function renderAllergies() {
    $('#allergyChips').innerHTML = state.allergies.map((t, i) => chipHtml(t, i, 'allergies')).join('');
  }

  function persistLists() {
    store.set('pantry', state.pantry);
    store.set('identified', state.identified);
    store.set('allergies', state.allergies);
  }

  function wireChips(container) {
    container.addEventListener('click', (e) => {
      const btn = e.target.closest('.x');
      if (!btn) return;
      const list = state[btn.dataset.group];
      list.splice(Number(btn.dataset.i), 1);
      persistLists();
      renderShelf();
      renderAllergies();
    });
  }
  wireChips($('#pantryChips'));
  wireChips($('#allergyChips'));

  function commitInput(inputEl, list) {
    if (inputEl.value.trim()) { addItems(list, inputEl.value); inputEl.value = ''; persistLists(); }
  }
  function wireAdder(inputSel, btnSel, list) {
    const input = $(inputSel);
    const add = () => { commitInput(input, list); renderShelf(); renderAllergies(); input.focus(); };
    $(btnSel).addEventListener('click', add);
    input.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ',') { e.preventDefault(); add(); }
    });
  }
  wireAdder('#pantryInput', '#pantryAdd', state.pantry);
  wireAdder('#allergyInput', '#allergyAdd', state.allergies);

  const GOALS = ['soothing evening', 'cold and cosy', 'gentle digestion', 'morning energy', 'calm before sleep', 'cooling hydration'];
  const COMMON_ALLERGIES = ['tree nuts', 'peanut', 'dairy', 'gluten', 'egg', 'soy', 'sesame', 'ragweed', 'birch pollen'];

  function renderSuggestions() {
    $('#goalSuggest').innerHTML = GOALS.map((g) => `<button type="button" data-goal="${esc(g)}">${esc(g)}</button>`).join('');
    $('#allergySuggest').innerHTML = COMMON_ALLERGIES.map((a) => `<button type="button" data-allergy="${esc(a)}">${esc(a)}</button>`).join('');
  }
  $('#goalSuggest').addEventListener('click', (e) => {
    const b = e.target.closest('button[data-goal]');
    if (!b) return;
    $('#goal').value = b.dataset.goal;
    store.set('goal', b.dataset.goal);
    $('#goal').focus();
  });
  $('#allergySuggest').addEventListener('click', (e) => {
    const b = e.target.closest('button[data-allergy]');
    if (!b) return;
    addItems(state.allergies, b.dataset.allergy);
    persistLists();
    renderAllergies();
  });
  $('#goal').addEventListener('input', (e) => store.set('goal', e.target.value));

  /* ============ markdown (small, safe) ============ */
  let citeMap = new Map(); // "S3" -> display number

  function inline(text) {
    let s = esc(text);
    s = s.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    s = s.replace(/(^|[^*\w])\*(?!\s)([^*]+?)\*(?![*\w])/g, '$1<em>$2</em>');
    s = s.replace(/\[(S\d+)\]/g, (m, id) => {
      const n = citeMap.get(id);
      return n ? `<sup class="cite"><a href="#note-${n}" title="See note ${n}">${n}</a></sup>` : '';
    });
    return s;
  }

  function md(text) {
    let html = '';
    let list = null;
    const close = () => { if (list) { html += `</${list}>`; list = null; } };
    for (const raw of String(text || '').split(/\r?\n/)) {
      const line = raw.trimEnd();
      if (!line.trim()) { close(); continue; }
      let m;
      if ((m = line.match(/^\s*#{1,6}\s+(.*)$/))) { close(); html += `<h4>${inline(m[1])}</h4>`; }
      else if ((m = line.match(/^\s*[-*•]\s+(.*)$/))) {
        if (list !== 'ul') { close(); html += '<ul>'; list = 'ul'; }
        html += `<li><span>${inline(m[1])}</span></li>`;
      } else if ((m = line.match(/^\s*\d+[.)]\s+(.*)$/))) {
        if (list !== 'ol') { close(); html += '<ol>'; list = 'ol'; }
        html += `<li><span>${inline(m[1])}</span></li>`;
      } else { close(); html += `<p>${inline(line)}</p>`; }
    }
    close();
    return html;
  }

  function parseElixirs(text) {
    const parts = { intro: [], heritage: [], modern: [], cautions: [] };
    let cur = 'intro';
    for (const raw of String(text || '').split(/\r?\n/)) {
      const trimmed = raw.trim();
      const plain = trimmed.replace(/[*_`#]/g, '').trim();
      const heading = /^(#{1,6}\s|\*\*[^*]+\*\*:?\s*$)/.test(trimmed);
      if (heading && /heritage/i.test(plain)) { cur = 'heritage'; continue; }
      if (heading && /modern/i.test(plain)) { cur = 'modern'; continue; }
      if (heading && /caution/i.test(plain)) { cur = 'cautions'; continue; }
      if (!heading && /^cautions?\b\s*[:\-]/i.test(plain)) {
        parts.cautions.push(trimmed.replace(/^[\s#*_-]*cautions?\b[\s:*_-]*/i, ''));
        continue;
      }
      if (cur === 'cautions') { if (plain) parts.cautions.push(trimmed.replace(/^[-*]\s+/, '')); continue; }
      parts[cur].push(raw);
    }
    return Object.fromEntries(Object.entries(parts).map(([k, v]) => [k, v.join('\n').trim()]));
  }

  /* ============ brewing ============ */
  let brewCtl = null;
  let steepTimer = null;
  const STEEP_LINES = [
    'Asking every search engine at once…',
    'Setting aside anything that does not suit your allergies…',
    'Reading what the old herbals say…',
    'Steeping with the local model. This part can take a minute…',
  ];

  function loaderHtml() {
    return `<div class="card steep">
      <svg viewBox="0 0 120 120" aria-hidden="true">
        <path class="steam" d="M42 40c-6-8 6-12 0-22"/>
        <path class="steam" d="M60 40c-6-8 6-12 0-22"/>
        <path class="steam" d="M78 40c-6-8 6-12 0-22"/>
        <path d="M22 54H92V88Q92 108 72 108H42Q22 108 22 88Z" fill="#B7C1F0"/>
        <path d="M92 64H100Q112 64 112 77Q112 90 98 90H91" fill="none" stroke="#9AA6E8" stroke-width="7" stroke-linecap="round"/>
        <path d="M22 62H92V72H22Z" fill="#FF9AA2" opacity=".8"/>
        <ellipse cx="57" cy="112" rx="44" ry="5" fill="#FFC46B"/>
      </svg>
      <p id="steepLine">${esc(STEEP_LINES[0])}</p>
      <p class="sub">Please keep this page open.</p>
      <button type="button" class="btn btn-ghost btn-sm" id="cancelBrew">Stop waiting</button>
    </div>`;
  }

  function setBrewing(on) {
    const btn = $('#brewBtn');
    btn.disabled = on;
    btn.textContent = on ? 'Brewing…' : 'Brew it';
    clearInterval(steepTimer);
    if (on) {
      let i = 0;
      steepTimer = setInterval(() => {
        i = (i + 1) % STEEP_LINES.length;
        const el = $('#steepLine');
        if (el) el.textContent = STEEP_LINES[i];
      }, 3800);
    }
  }

  function formProblem(message, focusEl) {
    const msg = $('#formMsg');
    msg.textContent = message;
    msg.className = 'msg err';
    const form = $('#brewForm');
    form.classList.remove('shake');
    void form.offsetWidth; // restart animation
    form.classList.add('shake');
    if (focusEl) focusEl.focus();
  }

  async function brew(ev) {
    ev.preventDefault();
    commitInput($('#pantryInput'), state.pantry);
    commitInput($('#allergyInput'), state.allergies);
    renderShelf();
    renderAllergies();
    $('#formMsg').textContent = '';
    $('#formMsg').className = 'msg';

    const goal = $('#goal').value.trim();
    if (goal.length < 2) return formProblem('Tell me what the drink should do for you.', $('#goal'));
    const own = state.pantry.slice();
    const found = state.identified.slice();
    if (!own.length && !found.length) return formProblem('Add at least one thing from your shelf first.', $('#pantryInput'));

    const body = {
      pantry_items: own.length ? own : found, // the server needs at least one pantry item
      identified_herbs: own.length ? found : [],
      wellness_goal: goal,
      allergies: state.allergies.slice(),
      location: state.loc.location,
      gl: state.loc.gl,
      hl: state.loc.hl,
      google_domain: state.loc.google_domain,
    };

    brewCtl = new AbortController();
    $('#results').innerHTML = loaderHtml();
    $('#results').scrollIntoView({ behavior: 'smooth', block: 'start' });
    $('#cancelBrew').addEventListener('click', () => brewCtl && brewCtl.abort());
    setBrewing(true);
    try {
      const data = await api('/api/brew', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
        signal: brewCtl.signal,
      });
      renderResults(data, goal);
    } catch (e) {
      if (e && e.name === 'AbortError') {
        $('#results').innerHTML = alertHtml('Stopped waiting', 'The request was cancelled. The server may still finish in the background.');
      } else {
        $('#results').innerHTML = errorHtml(e);
      }
    } finally {
      setBrewing(false);
      brewCtl = null;
    }
  }
  // Handled on click and Enter as well as submit, so it also works where a sandboxed frame blocks form submission.
  $('#brewForm').addEventListener('submit', brew);
  $('#brewBtn').addEventListener('click', (ev) => { ev.preventDefault(); if (!brewCtl) brew(ev); });
  $('#goal').addEventListener('keydown', (ev) => { if (ev.key === 'Enter') { ev.preventDefault(); if (!brewCtl) brew(ev); } });

  function alertHtml(title, text, hint = '') {
    return `<div class="alert" role="alert"><h3>${esc(title)}</h3><p>${esc(text)}</p>${hint ? `<p class="hint">${esc(hint)}</p>` : ''}</div>`;
  }
  function errorHtml(e) {
    const status = e instanceof ApiError ? e.status : 0;
    let hint = '';
    if (status === 0) hint = 'Start it with: uvicorn main:app, then reload this page.';
    else if (status === 503) hint = 'Check SERPAPI_KEY, or run once online so the saved results can be reused. A missing local model also causes this.';
    else if (status === 401) hint = 'The SerpApi key in SERPAPI_KEY was refused. Fix it and restart the server.';
    else if (status === 429) hint = 'SerpApi asked us to slow down or the monthly searches are used up. Wait a minute, then try again.';
    else if (status === 400) hint = 'Try taking something off your allergy list, or add more to your shelf.';
    return alertHtml("That brew did not work", e.message || 'Something went wrong.', hint);
  }

  /* ---------- result rendering ---------- */
  function buildCiteMap(data) {
    const map = new Map();
    const valid = new Set((data.citations || []).map((c) => c.id));
    const re = /\[(S\d+)\]/g;
    let m;
    const text = String(data.elixirs || '');
    while ((m = re.exec(text))) {
      if (valid.has(m[1]) && !map.has(m[1])) map.set(m[1], map.size + 1);
    }
    return map;
  }

  const badge = (cls, text) => `<span class="badge ${cls}"><i></i>${esc(text)}</span>`;

  function statusBadges(data) {
    const out = [];
    const al = data.allergies || {};
    const viol = data.pantry_violations || [];
    out.push(viol.length
      ? badge('warn', 'Mentions things not on your shelf: ' + viol.join(', '))
      : badge('ok', 'Only what is on your shelf'));
    const checked = al.checked || [];
    if (checked.length) {
      const hits = al.output_hits || [];
      out.push(hits.length
        ? badge('bad', 'Allergen words found: ' + hits.map((h) => h.split(':')[1]).join(', '))
        : badge('ok', 'Allergy scan clear for ' + checked.join(', ')));
      if (al.regenerated) out.push(badge('note', 'Rewritten once to keep allergens out'));
    } else {
      out.push(badge('note', 'No allergies listed'));
    }
    return `<div class="status-row">${out.join('')}</div>`;
  }

  function leftOutColumn(data) {
    const al = data.allergies || {};
    const blocked = al.blocked_items || [];
    const cautions = al.cross_reactivity_cautions || [];
    const rows = [];
    blocked.forEach((b) => rows.push(`<div class="item"><span class="no">${stepNo(rows.length + 1)}</span>
      <div class="main"><s>${esc(b.item)}</s> left out</div>
      <div class="sub">Matches your ${esc(b.allergy)} allergy (found “${esc(b.matched)}”).</div></div>`));
    cautions.forEach((c) => rows.push(`<div class="item"><span class="no">${stepNo(rows.length + 1)}</span>
      <div class="main">${esc(c.item)} <small style="font:400 13px var(--sans);color:var(--muted)">kept, with care</small></div>
      <div class="sub">Can cross-react with a ${esc(c.allergy)} allergy. Ask a clinician before using it.</div></div>`));
    return `<div class="col"><h3 class="col-title">Left out for your safety</h3>
      ${rows.length ? rows.join('') : '<p class="empty">Nothing needed leaving out.</p>'}</div>`;
  }

  function checkedColumn(data) {
    const rows = [];
    const viol = data.pantry_violations || [];
    const al = data.allergies || {};
    rows.push([viol.length ? `Outside your shelf: ${viol.join(', ')}` : 'Nothing from outside your shelf',
      viol.length ? 'Swap these for something you already have.' : 'Every ingredient is something you listed.']);
    const checked = al.checked || [];
    rows.push([checked.length ? 'Recipe scanned for allergens' : 'No allergies to check',
      checked.length ? `Looked for: ${checked.join(', ')}.` : 'Add allergies to your list to turn the scan on.']);
    const report = data.engine_report || [];
    const ok = report.filter((r) => ['success', 'cache_hit', 'fallback_cache'].includes(r.status)).length;
    rows.push([`${ok} of ${report.length} search engines answered`, 'Each one looks for something different, listed at the bottom.']);
    return `<div class="col"><h3 class="col-title">What I checked</h3>
      ${rows.map((r, i) => `<div class="item"><span class="no">${stepNo(i + 1)}</span><div class="main">${esc(r[0])}</div><div class="sub">${esc(r[1])}</div></div>`).join('')}</div>`;
  }

  function elixirCard(kind, title, sub, tag, text) {
    return `<article class="elixir ${kind}">
      <span class="tag">${esc(tag)}</span><h3>${esc(title)}</h3><p class="sub">${esc(sub)}</p>
      <div class="body">${md(text) || '<p class="empty">Nothing came back for this one.</p>'}</div></article>`;
  }

  function seasonHtml(s) {
    if (!s || !Array.isArray(s.series) || !s.series.length) return '';
    const letters = ['J', 'F', 'M', 'A', 'M', 'J', 'J', 'A', 'S', 'O', 'N', 'D'];
    const figs = s.series.map((one) => {
      const vals = (one.monthly || []).slice(0, 12).map((v) => Number(v) || 0);
      while (vals.length < 12) vals.push(0);
      const max = Math.max(...vals, 1);
      const peakIdx = vals.indexOf(Math.max(...vals));
      const bars = vals.map((v, i) => {
        const h = Math.max(3, (v / max) * 70);
        return `<rect class="bar-rect ${i === peakIdx ? 'peak' : ''}" x="${10 + i * 28}" y="${80 - h}" width="20" height="${h}" rx="4"><title>${esc(letters[i])}: ${Math.round(v)}</title></rect>
          <text x="${20 + i * 28}" y="94">${letters[i]}</text>`;
      }).join('');
      return `<figure><figcaption>${esc(one.query)} peaks in <strong>${esc(one.peak_month)}</strong></figcaption>
        <svg viewBox="0 0 346 100" role="img" aria-label="Monthly interest in ${esc(one.query)}, highest in ${esc(one.peak_month)}">${bars}</svg></figure>`;
    }).join('');
    return `<section class="block"><h3>Best time of year</h3><div class="season">${figs}
      <p class="note">How often people searched for this over the last twelve months, by month.</p></div></section>`;
  }

  function notesHtml(data) {
    const cites = (data.citations || []).filter((c) => citeMap.has(c.id))
      .sort((a, b) => citeMap.get(a.id) - citeMap.get(b.id));
    if (!cites.length) return '';
    const li = cites.map((c) => {
      const url = safeUrl(c.url);
      const title = url ? `<a href="${esc(url)}" target="_blank" rel="noopener noreferrer">${esc(c.title)}</a>` : esc(c.title);
      return `<li id="note-${citeMap.get(c.id)}"><span>${title}<small>${esc(engineLabel(c.engine))}</small></span></li>`;
    }).join('');
    const rest = (data.all_sources || []).filter((s) => !citeMap.has(s.id));
    const more = rest.length ? `<details class="raw"><summary>Everything else the search found (${rest.length})</summary>
      <ol class="notes">${rest.map((s) => {
        const url = safeUrl(s.url);
        const t = url ? `<a href="${esc(url)}" target="_blank" rel="noopener noreferrer">${esc(s.title)}</a>` : esc(s.title);
        return `<li><span>${t}<small>${esc(engineLabel(s.engine))}</small></span></li>`;
      }).join('')}</ol></details>` : '';
    return `<section class="block"><h3>Notes and sources</h3><ol class="notes">${li}</ol>${more}</section>`;
  }

  function crewHtml(data) {
    const report = data.engine_report || [];
    if (!report.length) return '';
    const kind = (s) => (['success', 'cache_hit'].includes(s) ? '' : s === 'fallback_cache' ? 'warn' : 'off');
    const label = (s) => ({ success: 'live', cache_hit: 'saved', fallback_cache: 'saved after an error', cooldown: 'resting', offline_miss: 'no saved result', error: 'failed' }[s] || s);
    const pills = report.map((r) => `<span class="badge ${kind(r.status)}" title="${esc(r.message || '')}"><i></i>${esc(engineLabel(r.engine))} <small>${esc(label(r.status))}${r.ms != null ? ` · ${r.ms} ms` : ''}</small></span>`).join('');
    return `<section class="block"><h3>The search crew</h3><div class="crew">${pills}</div></section>`;
  }

  function renderResults(data, goal) {
    citeMap = buildCiteMap(data);
    if (data.status === 'withheld') return renderWithheld(data);

    const parts = parseElixirs(data.elixirs);
    const hasSplit = parts.heritage || parts.modern;
    const heading = goal.charAt(0).toUpperCase() + goal.slice(1);

    const elixirs = hasSplit
      ? `<div class="elixirs">
          ${elixirCard('heritage', 'Heritage Elixir', 'slow, warming, time-tested', 'The classic pillar', parts.heritage)}
          ${elixirCard('modern', 'Modern Refresh', 'quick, crisp, everyday', 'The contemporary pillar', parts.modern)}
        </div>`
      : `<div class="elixirs">${elixirCard('single', 'Your brew', 'made from your shelf', 'The recipe', [parts.intro, parts.heritage, parts.modern].filter(Boolean).join('\n'))}</div>`;
    const intro = hasSplit && parts.intro ? `<div class="callout"><b>A note first</b>${md(parts.intro)}</div>` : '';
    const cautions = parts.cautions ? `<div class="callout"><b>Cautions</b>${md(parts.cautions)}</div>` : '';

    const visuals = (data.visuals || []).map((v) => ({ ...v, url: safeUrl(v.url) })).filter((v) => v.url).slice(0, 6);
    const looks = visuals.length ? `<section class="block"><h3>What it can look like</h3><div class="crew">${visuals.map((v) =>
      `<a class="badge" href="${esc(v.url)}" target="_blank" rel="noopener noreferrer"><i></i>${esc(v.title.slice(0, 48))}${v.snippet ? ` <small>${esc(v.snippet)}</small>` : ''}</a>`).join('')}</div></section>` : '';

    $('#results').innerHTML = `
      <header class="result-head">
        <span class="kicker">Fresh from your shelf</span>
        <h2 class="result-title">${esc(heading)}</h2>
        <p class="result-sub">Two drinks, made only from what you have</p>
        <svg class="flourish" viewBox="0 0 120 60" aria-hidden="true"><use href="#curl"/></svg>
        ${statusBadges(data)}
      </header>
      <div class="cols">${leftOutColumn(data)}${checkedColumn(data)}</div>
      ${intro}
      ${elixirs}
      ${cautions}
      ${seasonHtml(data.seasonality)}
      ${looks}
      ${notesHtml(data)}
      ${crewHtml(data)}
      <div class="actions">
        <button type="button" class="btn btn-ghost" id="copyBrew">Copy recipe</button>
        <button type="button" class="btn btn-ghost" id="printBrew">Print</button>
      </div>
      <p class="safety">${esc(data.safety_notice || 'Educational only, not medical advice.')}</p>`;

    $('#copyBrew').addEventListener('click', async (e) => {
      const lines = (data.citations || []).filter((c) => citeMap.has(c.id)).sort((a, b) => citeMap.get(a.id) - citeMap.get(b.id))
        .map((c) => `${citeMap.get(c.id)}. ${c.title} ${c.url || ''}`.trim());
      const text = `${heading}\n\n${data.elixirs}\n${lines.length ? '\nSources:\n' + lines.join('\n') : ''}\n\n${data.safety_notice || ''}`;
      const ok = await copyText(text);
      e.target.textContent = ok ? 'Copied' : 'Could not copy';
      setTimeout(() => { e.target.textContent = 'Copy recipe'; }, 1800);
    });
    $('#printBrew').addEventListener('click', () => window.print());
  }

  function renderWithheld(data) {
    const al = data.allergies || {};
    const blocked = (al.blocked_items || []).map((b) => `${b.item} (${b.allergy})`).join(', ');
    $('#results').innerHTML = `
      <div class="alert" role="alert">
        <h3>I held this recipe back</h3>
        <p>${esc(data.message || 'The recipe kept mentioning something on your allergy list, so I am not showing it.')}</p>
        ${blocked ? `<p class="hint">Already left out of your shelf: ${esc(blocked)}.</p>` : ''}
        <p class="hint">Try again, or take a few items off your shelf. A smaller model sometimes ignores a rule, which is why the check runs in code.</p>
      </div>
      ${crewHtml(data)}
      <p class="safety">${esc(data.safety_notice || '')}</p>`;
  }

  /* ============ identify ============ */
  let herbFile = null;
  $('#herbFile').addEventListener('change', (e) => {
    herbFile = e.target.files && e.target.files[0] ? e.target.files[0] : null;
    const img = $('#herbPreview');
    if (herbFile) {
      img.src = URL.createObjectURL(herbFile);
      img.hidden = false;
      $('#dropLabel').hidden = true;
    } else {
      img.hidden = true;
      $('#dropLabel').hidden = false;
    }
  });

  $('#scanBtn').addEventListener('click', async () => {
    const msg = $('#scanMsg');
    const url = $('#herbUrl').value.trim();
    if (!herbFile && !url) { msg.textContent = 'Choose a photo or paste a picture link first.'; msg.className = 'msg err'; return; }
    const fd = new FormData();
    if (herbFile) fd.append('file', herbFile); else fd.append('image_url', url);
    const btn = $('#scanBtn');
    btn.disabled = true;
    btn.textContent = 'Looking…';
    msg.textContent = '';
    msg.className = 'msg';
    $('#scanOut').innerHTML = '';
    try {
      const data = await api('/api/scan-herb', { method: 'POST', body: fd });
      const names = data.candidates || [];
      if (!names.length) {
        msg.textContent = 'I could not find a match. Try a clearer, closer photo.';
      } else {
        const clean = (n) => String(n).split(/\s[-|–—]\s/)[0].slice(0, 60);
        const single = names.length === 1;
        $('#scanOut').innerHTML = `<div class="found-box"><h4>${single ? 'This looks like' : 'Could it be one of these?'}</h4>
          <p class="hint">${single ? 'Check the name, change it if you like, then add it to your shelf.' : 'Tap the closest match, tidy the name if you like, then add it to your shelf.'}</p>
          ${single ? '' : `<div class="chips">${names.map((n) => `<button type="button" class="pick" data-name="${esc(n)}">${esc(n)}</button>`).join('')}</div>`}
          <div class="add-row add-as"><input id="foundName" type="text" maxlength="60" placeholder="name to add"><button type="button" class="btn btn-ghost" id="foundAdd">Add to my shelf</button></div></div>`;
        if (single) $('#foundName').value = clean(names[0]);
      }
    } catch (e) {
      msg.textContent = e.message;
      msg.className = 'msg err';
    } finally {
      btn.disabled = false;
      btn.textContent = 'Identify';
    }
  });

  $('#scanOut').addEventListener('click', (e) => {
    const pick = e.target.closest('.pick');
    if (pick) {
      $$('.pick').forEach((p) => p.classList.toggle('on', p === pick));
      // Lens titles often look like "Mentha spicata - Wikipedia"; keep the part before the separator.
      $('#foundName').value = pick.dataset.name.split(/\s[-|–—]\s/)[0].slice(0, 60);
      return;
    }
    if (e.target.id === 'foundAdd') {
      const input = $('#foundName');
      if (!input.value.trim()) return;
      addItems(state.identified, input.value);
      persistLists();
      renderShelf();
      input.value = '';
      $('#scanMsg').textContent = 'Added to your shelf. Head back to Brew it to use it.';
      $('#scanMsg').className = 'msg';
    }
  });

  /* ============ old pages ============ */
  $('#pageBtn').addEventListener('click', async () => {
    const url = $('#pageUrl').value.trim();
    const msg = $('#pageMsg');
    if (!safeUrl(url)) { msg.textContent = 'Paste a full link that starts with http:// or https://'; msg.className = 'msg err'; return; }
    const btn = $('#pageBtn');
    btn.disabled = true;
    btn.textContent = 'Reading…';
    msg.textContent = '';
    msg.className = 'msg';
    $('#pageOut').innerHTML = '';
    try {
      const data = await api('/api/extract?url=' + encodeURIComponent(url));
      const x = data.extracted || {};
      const text = x.text_content || x.markdown || x.text || x.content || x.extracted_text || x.body || '';
      if (text) {
        $('#pageOut').innerHTML = `<div class="paper"></div>`;
        $('#pageOut .paper').textContent = typeof text === 'string' ? text : Array.isArray(text) ? text.join('\n\n') : safeJson(text);
      } else {
        $('#pageOut').innerHTML = `<details class="raw" open><summary>Raw result</summary><pre></pre></details>`;
        $('#pageOut pre').textContent = safeJson(x);
      }
    } catch (e) {
      msg.textContent = e.message;
      msg.className = 'msg err';
    } finally {
      btn.disabled = false;
      btn.textContent = 'Read it';
    }
  });

  /* ============ ledger ============ */
  function scrub(value, depth = 0) {
    if (depth > 8) return null;
    if (Array.isArray(value)) return value.slice(0, 200).map((v) => scrub(v, depth + 1));
    if (value && typeof value === 'object') {
      const out = {};
      for (const [k, v] of Object.entries(value)) {
        if (/api_?key|e-?mail|token|secret/i.test(k)) continue;
        out[k] = scrub(v, depth + 1);
      }
      return out;
    }
    return value;
  }
  const safeJson = (v) => {
    const s = JSON.stringify(scrub(v), null, 2) || '';
    return s.length > 20000 ? s.slice(0, 20000) + '\n… (trimmed)' : s;
  };

  async function loadLedger() {
    const out = $('#ledgerOut');
    const [stats] = await Promise.allSettled([api('/api/stats')]);
    let html = '';
    if (stats.status === 'fulfilled') {
      const s = stats.value;
      const engines = Object.entries(s.by_engine || {}).sort((a, b) => b[1] - a[1]);
      const max = Math.max(1, ...engines.map((e) => e[1]));
      html += `<div class="tiles">
        <div class="tile"><b>${Number(s.brews || 0)}</b><span>Brews made</span></div>
        <div class="tile"><b>${Number(s.cached_searches || 0)}</b><span>Searches saved</span></div>
        <div class="tile"><b>${Number(s.unique_listings || 0)}</b><span>Unique listings</span></div>
        <div class="tile"><b>${Number(s.withheld_for_allergens || 0)}</b><span>Held back for allergens</span></div>
      </div>
      <div class="card panel"><h3 class="panel-title">Searches by engine</h3>
        ${engines.length ? `<div class="bars">${engines.map(([name, n]) =>
          `<div class="bar"><span>${esc(engineLabel(name))}</span><i style="width:${Math.max(3, (n / max) * 100)}%"></i><em>${n}</em></div>`).join('')}</div>`
          : '<p class="hint">Nothing saved yet. Make a brew and the counts will appear here.</p>'}
      </div>`;
    } else {
      html += `<div class="card panel"><p class="msg err">${esc(stats.reason.message)}</p></div>`;
    }
    out.innerHTML = html;
  }

  /* ============ settings ============ */
  function fillSettings() {
    $('#locName').value = state.loc.location;
    $('#locGl').value = state.loc.gl;
    $('#locHl').value = state.loc.hl;
    $('#locDomain').value = state.loc.google_domain;
  }

  async function checkHealth() {
    const banner = $('#banner');
    let health;
    try {
      health = await api('/api/health');
    } catch (e) {
      health = { error: e.message };
    }
    let text = '';
    if (health.error) text = health.error + ' Start it with: uvicorn main:app';
    else if (!health.model_loaded) text = 'The local model is not loaded, so brewing will fail until it is.';
    else if (!health.serpapi_key && !health.offline) text = 'No SerpApi key found. Only saved results can be used until SERPAPI_KEY is set.';
    $('#bannerText').textContent = text;
    banner.hidden = !text;
  }
  $('#bannerBtn').addEventListener('click', () => checkHealth());
  $('#bannerX').addEventListener('click', () => { $('#banner').hidden = true; });

  $('#locSearch').addEventListener('click', async () => {
    const q = $('#locQuery').value.trim();
    const msg = $('#locMsg');
    if (q.length < 2) { msg.textContent = 'Type at least two letters.'; msg.className = 'msg err'; return; }
    msg.textContent = 'Searching…';
    msg.className = 'msg';
    $('#locOut').innerHTML = '';
    try {
      const data = await api('/api/locations?q=' + encodeURIComponent(q));
      const list = Array.isArray(data.locations) ? data.locations.slice(0, 8) : [];
      msg.textContent = list.length ? 'Tap one to use it.' : 'No places found.';
      $('#locOut').innerHTML = list.map((l, i) => `<button type="button" data-i="${i}">${esc(l.canonical_name || l.name)} <small>${esc(l.target_type || '')}</small></button>`).join('');
      $('#locOut').onclick = (e) => {
        const b = e.target.closest('button[data-i]');
        if (!b) return;
        const l = list[Number(b.dataset.i)];
        $('#locName').value = l.canonical_name || l.name || '';
        if (l.country_code) $('#locGl').value = String(l.country_code).toLowerCase();
      };
    } catch (e) {
      msg.textContent = e.message;
      msg.className = 'msg err';
    }
  });

  $('#locSave').addEventListener('click', () => {
    state.loc = {
      location: $('#locName').value.trim() || DEFAULT_LOC.location,
      gl: $('#locGl').value.trim().toLowerCase() || DEFAULT_LOC.gl,
      hl: $('#locHl').value.trim().toLowerCase() || DEFAULT_LOC.hl,
      google_domain: $('#locDomain').value.trim().toLowerCase() || DEFAULT_LOC.google_domain,
    };
    store.set('loc', state.loc);
    $('#locSaved').textContent = 'Saved.';
    setTimeout(() => { $('#locSaved').textContent = ''; }, 2000);
  });

  // Two clicks instead of confirm(): browsers and sandboxed previews often block confirm() silently.
  let wipeTimer = null;
  $('#wipeBtn').addEventListener('click', () => {
    const btn = $('#wipeBtn');
    if (btn.dataset.armed !== '1') {
      btn.dataset.armed = '1';
      btn.textContent = 'Click again to clear everything';
      clearTimeout(wipeTimer);
      wipeTimer = setTimeout(() => { btn.dataset.armed = ''; btn.textContent = 'Clear my data'; }, 4000);
      return;
    }
    clearTimeout(wipeTimer);
    btn.dataset.armed = '';
    store.clearAll();
    state.pantry.length = 0; state.identified.length = 0; state.allergies.length = 0;   // in place, so nothing keeps stale lists
    state.goal = ''; state.loc = Object.assign({}, DEFAULT_LOC);
    $('#goal').value = '';
    ['#pantryInput', '#allergyInput', '#herbUrl', '#pageUrl', '#locQuery'].forEach((id) => { const el = $(id); if (el) el.value = ''; });
    ['#results', '#scanOut', '#pageOut', '#locOut'].forEach((id) => { const el = $(id); if (el) el.innerHTML = ''; });
    ['#formMsg', '#scanMsg', '#pageMsg', '#locMsg', '#locSaved'].forEach((id) => { const el = $(id); if (el) { el.textContent = ''; el.className = 'msg'; } });
    renderShelf();
    renderAllergies();
    renderSuggestions();
    fillSettings();
    btn.textContent = 'Cleared';
    setTimeout(() => { btn.textContent = 'Clear my data'; }, 1800);
    show('brew');
  });

  /* ============ start ============ */
  renderSuggestions();
  renderShelf();
  renderAllergies();
  $('#goal').value = state.goal;
  show(location.hash.slice(1) || 'brew', { scroll: false });
  checkHealth();
})();
