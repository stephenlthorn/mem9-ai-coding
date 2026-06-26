/* mem9-infra-kb · application dashboard */

const TYPE_COLOR = {
  S3: '#F5A524', RDS: '#5B8CFF', Cloudflare: '#F97D4B', Okta: '#38BDF8', Library: '#34D399',
  Account: '#2DD4BF', IAM: '#A78BFA', SCP: '#FB7185', OU: '#D4A72C',
  KMS: '#F5A524', Certificate: '#34D399', Service: '#38BDF8',
};
const TYPE_GLYPH = {
  S3: 'S3', RDS: 'RD', Cloudflare: 'CF', Okta: 'OK', Library: 'L', Account: 'AC',
  IAM: 'IAM', SCP: 'SCP', OU: 'OU', KMS: 'KM', Certificate: 'TLS', Service: 'SV',
};
const ENV_RING   = { production: '#34D399', staging: '#FBBF24', library: '#A78BFA', org: '#2DD4BF' };
const REPO_COLOR = { pulumi: '#5B8CFF', lza: '#2DD4BF' };
const REL_COLOR  = { instantiates: '#A78BFA', fronts: '#F97D4B', redirects_to: '#38BDF8', uses: '#52525e' };
const DEPTH_COLOR = { 0: '#2DD4BF', 1: '#5B8CFF', 2: '#A78BFA', 3: '#FB7185' };
const depthColor = d => DEPTH_COLOR[Math.min(d, 3)] || '#FB7185';
const SVGNS = 'http://www.w3.org/2000/svg';

const $ = id => document.getElementById(id);
const el = (t, c, x) => { const e = document.createElement(t); if (c) e.className = c; if (x !== undefined) e.textContent = x; return e; };
const clear = n => { while (n && n.firstChild) n.removeChild(n.firstChild); };
const getJSON = p => fetch(p).then(r => r.json());
const postJSON = (p, b) => fetch(p, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(b || {}) }).then(r => r.json());
const shortName = n => (n || '').replace('acme-prod-', '').replace('acme-staging-', '').replace('acme-lza-', '');
const cssEsc = s => (window.CSS && CSS.escape) ? CSS.escape(s) : String(s).replace(/"/g, '\\"');

let _components = [], _edges = [], _allComponents = [], _activeEnv = 'all', _lastLogId = -1;

// ── Live knowledge-graph engine (canvas, settling force layout) ───────────────
class GraphSim {
  constructor(id) {
    this.canvas = $(id);
    this.raf = null; this.nodes = []; this.edges = []; this.opts = {};
    this.scale = 1; this.ox = 0; this.oy = 0; this.settleFrames = 0;
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
    this.edges.forEach(e => {
      const a = byName[e.from_name], b = byName[e.to_name]; if (!a || !b) return;
      const col = REL_COLOR[e.relationship] || '#545b72';
      const ang = Math.atan2(b.y - a.y, b.x - a.x);
      ctx.save();
      ctx.strokeStyle = col; ctx.lineWidth = 1.1; ctx.globalAlpha = 0.5; ctx.setLineDash([4, 4]);
      ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
      const tip = { x: b.x - 15 * Math.cos(ang), y: b.y - 15 * Math.sin(ang) };
      ctx.setLineDash([]); ctx.globalAlpha = 0.65; ctx.fillStyle = col;
      ctx.beginPath(); ctx.moveTo(tip.x, tip.y);
      ctx.lineTo(tip.x - 8 * Math.cos(ang - 0.4), tip.y - 8 * Math.sin(ang - 0.4));
      ctx.lineTo(tip.x - 8 * Math.cos(ang + 0.4), tip.y - 8 * Math.sin(ang + 0.4));
      ctx.closePath(); ctx.fill();
      ctx.restore();
    });
    this.nodes.forEach(n => {
      const r = n.environment === 'library' ? 18 : 13;
      const fill = TYPE_COLOR[n.component_type] || '#888';
      const ring = ENV_RING[n.environment] || '#888';
      const isLza = n.repo === 'lza';
      ctx.save();
      ctx.globalAlpha = 0.55; ctx.beginPath(); ctx.arc(n.x, n.y, r + 4, 0, 7);
      ctx.strokeStyle = ring; ctx.lineWidth = 2; ctx.setLineDash(isLza ? [4, 3] : []); ctx.stroke(); ctx.setLineDash([]);
      ctx.globalAlpha = 0.2; ctx.beginPath(); ctx.arc(n.x, n.y, r, 0, 7); ctx.fillStyle = fill; ctx.fill();
      ctx.globalAlpha = 0.9; ctx.strokeStyle = fill; ctx.lineWidth = 1.5; ctx.stroke();
      ctx.globalAlpha = 1; ctx.fillStyle = fill; ctx.font = `bold ${r === 18 ? 10 : 9}px sans-serif`; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
      ctx.fillText((TYPE_GLYPH[n.component_type] || (n.component_type || '?')[0]).slice(0, 2), n.x, n.y);
      ctx.globalAlpha = 0.9; ctx.fillStyle = '#e8eaf0'; ctx.font = `${r === 18 ? 10 : 9}px sans-serif`;
      ctx.fillText(shortName(n.name), n.x, n.y + r + 10);
      ctx.restore();
    });
    ctx.restore();
  }
}

const liveGraph = new GraphSim('live-canvas');

// ── Tabs ──────────────────────────────────────────────────────────────────────
const TABS = ['live', 'cte', 'search', 'sysprompt'];
function showTab(name) {
  document.querySelectorAll('.tab').forEach(t => t.classList.toggle('active', t.dataset.tab === name));
  document.querySelectorAll('.view').forEach(v => v.classList.toggle('active', v.dataset.view === name));
  if (name === 'live') liveGraph.set(filteredLive(), _edges, {});
  if (name === 'cte') initDeps();
  if (name === 'search') initSearch();
}
document.querySelectorAll('.tab').forEach(t => t.addEventListener('click', () => { showTab(t.dataset.tab); location.hash = t.dataset.tab; }));

// ── Live: activity feed ───────────────────────────────────────────────────────
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

// ── Live: parity strip ────────────────────────────────────────────────────────
function renderParity(components, missing) {
  const strip = $('parity'); clear(strip);
  const prod = components.filter(c => c.environment === 'production');
  const missingNames = new Set(missing.map(m => m.expected_staging_name));
  $('parity-stat').textContent = missing.length ? `${missing.length} missing in staging` : 'at parity ✓';
  prod.forEach(p => {
    const logical = p.name.replace('acme-prod-', '');
    const present = !missingNames.has('acme-staging-' + logical);
    const row = el('div', 'parity-row');
    row.appendChild(el('span', `parity-mark ${present ? 'ok' : 'gap'}`, present ? '✓' : '✗'));
    row.appendChild(el('span', 'parity-name', logical));
    row.appendChild(el('span', `type-badge type-${p.component_type}`, p.component_type));
    row.appendChild(el('span', 'parity-state', present ? 'in staging' : 'missing'));
    strip.appendChild(row);
  });
}

// ── Live: env filter ──────────────────────────────────────────────────────────
function filteredLive() {
  return _activeEnv === 'all' ? _allComponents : _allComponents.filter(c => c.environment === _activeEnv);
}
document.querySelectorAll('.env-btn').forEach(b => b.addEventListener('click', () => {
  document.querySelectorAll('.env-btn').forEach(x => x.classList.remove('active'));
  b.classList.add('active'); _activeEnv = b.dataset.env; liveGraph.set(filteredLive(), _edges, {});
}));

// ── Load + poll (live) ────────────────────────────────────────────────────────
async function loadAll() {
  const [allComps, pulComps, edges, log, missing] = await Promise.all([
    getJSON('/api/all-components'), getJSON('/api/components'), getJSON('/api/edges'),
    getJSON('/api/session-log'), getJSON('/api/missing'),
  ]);
  _allComponents = allComps; _components = pulComps; _edges = edges;
  liveGraph.set(filteredLive(), edges, {});
  renderFeed(log); renderParity(pulComps, missing);
  _lastLogId = log.length ? log[0].id : -1;
}

async function poll() {
  if (!document.querySelector('.view[data-view="live"]').classList.contains('active')) return;
  const [log, allComps, pulComps, missing] = await Promise.all([
    getJSON('/api/session-log'), getJSON('/api/all-components'), getJSON('/api/components'), getJSON('/api/missing'),
  ]);
  const newest = log.length ? log[0].id : -1;
  const grew = allComps.length !== _allComponents.length;
  if (newest !== _lastLogId) renderFeed(log);
  if (grew || newest !== _lastLogId) {
    _allComponents = allComps; _components = pulComps; _edges = await getJSON('/api/edges');
    if (grew && $('live-canvas').offsetParent !== null) liveGraph.set(filteredLive(), _edges, {});
    renderParity(pulComps, missing);
    _lastLogId = newest;
  }
}

// ── DEPENDENCIES: the Dependency Rail ─────────────────────────────────────────
let _depMode = 'blast-radius', _depRoot = 'KmsKey', _depInit = false, _depData = null;
const SOURCE_W = 200;

function initDeps() {
  if (!_depInit) {
    _depInit = true;
    const sel = $('cte-node');
    const names = [..._allComponents].map(c => c.name).sort();
    clear(sel);
    names.forEach(n => sel.appendChild(el('option', null, n)));
    sel.value = names.includes(_depRoot) ? _depRoot : names[0];
    _depRoot = sel.value;
    sel.addEventListener('change', () => { _depRoot = sel.value; runRail(); });
    const modeBtns = document.querySelectorAll('.dep-controls .seg [data-mode]');
    modeBtns.forEach(b => b.addEventListener('click', () => {
      modeBtns.forEach(x => x.classList.remove('active'));
      b.classList.add('active'); _depMode = b.dataset.mode; runRail();
    }));
    document.querySelectorAll('.ex-btn').forEach(b => b.addEventListener('click', () => {
      _depRoot = b.dataset.node; _depMode = b.dataset.mode;
      $('cte-node').value = _depRoot;
      modeBtns.forEach(x => x.classList.toggle('active', x.dataset.mode === _depMode));
      runRail();
    }));
    window.addEventListener('resize', () => { if (_depData) drawConnectors(); });
  }
  runRail();
}

async function runRail() {
  const data = await getJSON(`/api/cte/${_depMode}?name=${encodeURIComponent(_depRoot)}`);
  _depData = data;
  renderRail(data);
}

function renderRail(data) {
  const rail = $('rail'); clear(rail);
  const meta = {}; (data.nodes_meta || []).forEach(n => meta[n.name] = n);
  const depthOf = {}; (data.nodes_meta || []).forEach(n => depthOf[n.name] = n.depth);
  const maxDepth = data.max_depth || 0;

  const dir = _depMode === 'blast-radius' ? 'upstream' : 'downstream';
  const stat = $('dep-stat'); clear(stat);
  stat.appendChild(el('b', null, String(data.count)));
  stat.appendChild(document.createTextNode(` component${data.count === 1 ? '' : 's'} · `));
  stat.appendChild(el('b', null, String(maxDepth)));
  stat.appendChild(document.createTextNode(` hop${maxDepth === 1 ? '' : 's'} · ${dir}`));
  $('cte-note').textContent = data.note || '';

  // adjacency: parent (shallower) -> child (deeper); keep real arc direction
  const parentOf = {}, relOf = {};
  (data.rows || []).forEach(r => {
    const a = r.from_name, b = r.to_name;
    if (depthOf[a] == null || depthOf[b] == null) return;
    let parent, child;
    if (depthOf[b] > depthOf[a]) { parent = a; child = b; }
    else if (depthOf[a] > depthOf[b]) { parent = b; child = a; }
    else return;
    (parentOf[child] = parentOf[child] || []).push(parent);
    relOf[parent + '' + child] = { rel: r.relationship, from: a, to: b };
  });

  const lanes = []; for (let d = 0; d <= maxDepth; d++) lanes[d] = [];
  (data.nodes_meta || []).forEach(n => { if (lanes[n.depth]) lanes[n.depth].push(n.name); });
  for (let d = 1; d <= maxDepth; d++) {
    lanes[d].sort((x, y) => {
      const px = (parentOf[x] && parentOf[x][0]) || '', py = (parentOf[y] && parentOf[y][0]) || '';
      const ix = lanes[d - 1].indexOf(px), iy = lanes[d - 1].indexOf(py);
      if (ix !== iy) return ix - iy;
      return x.localeCompare(y);
    });
  }

  rail.style.gridTemplateColumns = `${SOURCE_W}px repeat(${maxDepth}, minmax(168px, 220px))`;

  const spineNodes = new Set((data.paths && data.paths[0]) || []);
  const spineEdges = new Set();
  const sp = (data.paths && data.paths[0]) || [];
  for (let i = 0; i < sp.length - 1; i++) spineEdges.add(edgeKey(sp[i], sp[i + 1], depthOf));

  function card(name, isRoot) {
    const m = meta[name] || {};
    const d = depthOf[name] || 0;
    const c = el('div', 'dep-card' + (isRoot ? ' is-root' : '') + (m.repo === 'lza' ? ' is-lza' : ''));
    c.dataset.name = name;
    c.style.setProperty('--depth-color', depthColor(d));
    if (!spineNodes.has(name) && !isRoot) c.classList.add('off-spine');
    const top = el('div', 'dc-top');
    top.appendChild(el('span', 'dc-depth', isRoot ? (_depMode === 'blast-radius' ? 'root' : 'src') : 'd' + d));
    const tok = el('span', 'dc-type');
    const dot = el('span', 'dc-dot'); dot.style.background = TYPE_COLOR[m.type] || '#888'; tok.appendChild(dot);
    tok.appendChild(el('span', 'dc-tok', TYPE_GLYPH[m.type] || (m.type || '?').slice(0, 2)));
    top.appendChild(tok);
    c.appendChild(top);
    c.appendChild(el('div', 'dc-name', shortName(name)));
    c.appendChild(el('div', 'dc-env', `${m.env || ''}${m.repo ? ' · ' + m.repo : ''}`));
    c.addEventListener('mouseenter', () => highlightPath(name, parentOf));
    c.addEventListener('mouseleave', restoreSpine);
    c.addEventListener('click', () => { _depRoot = name; $('cte-node').value = name; runRail(); });
    return c;
  }

  const srcRail = el('div', 'source-rail');
  srcRail.appendChild(card(data.root, true));
  if ((data.count || 0) === 0) srcRail.appendChild(el('div', 'rail-empty', _depMode === 'blast-radius' ? 'Nothing depends on this — safe to change.' : 'No dependencies — this is a leaf.'));
  rail.appendChild(srcRail);

  for (let d = 1; d <= maxDepth; d++) {
    const lane = el('div', 'lane');
    const head = el('div', 'lane-head');
    head.style.color = depthColor(d);
    head.appendChild(el('span', 'lh-hop', 'hop ' + d));
    head.appendChild(el('span', 'lh-count', String(lanes[d].length)));
    lane.appendChild(head);
    const stack = el('div', 'lane-stack');
    lanes[d].forEach(n => stack.appendChild(card(n, false)));
    lane.appendChild(stack);
    rail.appendChild(lane);
  }

  rail._graph = { parentOf, relOf, depthOf, spineEdges };
  requestAnimationFrame(() => drawConnectors());
  renderTrace(data, relOf, depthOf);
}

function edgeKey(a, b, depthOf) {
  if ((depthOf[a] || 0) <= (depthOf[b] || 0)) return a + '' + b;
  return b + '' + a;
}

function drawConnectors() {
  const rail = $('rail'); if (!rail || !rail._graph) return;
  const { parentOf, relOf, depthOf, spineEdges } = rail._graph;
  const old = rail.querySelector('svg.rail-edges'); if (old) old.remove();
  const railRect = rail.getBoundingClientRect();
  const W = rail.scrollWidth, H = rail.scrollHeight;
  const svg = document.createElementNS(SVGNS, 'svg');
  svg.setAttribute('class', 'rail-edges');
  svg.setAttribute('width', W); svg.setAttribute('height', H);
  svg.setAttribute('viewBox', `0 0 ${W} ${H}`);

  const defs = document.createElementNS(SVGNS, 'defs');
  const marker = document.createElementNS(SVGNS, 'marker');
  marker.setAttribute('id', 'rail-arrow');
  marker.setAttribute('markerWidth', '8'); marker.setAttribute('markerHeight', '8');
  marker.setAttribute('refX', '6.5'); marker.setAttribute('refY', '3'); marker.setAttribute('orient', 'auto');
  const mp = document.createElementNS(SVGNS, 'path');
  mp.setAttribute('d', 'M0,0 L6.5,3 L0,6 Z'); mp.setAttribute('fill', 'context-stroke');
  marker.appendChild(mp); defs.appendChild(marker); svg.appendChild(defs);

  const box = name => {
    const e = rail.querySelector(`.dep-card[data-name="${cssEsc(name)}"]`);
    if (!e) return null;
    const r = e.getBoundingClientRect();
    return {
      left: r.left - railRect.left + rail.scrollLeft,
      right: r.right - railRect.left + rail.scrollLeft,
      midY: r.top - railRect.top + rail.scrollTop + r.height / 2,
    };
  };

  Object.keys(parentOf).forEach(child => {
    parentOf[child].forEach(parent => {
      const p = box(parent), c = box(child); if (!p || !c) return;
      const info = relOf[parent + '' + child] || {};
      const childDepth = depthOf[child] || 1;
      const col = depthColor(childDepth);
      const isSpine = spineEdges.has(parent + '' + child);
      const path = document.createElementNS(SVGNS, 'path');
      let d;
      if (info.from === parent) {
        d = `M ${p.right} ${p.midY} C ${p.right + 56} ${p.midY}, ${c.left - 56} ${c.midY}, ${c.left} ${c.midY}`;
      } else {
        d = `M ${c.left} ${c.midY} C ${c.left - 56} ${c.midY}, ${p.right + 56} ${p.midY}, ${p.right} ${p.midY}`;
      }
      path.setAttribute('d', d);
      path.setAttribute('fill', 'none');
      path.setAttribute('stroke', col);
      path.setAttribute('stroke-width', isSpine ? 2 : 1.2);
      path.setAttribute('marker-end', 'url(#rail-arrow)');
      path.setAttribute('class', 'rail-edge' + (isSpine ? ' is-spine' : ' off-spine'));
      path.dataset.edge = parent + '' + child;
      if (childDepth >= 4) path.setAttribute('stroke-dasharray', '5 4');
      svg.appendChild(path);
      const t = document.createElementNS(SVGNS, 'text');
      t.setAttribute('x', (p.right + c.left) / 2);
      t.setAttribute('y', (p.midY + c.midY) / 2 - 4);
      t.setAttribute('class', 'rail-verb' + (isSpine ? ' is-spine' : ' off-spine'));
      t.setAttribute('fill', col);
      t.textContent = info.rel || '';
      t.dataset.edge = parent + '' + child;
      svg.appendChild(t);
    });
  });
  rail.insertBefore(svg, rail.firstChild);
}

function highlightPath(name, parentOf) {
  const rail = $('rail');
  const nodes = new Set([name]); const edges = new Set();
  let frontier = [name], guard = 0;
  while (frontier.length && guard++ < 80) {
    const next = [];
    frontier.forEach(n => (parentOf[n] || []).forEach(p => {
      edges.add(p + '' + n);
      if (!nodes.has(p)) { nodes.add(p); next.push(p); }
    }));
    frontier = next;
  }
  rail.querySelectorAll('.dep-card').forEach(c => {
    const on = nodes.has(c.dataset.name);
    c.classList.toggle('hl', on); c.classList.toggle('dim', !on);
  });
  rail.querySelectorAll('.rail-edge, .rail-verb').forEach(p => {
    const on = edges.has(p.dataset.edge);
    p.classList.toggle('hl', on); p.classList.toggle('dim', !on);
  });
}

function restoreSpine() {
  const rail = $('rail');
  rail.querySelectorAll('.dep-card, .rail-edge, .rail-verb').forEach(e => e.classList.remove('hl', 'dim'));
}

function renderTrace(data, relOf, depthOf) {
  const box = $('trace-chains'); clear(box);
  const paths = (data.paths || []).slice(0, 3);
  if (!paths.length) { box.appendChild(el('div', 'feed-empty', 'No chains.')); return; }
  paths.forEach((p, idx) => {
    const row = el('div', 'trace-sentence' + (idx === 0 ? ' is-spine' : ''));
    row.appendChild(el('span', 'trace-hops', (p.length - 1) + 'h'));
    p.forEach((n, i) => {
      const pill = el('span', 'trace-pill', shortName(n));
      pill.addEventListener('click', () => { _depRoot = n; $('cte-node').value = n; runRail(); });
      row.appendChild(pill);
      if (i < p.length - 1) {
        const info = relOf[edgeKey(p[i], p[i + 1], depthOf)] || {};
        row.appendChild(el('span', 'trace-verb', '→ ' + (info.rel || 'uses') + ' →'));
      }
    });
    box.appendChild(row);
  });
}

// ── Search ────────────────────────────────────────────────────────────────────
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
  $('search-input').value = 'what encrypts production data';
  runSearch();
}

async function runSearch() {
  const q = ($('search-input').value || '').trim();
  if (!q) return;
  $('search-stat').textContent = 'searching…';
  const data = await getJSON(`/api/search?mode=${_searchMode}&q=${encodeURIComponent(q)}`);
  $('search-sql').textContent = data.note || '';
  const box = $('search-results'); clear(box);
  if (!data.available) { box.appendChild(el('div', 'feed-empty', data.note || 'Search unavailable.')); $('search-stat').textContent = 'unavailable'; return; }
  $('search-stat').textContent = `${data.results.length} results · ${data.mode}`;
  if (!data.results.length) { box.appendChild(el('div', 'feed-empty', 'No matches.')); return; }
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

// ── Reset ──────────────────────────────────────────────────────────────────────
$('reset-btn').addEventListener('click', async () => {
  if (!confirm('Reset the demo? This restores the clean baseline (staging gap reopens).')) return;
  $('reset-btn').textContent = 'Resetting…';
  await postJSON('/api/reset');
  await loadAll();
  if (document.querySelector('.view[data-view="live"]').classList.contains('active')) liveGraph.set(filteredLive(), _edges, {});
  $('reset-btn').textContent = 'Reset';
});

// ── Boot ─────────────────────────────────────────────────────────────────────
function applyHash() {
  const h = (location.hash || '').replace('#', '');
  if (TABS.includes(h)) showTab(h);
}
window.addEventListener('hashchange', applyHash);
getJSON('/api/backend').then(() => { $('backend-name').textContent = 'TiDB Cloud'; }).catch(() => {});
loadAll().then(applyHash);
setInterval(poll, 2000);
