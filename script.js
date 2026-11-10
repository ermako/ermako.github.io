// Scroll-driven sunset.
// p goes from 0 (top of page) to 1 (end of the scroll track).
// Each layer gets its own window of p via seg(p, start, end).

const $ = (id) => document.getElementById(id);
const track = $('track');
const els = {
  skyDay: $('skyDayLayer'),
  skyDusk: $('skyDuskLayer'),
  sun: $('sun'),
  sunGlow: $('sunGlow'),
  sunBody: $('sunBody'),
  sunBodyDusk: $('sunBodyDusk'),
  sunOutline: $('sunOutline'),
  hint: $('hint'),
};

// Mountain layers, far → near.
//   from:     how far below its resting place it starts (SVG units)
//   at:       scroll window in which it slides up
//   day/dusk: flat fill colour; it blends from day to dusk as the sun sets
//   key:      which shape to use from each range in ranges.js
const mountains = [
  { key: 'far',    el: $('mtFar'),  from: 650, at: [0.12, 0.36], day: '#a7b3cc', dusk: '#9b5577' },
  { key: 'mid',    el: $('mtMid'),  from: 500, at: [0.15, 0.38], day: '#7d84a3', dusk: '#6e3d62' },
  { key: 'near',   el: $('mtNear'), from: 380, at: [0.18, 0.40], day: '#4f4f6e', dusk: '#4a2f4f' },
  { key: 'ground', el: $('ground'), from: 300, at: [0.20, 0.42], day: '#2a2232', dusk: '#2a2232' },
];

const clamp = (v, a = 0, b = 1) => Math.min(b, Math.max(a, v));
const lerp = (a, b, t) => a + (b - a) * t;
// 0→1 between a and b, eased (smoothstep)
const seg = (p, a, b) => {
  const t = clamp((p - a) / (b - a));
  return t * t * (3 - 2 * t);
};
// blend two '#rrggbb' colours
const mix = (a, b, t) => {
  const c = (hex, i) => parseInt(hex.slice(1 + i * 2, 3 + i * 2), 16);
  return '#' + [0, 1, 2].map((i) =>
    Math.round(lerp(c(a, i), c(b, i), t)).toString(16).padStart(2, '0')).join('');
};

function render(p) {
  els.hint.style.opacity = 0.7 * (1 - seg(p, 0, 0.08));

  // 1. plain circle → filled sun
  els.sunBody.style.opacity = seg(p, 0.1, 0.4);
  els.sunOutline.style.opacity = 1 - seg(p, 0.08, 0.25);

  // 2. day sky appears, mountains slide up from below the screen
  els.skyDay.style.opacity = seg(p, 0.15, 0.45);
  els.sunGlow.style.opacity = seg(p, 0.25, 0.55);

  // 3. sun sinks, sky (and mountains) turn to dusk
  const dusk = seg(p, 0.5, 0.85);
  const y = lerp(400, 720, seg(p, 0.35, 0.9));
  els.sun.setAttribute('transform', `translate(800 ${y})`);
  els.sunBodyDusk.style.opacity = dusk;
  els.skyDusk.style.opacity = dusk;

  for (const m of mountains) {
    m.el.setAttribute('transform', `translate(0 ${lerp(m.from, 0, seg(p, ...m.at))})`);
    m.el.setAttribute('fill', mix(m.day, m.dusk, dusk));
  }
}

function progress() {
  const total = track.offsetHeight - window.innerHeight;
  return total > 0 ? clamp(-track.getBoundingClientRect().top / total) : 1;
}

// ---------- Mountain range selection ----------

const STORAGE_KEY = 'mountainRange';
const store = {
  get() { try { return localStorage.getItem(STORAGE_KEY); } catch { return null; } },
  set(v) { try { localStorage.setItem(STORAGE_KEY, v); } catch { /* storage blocked: choice just won't persist */ } },
};

let currentRange = clamp(parseInt(store.get(), 10) || 0, 0, RANGES.length - 1);

function applyRange(i) {
  currentRange = i;
  for (const m of mountains) m.el.setAttribute('d', RANGES[i][m.key]);
}
applyRange(currentRange);

// ---------- Settings gear + picker ----------

const gear = $('gear');
const picker = $('picker');
const grid = $('pickerGrid');
const SVG_NS = 'http://www.w3.org/2000/svg';
const svgEl = (tag, attrs) => {
  const el = document.createElementNS(SVG_NS, tag);
  for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, v);
  return el;
};

// One thumbnail per range, drawn as the finished sunset.
// The gradients are shared with the main scene's <defs>.
RANGES.forEach((range, i) => {
  const btn = document.createElement('button');
  btn.type = 'button';
  btn.className = 'thumb';
  btn.setAttribute('aria-label', `Mountain range ${i + 1}`);
  btn.setAttribute('aria-pressed', String(i === currentRange));

  const svg = svgEl('svg', { viewBox: '0 250 1600 750', preserveAspectRatio: 'xMidYMid slice', 'aria-hidden': 'true' });
  svg.append(
    svgEl('rect', { y: 0, width: 1600, height: 1000, fill: 'url(#skyDusk)' }),
    svgEl('circle', { cx: 800, cy: 720, r: 220, fill: 'url(#sunFillDusk)' }),
    ...mountains.map((m) => svgEl('path', { d: range[m.key], fill: m.dusk })),
  );
  const label = document.createElement('span');
  label.textContent = i + 1;
  btn.append(svg, label);

  btn.addEventListener('click', () => {
    applyRange(i);
    store.set(String(i));
    grid.querySelectorAll('.thumb').forEach((t, j) => t.setAttribute('aria-pressed', String(j === i)));
  });
  grid.append(btn);
});

function setPickerOpen(open) {
  picker.hidden = !open;
  gear.setAttribute('aria-expanded', String(open));
  if (open) grid.children[currentRange]?.focus();
}
gear.addEventListener('click', () => setPickerOpen(picker.hidden));
document.addEventListener('click', (e) => {
  if (!picker.hidden && !picker.contains(e.target) && !gear.contains(e.target)) setPickerOpen(false);
});
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape' && !picker.hidden) { setPickerOpen(false); gear.focus(); }
});

// ---------- Scroll wiring ----------

const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

if (reduceMotion) {
  render(1);
} else {
  let ticking = false;
  const update = () => {
    if (ticking) return;
    ticking = true;
    requestAnimationFrame(() => { render(progress()); ticking = false; });
  };
  window.addEventListener('scroll', update, { passive: true });
  window.addEventListener('resize', update);
  render(progress());
}
