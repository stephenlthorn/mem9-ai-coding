/* tidb-infra-kb · live mission control */

const TYPE_COLOR = { S3: '#FF9F0A', RDS: '#4A90E2', Cloudflare: '#F6821F', Okta: '#0C7DC1', Library: '#30D158' };
const ENV_RING   = { production: '#30D158', staging: '#FFD60A', library: '#BF5AF2' };
const REL_COLOR  = { instantiates: '#BF5AF2', fronts: '#F6821F', redirects_to: '#0C7DC1', uses: '#545b72' };
const DEPTH_COLOR = { 1: '#4A90E2', 2: '#BF5AF2', 3: '#FF453A' };

const $ = id => document.getElementById(id);
const el = (t, c, x) => { const e = document.createElement(t); if (c) e.className = c; if (x !== undefined) e.textContent = x; return e; };
const clear = n => { while (n.firstChild) n.removeChild(n.firstChild); };
const getJSON = p => fetch(p).then(r => r.json());
const postJSON = (p, b) => fetch(p, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(b || {}) }).then(r => r.json());
const shortName = n => n.replace('acme-prod-', '').replace('acme-staging-', '');

let _components = [], _edges = [], _activeEnv = 'all', _lastLogId = -1;

// ── Graph engine (shared by Live + CTE) ──────────────────────────────────────
class GraphSim {
  constructor(id) { this.canvas = $(id); this.raf = null; this.nodes = []; this.edges = []; this.opts = {}; }
  set(nodes, edges, opts = {}) {
    const W = this.canvas.width, H = this.canvas.height, cx = W / 2, cy = H / 2;
    const prev = Object.fromEntries(this.nodes.map(n => [n.name, n]));
    this.nodes = nodes.map((c, i) => {
      const p = prev[c.name];
      if (p) return Object.assign(p, c);
      const a = (i / nodes.length) * Math.PI * 2;
      const r = c.environment === 'library' ? 52 : c.environment === 'production' ? 150 : 100;
      return { ...c, x: cx + r * Math.cos(a) + (Math.random() - 0.5) * 22, y: cy + r * Math.sin(a) + (Math.random() - 0.5) * 22, vx: 0, vy: 0 };
    });
    const names = new Set(this.nodes.map(n => n.name));
    this.edges = edges.filter(e => names.has(e.from_name) && names.has(e.to_name));
    this.opts = opts;
    if (!this.raf) this._loop();
  }
  stop() { if (this.raf) cancelAnimationFrame(this.raf); this.raf = null; }
  _loop() {
    const W = this.canvas.width, H = this.canvas.height, cx = W / 2, cy = H / 2;
    const N = this.nodes, byName = Object.fromEntries(N.map(n => [n.name, n]));
    for (let i = 0; i < N.length; i++) for (let j = i + 1; j < N.length; j++) {
      const a = N[i], b = N[j], dx = a.x - b.x, dy = a.y - b.y, f = 2300 / (dx * dx + dy * dy + 1);
      a.vx += dx * f; a.vy += dy * f; b.vx -= dx * f; b.vy -= dy * f;
    }
    this.edges.forEach(e => {
      const a = byName[e.from_name], b = byName[e.to_name]; if (!a || !b) return;
      const dx = b.x - a.x, dy = b.y - a.y, d = Math.hypot(dx, dy) + 0.001, f = (d - 112) * 0.024;
      a.vx += dx / d * f; a.vy += dy / d * f; b.vx -= dx / d * f; b.vy -= dy / d * f;
    });
    N.forEach(n => {
      n.vx += (cx - n.x) * 0.008; n.vy += (cy - n.y) * 0.008; n.vx *= 0.78; n.vy *= 0.78;
      n.x = Math.max(44, Math.min(W - 44, n.x + n.vx)); n.y = Math.max(26, Math.min(H - 26, n.y + n.vy));
    });
    this._draw(); this.raf = requestAnimationFrame(() => this._loop());
  }
  _draw() {
    const ctx = this.canvas.getContext('2d'), W = this.canvas.width, H = this.canvas.height;
    ctx.clearRect(0, 0, W, H);
    const byName = Object.fromEntries(this.nodes.map(n => [n.name, n]));
    const { highlight, depthMap, dim } = this.opts;
    this.edges.forEach(e => {
      const a = byName[e.from_name], b = byName[e.to_name]; if (!a || !b) return;
      const inHL = highlight && highlight.has(e.from_name) && highlight.has(e.to_name);
      let col = REL_COLOR[e.relationship] || '#545b72';
      if (depthMap && inHL) { const d = Math.min(depthMap[e.from_name] || depthMap[e.to_name] || 1, 3); col = DEPTH_COLOR[d] || col; }
      const ang = Math.atan2(b.y - a.y, b.x - a.x);
      ctx.save();
      ctx.strokeStyle = col; ctx.lineWidth = inHL ? 2.2 : 1.1;
      ctx.globalAlpha = dim ? (inHL ? 0.85 : 0.08) : 0.5; ctx.setLineDash(inHL ? [] : [4, 4]);
      ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
      const tip = { x: b.x - 15 * Math.cos(ang), y: b.y - 15 * Math.sin(ang) };
      ctx.setLineDash([]); ctx.globalAlpha = dim ? (inHL ? 0.9 : 0.1) : 0.65; ctx.fillStyle = col;
      ctx.beginPath(); ctx.moveTo(tip.x, tip.y);
      ctx.lineTo(tip.x - 8 * Math.cos(ang - 0.4), tip.y - 8 * Math.sin(ang - 0.4));
      ctx.lineTo(tip.x - 8 * Math.cos(ang + 0.4), tip.y - 8 * Math.sin(ang + 0.4));
      ctx.closePath(); ctx.fill();
      if (!dim || inHL) { ctx.globalAlpha = dim ? 0.7 : 0.45; ctx.fillStyle = col; ctx.font = '9px sans-serif'; ctx.textAlign = 'left'; ctx.fillText(e.relationship, (a.x + b.x) / 2 + 4, (a.y + b.y) / 2 - 3); }
      ctx.restore();
    });
    this.nodes.forEach(n => {
      const isHL = !highlight || highlight.has(n.name);
      const r = n.environment === 'library' ? 18 : 13;
      const fill = TYPE_COLOR[n.component_type] || '#888';
      let ring = ENV_RING[n.environment] || '#888';
      if (depthMap && depthMap[n.name]) ring = DEPTH_COLOR[Math.min(depthMap[n.name], 3)] || ring;
      const a0 = dim ? (isHL ? 1 : 0.18) : 1;
      ctx.save();
      ctx.globalAlpha = a0 * 0.55; ctx.beginPath(); ctx.arc(n.x, n.y, r + 4, 0, 7); ctx.strokeStyle = ring; ctx.lineWidth = depthMap && depthMap[n.name] ? 3 : 2; ctx.stroke();
      ctx.globalAlpha = a0 * 0.2; ctx.beginPath(); ctx.arc(n.x, n.y, r, 0, 7); ctx.fillStyle = fill; ctx.fill();
      ctx.globalAlpha = a0 * 0.9; ctx.strokeStyle = fill; ctx.lineWidth = 1.5; ctx.stroke();
      ctx.globalAlpha = a0; ctx.fillStyle = fill; ctx.font = `bold ${r === 18 ? 10 : 9}px sans-serif`; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
      ctx.fillText(n.component_type === 'Cloudflare' ? 'CF' : n.component_type === 'Library' ? 'L' : n.component_type[0], n.x, n.y);
      ctx.globalAlpha = a0 * 0.9; ctx.fillStyle = '#e8eaf0'; ctx.font = `${r === 18 ? 10 : 9}px sans-serif`;
      ctx.fillText(shortName(n.name), n.x, n.y + r + 10);
      ctx.restore();
    });
  }
}

const liveGraph = new GraphSim('live-canvas');
const cteGraph = new GraphSim('cte-canvas');

// ── Tabs ─────────────────────────────────────────────────────────────────────
function showTab(name) {
  document.querySelectorAll('.tab').forEach(t => t.classList.toggle('active', t.dataset.tab === name));
  document.querySelectorAll('.view').forEach(v => v.classList.toggle('active', v.dataset.view === name));
  if (name === 'live') liveGraph.set(filtered(), _edges, {});
  if (name === 'cte') initCte();
  if (name === 'search') initSearch();
  if (name === 'scenarios') loadScenarios();
}
document.querySelectorAll('.tab').forEach(t => t.addEventListener('click', () => showTab(t.dataset.tab)));

// ── Live: activity feed ──────────────────────────────────────────────────────
function renderFeed(entries) {
  const c = $('live-feed'); clear(c);
  if (!entries.length) { c.appendChild(el('div', 'feed-empty', 'No activity yet. Launch a CLI and ask it to query the knowledge base.')); return; }
  entries.forEach(e => {
    const dev = (e.developer || 'unknown').replace(/[^a-z-]/gi, '');
    const row = el('div', `feed-row ${e.action === 'created' ? 'is-write' : 'is-query'}`);
    const left = el('div', 'feed-left');
    left.appendChild(el('span', `feed-dev dev-${dev}`, e.developer || '?'));
    left.appendChild(el('span', `feed-action act-${e.action}`, e.action === 'created' ? 'WRITE' : 'QUERY'));
    row.appendChild(left);
    row.appendChild(el('div', 'feed-detail', e.detail || ''));
    row.appendChild(el('span', 'feed-time', (e.created_at || '').slice(11, 19)));
    c.appendChild(row);
  });
}

// ── Live: parity strip ───────────────────────────────────────────────────────
function renderParity(components, missing) {
  const strip = $('parity'); clear(strip);
  const prod = components.filter(c => c.environment === 'production');
  const missingNames = new Set(missing.map(m => m.expected_staging_name));
  $('parity-stat').textContent = missing.length ? `${missing.length} missing in staging` : 'at parity ✓';
  prod.forEach(p => {
    const logical = p.name.replace('acme-prod-', '');
    const stagingName = 'acme-staging-' + logical;
    const present = !missingNames.has(stagingName);
    const row = el('div', 'parity-row');
    row.appendChild(el('span', `parity-mark ${present ? 'ok' : 'gap'}`, present ? '✓' : '✗'));
    row.appendChild(el('span', 'parity-name', logical));
    row.appendChild(el('span', `type-badge type-${p.component_type}`, p.component_type));
    row.appendChild(el('span', 'parity-state', present ? 'in staging' : 'missing'));
    strip.appendChild(row);
  });
}

// ── Env filter (live graph) ──────────────────────────────────────────────────
function filtered() { return _activeEnv === 'all' ? _components : _components.filter(c => c.environment === _activeEnv); }
document.querySelectorAll('.env-btn').forEach(b => b.addEventListener('click', () => {
  document.querySelectorAll('.env-btn').forEach(x => x.classList.remove('active'));
  b.classList.add('active'); _activeEnv = b.dataset.env; liveGraph.set(filtered(), _edges, {});
}));

// ── Load + poll ──────────────────────────────────────────────────────────────
async function loadAll() {
  const [comps, edges, log, missing] = await Promise.all([
    getJSON('/api/components'), getJSON('/api/edges'), getJSON('/api/session-log'), getJSON('/api/missing'),
  ]);
  _components = comps; _edges = edges;
  liveGraph.set(filtered(), edges, {});
  renderFeed(log); renderParity(comps, missing);
  _lastLogId = log.length ? log[0].id : -1;
}

async function poll() {
  const [log, comps, missing] = await Promise.all([
    getJSON('/api/session-log'), getJSON('/api/components'), getJSON('/api/missing'),
  ]);
  renderFeed(log);
  const newest = log.length ? log[0].id : -1;
  const grew = comps.length !== _components.length;
  if (grew || newest !== _lastLogId) {
    _components = comps; _edges = await getJSON('/api/edges');
    if ($('live-canvas').offsetParent !== null) liveGraph.set(filtered(), _edges, {});
    renderParity(comps, missing);
    _lastLogId = newest;
  }
}

// ── CTE ──────────────────────────────────────────────────────────────────────
let _cteMode = 'blast-radius', _cteInit = false;
function initCte() {
  const sel = $('cte-node'); const cur = sel.value;
  clear(sel); _components.forEach(c => sel.appendChild(el('option', null, c.name)));
  sel.value = cur || 'S3Bucket';
  if (!_cteInit) { _cteInit = true; runCte(); }
}
document.querySelectorAll('.cte-btn').forEach(b => b.addEventListener('click', () => {
  document.querySelectorAll('.cte-btn').forEach(x => x.classList.remove('active'));
  b.classList.add('active'); _cteMode = b.dataset.mode; runCte();
}));
$('cte-run').addEventListener('click', runCte);
$('cte-node').addEventListener('change', runCte);

async function runCte() {
  const name = $('cte-node').value || 'S3Bucket';
  const data = await getJSON(`/api/cte/${_cteMode}?name=${encodeURIComponent(name)}`);
  $('cte-sql').textContent = data.sql;
  $('cte-rowcount').textContent = data.rows.length + ' rows';
  $('cte-summary').textContent = `${name} · ${data.nodes.length} nodes`;
  const depthMap = {}; depthMap[name] = 0;
  data.rows.forEach(r => { const far = _cteMode === 'blast-radius' ? r.from_name : r.to_name; depthMap[far] = Math.min(depthMap[far] ?? 99, r.depth); });
  cteGraph.set(_components, _edges, { highlight: new Set(data.nodes), depthMap, dim: true });
  const rows = $('cte-rows'); clear(rows);
  if (!data.rows.length) { rows.appendChild(el('div', 'feed-empty', 'No dependencies at this node.')); return; }
  data.rows.forEach(r => {
    const row = el('div', 'cte-row');
    row.appendChild(el('span', `depth-pill depth-${Math.min(r.depth, 3)}`, 'd' + r.depth));
    const edge = el('span', 'cte-edge');
    edge.appendChild(el('span', null, shortName(r.from_name) + ' '));
    edge.appendChild(el('span', 'cte-rel', '--' + r.relationship + '--> '));
    edge.appendChild(el('span', null, shortName(r.to_name)));
    row.appendChild(edge); rows.appendChild(row);
  });
}

// ── Vector / full-text / hybrid search ───────────────────────────────────────
let _searchMode = 'hybrid', _searchInit = false;

function initSearch() {
  if (_searchInit) return;
  _searchInit = true;
  document.querySelectorAll('[data-smode]').forEach(b => b.addEventListener('click', () => {
    document.querySelectorAll('[data-smode]').forEach(x => x.classList.remove('active'));
    b.classList.add('active'); _searchMode = b.dataset.smode; runSearch();
  }));
  document.querySelectorAll('.preset-btn').forEach(b => b.addEventListener('click', () => {
    $('search-input').value = b.dataset.q; runSearch();
  }));
  $('search-run').addEventListener('click', runSearch);
  $('search-input').addEventListener('keydown', e => { if (e.key === 'Enter') runSearch(); });
  $('search-input').value = 'admin portal access control login';
  runSearch();
}

async function runSearch() {
  const q = ($('search-input').value || '').trim();
  if (!q) return;
  $('search-stat').textContent = 'searching...';
  const data = await getJSON(`/api/search?mode=${_searchMode}&q=${encodeURIComponent(q)}`);
  $('search-sql').textContent = data.sql || '';
  const box = $('search-results'); clear(box);
  if (!data.available) {
    box.appendChild(el('div', 'feed-empty', data.note || 'Search requires the TiDB backend.'));
    $('search-stat').textContent = 'unavailable';
    return;
  }
  $('search-stat').textContent = `${data.results.length} results · ${data.mode}`;
  if (!data.results.length) { box.appendChild(el('div', 'feed-empty', 'No matches.')); return; }
  const mode = data.mode;
  data.results.forEach((r, i) => {
    const semanticOnly = r.in_vector && !r.in_fts;
    const card = el('div', 'search-row' + (mode === 'hybrid' && semanticOnly ? ' semantic-only' : ''));
    const head = el('div', 'search-row-head');
    head.appendChild(el('span', 'search-rank', '#' + (i + 1)));
    head.appendChild(el('span', 'mem-name', r.name));
    head.appendChild(el('span', `type-badge type-${r.component_type}`, r.component_type));
    head.appendChild(el('span', `env-badge env-${r.environment}`, r.environment));
    const sig = el('span', 'search-sigs');
    // Mode-specific chips so the three modes look genuinely different:
    //  vector  -> only the cosine-distance chip (pure semantic ranking)
    //  fts     -> only the keyword chip (pure full-text)
    //  hybrid  -> both signals, with an explicit hit/miss so you can see
    //             which rows the keyword index MISSED but vectors caught.
    if (mode === 'vector') {
      sig.appendChild(el('span', 'sig-chip sig-vec', r.distance != null ? `cosine ${r.distance.toFixed(3)}` : 'vector'));
    } else if (mode === 'fts') {
      sig.appendChild(el('span', 'sig-chip sig-fts', 'keyword match'));
    } else {
      sig.appendChild(el('span', 'sig-chip sig-vec', r.distance != null ? `vector ${r.distance.toFixed(3)}` : 'vector'));
      sig.appendChild(el('span', r.in_fts ? 'sig-chip sig-fts' : 'sig-chip sig-miss',
        r.in_fts ? 'FTS ✓' : 'FTS ✗'));
    }
    head.appendChild(sig);
    card.appendChild(head);
    card.appendChild(el('div', 'search-summary', r.summary || ''));
    if (mode === 'hybrid' && semanticOnly) {
      card.appendChild(el('div', 'semantic-note', '⚡ vector-only - keyword search missed this; semantics found it'));
    }
    box.appendChild(card);
  });
}

// ── Scenarios ─────────────────────────────────────────────────────────────────
async function loadScenarios() {
  const data = await getJSON('/api/scenarios');
  const list = $('scenario-list'); clear(list);
  data.forEach(s => {
    const card = el('div', 'scenario' + (s.headline ? ' headline' : ''));
    const head = el('div', 'sc-head');
    head.appendChild(el('span', 'sc-title', s.title));
    head.appendChild(el('span', `tool-pill tool-${s.tool}`, s.tool));
    if (s.headline) head.appendChild(el('span', 'sc-tag', 'HEADLINE'));
    head.appendChild(el('div', 'sc-task', 'Task: ' + s.task));
    card.appendChild(head);
    const body = el('div', 'sc-body');
    const w = el('div', 'sc-col sc-without'); w.appendChild(el('h4', null, 'Without the graph'));
    const ulW = el('ul'); s.without.forEach(x => ulW.appendChild(el('li', null, x))); w.appendChild(ulW);
    const y = el('div', 'sc-col sc-with'); y.appendChild(el('h4', null, 'With TiDB knowledge graph'));
    const ulY = el('ul'); s.with.forEach(x => ulY.appendChild(el('li', null, x))); y.appendChild(ulY);
    body.appendChild(w); body.appendChild(y); card.appendChild(body);
    const q = el('div', 'sc-query');
    q.appendChild(el('div', 'sc-query-label', 'The query that answers it'));
    const pre = el('pre'); pre.appendChild(el('code', null, s.query)); q.appendChild(pre);
    q.appendChild(el('div', 'sc-result', '→ ' + s.result)); card.appendChild(q);
    const why = el('div', 'sc-why'); why.appendChild(el('b', null, 'Why TiDB: ')); why.appendChild(el('span', null, s.why_tidb)); card.appendChild(why);
    list.appendChild(card);
  });
}

// ── Reset ─────────────────────────────────────────────────────────────────────
$('reset-btn').addEventListener('click', async () => { await postJSON('/api/reset'); await loadAll(); });

// ── Boot ──────────────────────────────────────────────────────────────────────
function applyHash() {
  const h = (location.hash || '').replace('#', '');
  if (['live', 'cte', 'search', 'scenarios'].includes(h)) showTab(h);
}
window.addEventListener('hashchange', applyHash);
getJSON('/api/backend').then(d => { $('backend-name').textContent = '· ' + d.backend; }).catch(() => {});
applyHash();           // deep-link to the right tab immediately (don't wait on data)
loadAll().then(applyHash);
setInterval(poll, 2000);
