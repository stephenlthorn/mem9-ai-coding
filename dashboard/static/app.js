/* mem9-infra-kb · live mission control */

const TYPE_COLOR = {
  S3: '#F5A524', RDS: '#5B8CFF', Cloudflare: '#F97D4B', Okta: '#38BDF8', Library: '#34D399',
  Account: '#2DD4BF', IAM: '#A78BFA', SCP: '#FB7185', OU: '#D4A72C',
};
const ENV_RING   = { production: '#34D399', staging: '#FBBF24', library: '#A78BFA', org: '#2DD4BF' };
const REPO_COLOR = { pulumi: '#5B8CFF', lza: '#2DD4BF' };
const REL_COLOR  = { instantiates: '#A78BFA', fronts: '#F97D4B', redirects_to: '#38BDF8', uses: '#52525e' };
const DEPTH_COLOR = { 1: '#5B8CFF', 2: '#A78BFA', 3: '#FB7185' };

const $ = id => document.getElementById(id);
const el = (t, c, x) => { const e = document.createElement(t); if (c) e.className = c; if (x !== undefined) e.textContent = x; return e; };
const clear = n => { while (n.firstChild) n.removeChild(n.firstChild); };
const getJSON = p => fetch(p).then(r => r.json());
const postJSON = (p, b) => fetch(p, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(b || {}) }).then(r => r.json());
const shortName = n => n.replace('acme-prod-', '').replace('acme-staging-', '').replace('acme-lza-', '');

let _components = [], _edges = [], _allComponents = [], _activeEnv = 'all', _activeRepo = 'all', _lastLogId = -1;

// ── Graph engine (shared by Live + CTE + Teams) ──────────────────────────────
class GraphSim {
  constructor(id) {
    this.canvas = $(id);
    this.raf = null; this.nodes = []; this.edges = []; this.opts = {};
    this.scale = 1; this.ox = 0; this.oy = 0;
    this.settleFrames = 0;
    this.drag = null; this.pan = null;
    if (this.canvas) this._wire();
  }
  set(nodes, edges, opts = {}) {
    if (!this.canvas) return;
    const W = this.canvas.width, H = this.canvas.height, cx = W / 2, cy = H / 2;
    const prev = Object.fromEntries(this.nodes.map(n => [n.name, n]));
    this.nodes = nodes.map((c, i) => {
      const p = prev[c.name];
      if (p) return Object.assign(p, c);
      // phyllotaxis (sunflower) spawn: golden-angle spread so no two nodes
      // start on top of each other — eliminates label collisions on load.
      const a = i * 2.399963229728653;
      const rr = 34 + 120 * Math.sqrt((i + 0.5) / Math.max(1, nodes.length));
      return { ...c, x: cx + rr * Math.cos(a), y: cy + rr * Math.sin(a), vx: 0, vy: 0, fixed: false };
    });
    const names = new Set(this.nodes.map(n => n.name));
    this.edges = edges.filter(e => names.has(e.from_name) && names.has(e.to_name));
    this.opts = opts;
    this._wake();
  }
  stop() { if (this.raf) cancelAnimationFrame(this.raf); this.raf = null; }
  _wake() { this.settleFrames = 0; if (!this.raf) this.raf = requestAnimationFrame(() => this._loop()); }

  _toWorld(e) {
    const rect = this.canvas.getBoundingClientRect();
    const cxp = (e.clientX - rect.left) * (this.canvas.width / rect.width);
    const cyp = (e.clientY - rect.top) * (this.canvas.height / rect.height);
    return { cxp, cyp, x: (cxp - this.ox) / this.scale, y: (cyp - this.oy) / this.scale };
  }
  _wire() {
    const c = this.canvas;
    c.style.cursor = 'grab';
    c.addEventListener('wheel', e => {
      e.preventDefault();
      const p = this._toWorld(e);
      const k = Math.exp(-e.deltaY * 0.0015);
      const ns = Math.max(0.4, Math.min(4, this.scale * k));
      this.ox = p.cxp - p.x * ns; this.oy = p.cyp - p.y * ns; this.scale = ns;
      this._wake();
    }, { passive: false });
    c.addEventListener('mousedown', e => {
      const p = this._toWorld(e);
      const hit = this.nodes.find(n => Math.hypot(p.x - n.x, p.y - n.y) < (n.environment === 'library' ? 22 : 17));
      if (hit) { this.drag = hit; hit.fixed = true; c.style.cursor = 'grabbing'; }
      else { this.pan = { x: p.cxp, y: p.cyp, ox: this.ox, oy: this.oy }; c.style.cursor = 'grabbing'; }
      this._wake();
    });
    window.addEventListener('mousemove', e => {
      if (this.drag) { const p = this._toWorld(e); this.drag.x = p.x; this.drag.y = p.y; this.drag.vx = this.drag.vy = 0; this._wake(); }
      else if (this.pan) { const p = this._toWorld(e); this.ox = this.pan.ox + (p.cxp - this.pan.x); this.oy = this.pan.oy + (p.cyp - this.pan.y); this._wake(); }
    });
    window.addEventListener('mouseup', () => { if (this.drag || this.pan) c.style.cursor = 'grab'; this.drag = null; this.pan = null; });
    c.addEventListener('dblclick', () => { this.scale = 1; this.ox = 0; this.oy = 0; this.nodes.forEach(n => n.fixed = false); this._wake(); });
  }
  _loop() {
    const W = this.canvas.width, H = this.canvas.height, cx = W / 2, cy = H / 2;
    const N = this.nodes, byName = Object.fromEntries(N.map(n => [n.name, n]));
    let energy = 0;
    if (!this.drag) {
      for (let i = 0; i < N.length; i++) for (let j = i + 1; j < N.length; j++) {
        const a = N[i], b = N[j], dx = a.x - b.x, dy = a.y - b.y, f = 4200 / (dx * dx + dy * dy + 1);
        a.vx += dx * f; a.vy += dy * f; b.vx -= dx * f; b.vy -= dy * f;
      }
      this.edges.forEach(e => {
        const a = byName[e.from_name], b = byName[e.to_name]; if (!a || !b) return;
        const dx = b.x - a.x, dy = b.y - a.y, d = Math.hypot(dx, dy) + 0.001, f = (d - 134) * 0.022;
        a.vx += dx / d * f; a.vy += dy / d * f; b.vx -= dx / d * f; b.vy -= dy / d * f;
      });
      N.forEach(n => {
        if (n.fixed) { n.vx = n.vy = 0; return; }
        n.vx += (cx - n.x) * 0.006; n.vy += (cy - n.y) * 0.006; n.vx *= 0.8; n.vy *= 0.8;
        n.x = Math.max(44, Math.min(W - 44, n.x + n.vx)); n.y = Math.max(26, Math.min(H - 26, n.y + n.vy));
        energy += n.vx * n.vx + n.vy * n.vy;
      });
    }
    this._draw();
    if (!this.drag && !this.pan && energy < 0.05) this.settleFrames++; else this.settleFrames = 0;
    if (this.settleFrames > 20) { this.raf = null; return; }
    this.raf = requestAnimationFrame(() => this._loop());
  }
  _draw() {
    const ctx = this.canvas.getContext('2d'), W = this.canvas.width, H = this.canvas.height;
    ctx.clearRect(0, 0, W, H);
    ctx.save();
    ctx.translate(this.ox, this.oy); ctx.scale(this.scale, this.scale);
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
      const isLza = n.repo === 'lza';
      ctx.save();
      // outer ring — dashed for lza to distinguish repos visually
      ctx.globalAlpha = a0 * 0.55;
      ctx.beginPath(); ctx.arc(n.x, n.y, r + 4, 0, 7);
      ctx.strokeStyle = ring; ctx.lineWidth = depthMap && depthMap[n.name] ? 3 : 2;
      ctx.setLineDash(isLza ? [4, 3] : []);
      ctx.stroke();
      ctx.setLineDash([]);
      ctx.globalAlpha = a0 * 0.2; ctx.beginPath(); ctx.arc(n.x, n.y, r, 0, 7); ctx.fillStyle = fill; ctx.fill();
      ctx.globalAlpha = a0 * 0.9; ctx.strokeStyle = fill; ctx.lineWidth = 1.5; ctx.stroke();
      ctx.globalAlpha = a0; ctx.fillStyle = fill; ctx.font = `bold ${r === 18 ? 10 : 9}px sans-serif`; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
      const typeLabel = n.component_type === 'Cloudflare' ? 'CF' : n.component_type === 'Library' ? 'L' : (n.component_type || '?')[0];
      ctx.fillText(typeLabel, n.x, n.y);
      ctx.globalAlpha = a0 * 0.9; ctx.fillStyle = '#e8eaf0'; ctx.font = `${r === 18 ? 10 : 9}px sans-serif`;
      ctx.fillText(shortName(n.name), n.x, n.y + r + 10);
      // repo dot below name for multi-repo graphs
      if (this.opts.showRepo) {
        ctx.globalAlpha = a0 * 0.7; ctx.fillStyle = REPO_COLOR[n.repo] || '#888';
        ctx.beginPath(); ctx.arc(n.x, n.y + r + 20, 3, 0, 7); ctx.fill();
      }
      ctx.restore();
    });
    ctx.restore();
  }
}

const liveGraph  = new GraphSim('live-canvas');
const cteGraph   = new GraphSim('cte-canvas');
const teamsGraph = new GraphSim('teams-canvas');

// ── Tabs ─────────────────────────────────────────────────────────────────────
function showTab(name) {
  document.querySelectorAll('.tab').forEach(t => t.classList.toggle('active', t.dataset.tab === name));
  document.querySelectorAll('.view').forEach(v => v.classList.toggle('active', v.dataset.view === name));
  if (name === 'live')   liveGraph.set(filteredLive(), _edges, {});
  if (name === 'teams')  renderTeamsGraph();
  if (name === 'cte')    initCte();
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
    const devLabel = e.developer === 'seed' ? 'baseline' : (e.developer || '?');
    const row = el('div', `feed-row ${e.action === 'created' ? 'is-write' : 'is-query'}`);
    const left = el('div', 'feed-left');
    left.appendChild(el('span', `feed-dev dev-${dev}`, devLabel));
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

// ── Env filter (live graph) ───────────────────────────────────────────────────
function filteredLive() {
  return _activeEnv === 'all' ? _allComponents : _allComponents.filter(c => c.environment === _activeEnv);
}
document.querySelectorAll('.env-btn').forEach(b => b.addEventListener('click', () => {
  document.querySelectorAll('.env-btn').forEach(x => x.classList.remove('active'));
  b.classList.add('active'); _activeEnv = b.dataset.env; liveGraph.set(filteredLive(), _edges, {});
}));

// ── Teams tab: repo filter + graph ────────────────────────────────────────────
let _teamsActiveRepo = 'all';

function filteredTeams() {
  if (_teamsActiveRepo === 'all') return _allComponents;
  return _allComponents.filter(c => c.repo === _teamsActiveRepo);
}

function renderTeamsGraph() {
  teamsGraph.set(filteredTeams(), _edges, { showRepo: true });
}

document.querySelectorAll('.repo-btn').forEach(b => b.addEventListener('click', () => {
  document.querySelectorAll('.repo-btn').forEach(x => x.classList.remove('active'));
  b.classList.add('active'); _teamsActiveRepo = b.dataset.repo; renderTeamsGraph();
}));

async function loadTeamsTab() {
  try {
    const data = await getJSON('/api/repos');
    if (data.repos) {
      data.repos.forEach(r => {
        const el2 = $(`repo-count-${r.repo}`);
        if (el2) el2.textContent = r.component_count;
      });
    }
    const hdr = $('header-team-repos');
    if (hdr && data.team && data.repos) {
      const names = data.repos.map(r => r.repo).join(' + ');
      hdr.textContent = `${data.team} · ${names}`;
    }
  } catch (e) { /* non-critical */ }
}

// ── Load + poll ──────────────────────────────────────────────────────────────
async function loadAll() {
  const [allComps, pulComps, edges, log, missing] = await Promise.all([
    getJSON('/api/all-components'),
    getJSON('/api/components'),
    getJSON('/api/edges'),
    getJSON('/api/session-log'),
    getJSON('/api/missing'),
  ]);
  _allComponents = allComps;
  _components = pulComps;  // pulumi-only, used for parity + CTE
  _edges = edges;
  liveGraph.set(filteredLive(), edges, {});
  renderFeed(log); renderParity(pulComps, missing);
  _lastLogId = log.length ? log[0].id : -1;
}

async function poll() {
  const [log, allComps, pulComps, missing] = await Promise.all([
    getJSON('/api/session-log'), getJSON('/api/all-components'), getJSON('/api/components'), getJSON('/api/missing'),
  ]);
  const newest = log.length ? log[0].id : -1;
  const grew = allComps.length !== _allComponents.length;
  if (newest !== _lastLogId) renderFeed(log);
  if (grew || newest !== _lastLogId) {
    _allComponents = allComps; _components = pulComps;
    _edges = await getJSON('/api/edges');
    if (grew && $('live-canvas').offsetParent !== null) liveGraph.set(filteredLive(), _edges, {});
    if (grew && $('teams-canvas').offsetParent !== null) renderTeamsGraph();
    renderParity(pulComps, missing);
    _lastLogId = newest;
  }
}

// ── CTE ──────────────────────────────────────────────────────────────────────
let _cteMode = 'blast-radius', _cteInit = false;
function initCte() {
  const sel = $('cte-node'); const cur = sel.value;
  clear(sel); _allComponents.forEach(c => sel.appendChild(el('option', null, c.name)));
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
  $('cte-sql').textContent = data.note || '';
  $('cte-rowcount').textContent = data.rows.length + ' rows';
  $('cte-summary').textContent = `${name} · ${data.nodes.length} nodes`;
  const depthMap = {}; depthMap[name] = 0;
  data.rows.forEach(r => { const far = _cteMode === 'blast-radius' ? r.from_name : r.to_name; depthMap[far] = Math.min(depthMap[far] ?? 99, r.depth); });
  cteGraph.set(_allComponents, _edges, { highlight: new Set(data.nodes), depthMap, dim: true });
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
  $('search-sql').textContent = data.note || '';
  const box = $('search-results'); clear(box);
  if (!data.available) {
    box.appendChild(el('div', 'feed-empty', data.note || 'Search unavailable.'));
    $('search-stat').textContent = 'unavailable';
    return;
  }
  $('search-stat').textContent = `${data.results.length} results · ${data.mode}`;
  if (!data.results.length) { box.appendChild(el('div', 'feed-empty', 'No matches.')); return; }
  const mode = data.mode;
  data.results.forEach((r, i) => {
    const card = el('div', 'search-row');
    const head = el('div', 'search-row-head');
    head.appendChild(el('span', 'search-rank', '#' + (i + 1)));
    head.appendChild(el('span', 'mem-name', r.name));
    head.appendChild(el('span', `type-badge type-${r.component_type}`, r.component_type));
    head.appendChild(el('span', `env-badge env-${r.environment}`, r.environment));
    if (r.repo) head.appendChild(el('span', `repo-badge repo-${r.repo}`, r.repo));
    const sig = el('span', 'search-sigs');
    if (r.hybrid_score != null) sig.appendChild(el('span', 'sig-chip sig-vec', `score ${r.hybrid_score.toFixed(3)}`));
    head.appendChild(sig);
    card.appendChild(head);
    card.appendChild(el('div', 'search-summary', r.summary || ''));
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
    const y = el('div', 'sc-col sc-with'); y.appendChild(el('h4', null, 'With mem9 knowledge graph'));
    const ulY = el('ul'); s.with.forEach(x => ulY.appendChild(el('li', null, x))); y.appendChild(ulY);
    body.appendChild(w); body.appendChild(y); card.appendChild(body);
    const q = el('div', 'sc-query');
    q.appendChild(el('div', 'sc-query-label', 'The query that answers it'));
    const pre = el('pre'); pre.appendChild(el('code', null, s.query)); q.appendChild(pre);
    q.appendChild(el('div', 'sc-result', '→ ' + s.result)); card.appendChild(q);
    const why = el('div', 'sc-why'); why.appendChild(el('b', null, 'Why mem9: ')); why.appendChild(el('span', null, s.why_tidb)); card.appendChild(why);
    list.appendChild(card);
  });
}

// ── Reset ─────────────────────────────────────────────────────────────────────
$('reset-btn').addEventListener('click', async () => {
  if (!confirm('Reset the demo? This deletes everything the agents wrote and restores the clean baseline (4 staging components missing again).')) return;
  $('reset-btn').textContent = 'Resetting…';
  await postJSON('/api/reset');
  await loadAll();
  if (document.querySelector('.view[data-view="live"]').classList.contains('active')) liveGraph.set(filteredLive(), _edges, {});
  $('reset-btn').textContent = 'Reset KB';
});

// ── Boot ──────────────────────────────────────────────────────────────────────
function applyHash() {
  const h = (location.hash || '').replace('#', '');
  if (['scenario', 'teams', 'architecture', 'sysprompt', 'live', 'cte', 'search', 'scenarios'].includes(h)) showTab(h);
}
window.addEventListener('hashchange', applyHash);
getJSON('/api/backend').then(() => { $('backend-name').textContent = 'TiDB Cloud'; }).catch(() => {});
loadTeamsTab();
applyHash();
loadAll().then(applyHash);
setInterval(poll, 2000);
