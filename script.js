// Scroll-driven sunset.
// p goes from 0 (top of page) to 1 (end of the scroll track).
// Each layer gets its own window of p via seg(p, start, end).

const $ = (id) => document.getElementById(id);
const track = $('track');
const stage = document.querySelector('.stage');
const els = {
  skyDay: $('skyDayLayer'),
  skyDusk: $('skyDuskLayer'),
  sunGlow: $('sunGlow'),
  sunBody: $('sunBody'),
  sunBodyDusk: $('sunBodyDusk'),
  sunOutline: $('sunOutline'),
  hint: $('hint'),
};

// Mountain layers, far → near. The sun never moves on screen; it "sets"
// because the mountains rise over it. Shapes in ranges.js are drawn at
// their final resting place. Each layer rises at one constant speed and
// lands exactly at rest when the animation ends, where normal page
// scrolling takes over.
//   speed:    fraction of normal page-scroll speed. The ground is 1, so it
//             moves exactly like page content; further layers are slower
//             (parallax). Slower layers also start appearing earlier.
//   day/dusk: flat fill colour; it blends from day to dusk as the sun sets
//   key:      which shape to use from each range in ranges.js
const mountains = [
  { key: 'far',    el: $('mtFar'),  speed: 0.5,  day: '#a7b3cc', dusk: '#9b5577' },
  { key: 'mid',    el: $('mtMid'),  speed: 0.65, day: '#7d84a3', dusk: '#6e3d62' },
  { key: 'near',   el: $('mtNear'), speed: 0.8,  day: '#4f4f6e', dusk: '#4a2f4f' },
  { key: 'ground', el: $('ground'), speed: 1,    day: '#2a2232', dusk: '#2a2232' },
  // egg scene only: faster than the skillet (which rides on the ground at 1),
  // so the egg white starts hidden behind the pan and rises out of it
  { key: 'eggWhite', el: $('eggWhite'), speed: 1.2, day: '#ffffff', dusk: '#ffffff', eggFit: true },
];

// Converting scroll pixels to SVG units (the viewBox is 1600x1000 with
// "slice" scaling, so this depends on the window shape). Updated on resize.
const scene = $('scene');
const eggScene = $('eggScene');
const eggBg = $('eggBg');
let unitsPerPx = 1;
let trackScroll = 0; // how many px of scrolling the animation lasts
function measure() {
  const r = scene.getBoundingClientRect();
  unitsPerPx = 1 / Math.max(r.width / 1600, r.height / 1000);
  // the stage's height (fixed on phones), not the window's, which changes as
  // the URL bar shows/hides; the sticky part of the scroll lasts this long
  trackScroll = Math.max(0, track.offsetHeight - stage.offsetHeight);
  placeMenu();
  fitEgg();
}

// Egg scene on narrow screens (phones): shrink the yolk, egg white and skillet
// together, towards a point on the stovetop under the pan, until the whole
// skillet fits the screen width. Scale 1 (no change) wherever it already fits.
let eggFit = ''; // extra transform for the egg pieces ('' = none)
const EGG_ANCHOR = [800, 545];  // centre of the stovetop under the pan (SVG units)
const EGG_HALF_WIDTH = 700;     // pan + a bit of handle, from the centre (SVG units)
function fitEgg() {
  const visibleWidth = scene.getBoundingClientRect().width * unitsPerPx;
  const s = Math.min(1, visibleWidth / 2 / EGG_HALF_WIDTH);
  const [ax, ay] = EGG_ANCHOR;
  eggFit = scene.classList.contains('egg') && s < 1
    ? ` translate(${ax} ${ay}) scale(${s}) translate(${-ax} ${-ay})` : '';
  $('sun').setAttribute('transform', `${eggFit} translate(800 500)`.trim()); // the yolk
}

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
  // colour revealed by bounce-scrolling (see html.at-top in style.css)
  document.documentElement.classList.toggle('at-top', p < 0.5);

  els.hint.style.opacity = 0.7 * (1 - seg(p, 0, 0.08));

  // 1. plain circle → filled sun
  els.sunBody.style.opacity = seg(p, 0.1, 0.4);
  els.sunOutline.style.opacity = 1 - seg(p, 0.08, 0.25);

  // 2. day sky appears, mountains slide up from below the screen
  els.skyDay.style.opacity = seg(p, 0.15, 0.45);
  els.sunGlow.style.opacity = seg(p, 0.25, 0.55);

  // 3. mountains climb over the (stationary) sun, sky turns to dusk
  const dusk = seg(p, 0.55, 0.95);
  els.sunBodyDusk.style.opacity = dusk;
  els.skyDusk.style.opacity = dusk;

  // scrolling left until the animation ends, in SVG units
  const left = (1 - p) * trackScroll * unitsPerPx;
  for (const m of mountains) {
    m.el.setAttribute('transform', `translate(0 ${m.speed * left})${m.eggFit ? eggFit : ''}`);
    m.el.setAttribute('fill', mix(m.day, m.dusk, dusk));
  }

  // "egg" scene (only visible when selected): the skillet rises with the
  // ground at page speed
  eggScene.setAttribute('transform', `translate(0 ${left})${eggFit}`);
  eggBg.style.opacity = seg(p, 0.15, 0.45); // darker cream fades in (same timing as the day sky)
}

function progress() {
  const total = track.offsetHeight - stage.offsetHeight;
  return total > 0 ? clamp(-track.getBoundingClientRect().top / total) : 1;
}

// ---------- Mountain range selection ----------

// The choice isn't remembered: every visit starts on the first range.
// (Clear the choice older versions of the site saved, so it's not left behind.)
try { localStorage.removeItem('mountainRange'); } catch { /* storage blocked: nothing to clear */ }

// The joke option at the end of the menu: a fried egg in a skillet instead of
// mountains (drawn in index.html, #eggScene). Its "ground" is the flat
// stovetop, kept no lower than the mountain grounds so the menu doesn't move.
RANGES.push({
  name: 'egg',
  egg: true,
  far: '', mid: '', near: '',
  ground: 'M -40 1000 L -40 545 L 1640 545 L 1640 1000 Z',
  eggWhite: 'M 380 490 C 380 438, 405 407, 470 405 L 1130 405 C 1195 407, 1220 438, 1220 490 Z', // flat on top, curving down near the edges
});

let currentRange = 0;

function applyRange(i) {
  currentRange = i;
  for (const m of mountains) m.el.setAttribute('d', RANGES[i][m.key] ?? ''); // missing layer = not drawn
  scene.classList.toggle('egg', Boolean(RANGES[i].egg)); // CSS swaps the scene
  fitEgg();
}
applyRange(currentRange);


// The top edge of every range's ground, as segments [xMin, xMax, yMax] in SVG
// units (at rest). The menu sits below the lowest of them, so it stays put
// whichever range is selected. Read straight from the path data: a line or
// curve never dips below its lowest (control) point, so that's a safe floor
// and costs next to nothing. Paths using other commands (e.g. hand-drawn
// ones) fall back to sampling points along the path.
function groundSegments(d) {
  const tokens = d.match(/[a-zA-Z]|-?\d*\.?\d+(?:e[-+]?\d+)?/g) || [];
  const segs = [];
  let cx = 0, cy = 0, i = 0, cmd = '';
  const num = () => parseFloat(tokens[i++]);
  while (i < tokens.length) {
    if (/[a-zA-Z]/.test(tokens[i])) cmd = tokens[i++];
    if (cmd === 'M') { cx = num(); cy = num(); cmd = 'L'; continue; } // further pairs are lines
    if (cmd === 'Z' || cmd === 'z') continue;
    let xs, ys;
    if (cmd === 'L') { const x = num(), y = num(); xs = [cx, x]; ys = [cy, y]; cx = x; cy = y; }
    else if (cmd === 'C') { const p = [num(), num(), num(), num(), num(), num()]; xs = [cx, p[0], p[2], p[4]]; ys = [cy, p[1], p[3], p[5]]; cx = p[4]; cy = p[5]; }
    else return null; // other commands: caller samples instead
    if (Math.max(...ys) >= 999) continue; // the shape's sides and bottom, not the top edge
    segs.push([Math.min(...xs), Math.max(...xs), Math.max(...ys)]);
  }
  return segs;
}
function sampledSegments(d) {
  const probe = document.createElementNS('http://www.w3.org/2000/svg', 'path');
  probe.setAttribute('d', d);
  scene.querySelector('defs').append(probe);
  const len = probe.getTotalLength(), segs = [];
  let prev = null;
  for (let s = 0; s <= len; s += 12) {
    const pt = probe.getPointAtLength(s);
    if (prev && pt.y < 999 && prev.y < 999) segs.push([Math.min(prev.x, pt.x) - 6, Math.max(prev.x, pt.x) + 6, Math.max(prev.y, pt.y)]);
    prev = pt;
  }
  probe.remove();
  return segs;
}
const groundEdges = RANGES.map((range) => groundSegments(range.ground) ?? sampledSegments(range.ground));

// ---------- Range menu ----------

// One option per range. A range can have a `name` (e.g. a famous peak you
// recreate); generated ones fall back to "Range N".
const rangeMenu = $('rangeMenu');
RANGES.forEach((range, i) => rangeMenu.add(new Option(range.name || `Range ${i + 1}`, i)));
rangeMenu.value = currentRange;
rangeMenu.addEventListener('change', () => {
  applyRange(Number(rangeMenu.value));
  render(progress()); // apply (or undo) the egg fit right away
  sizeMenu();
});

// Text width in the menu's font (measured on a canvas; nothing is drawn)
const measureCtx = document.createElement('canvas').getContext('2d');
function menuTextWidth(text) {
  const cs = getComputedStyle(rangeMenu);
  measureCtx.font = `${cs.fontStyle} ${cs.fontWeight} ${cs.fontSize} ${cs.fontFamily}`;
  const spacing = parseFloat(cs.letterSpacing) || 0; // canvas doesn't apply letter-spacing
  return measureCtx.measureText(text).width + spacing * text.length;
}
function menuPadding() {
  const cs = getComputedStyle(rangeMenu);
  return parseFloat(cs.paddingLeft) + parseFloat(cs.paddingRight);
}

// Size the menu to the selected name, with room for the arrow (browsers can
// otherwise clip the text). It's right-aligned, so only its left edge moves.
function sizeMenu() {
  const w = menuTextWidth(rangeMenu.selectedOptions[0].text);
  rangeMenu.style.width = `${Math.ceil(w + menuPadding()) + 2}px`;
}
sizeMenu();

// Rest the menu just below the ground's edge: the lowest edge point of ANY
// range across the space the menu can take up (its widest name), so its
// position never changes when switching ranges.
function placeMenu() {
  const r = scene.getBoundingClientRect();
  const scale = 1 / unitsPerPx;
  const offX = (r.width - 1600 * scale) / 2;  // where the viewBox starts on screen
  const offY = (r.height - 1000 * scale) / 2; // (negative when "slice" crops it)
  const m = rangeMenu.getBoundingClientRect();
  const widest = Math.max(...[...rangeMenu.options].map((o) => menuTextWidth(o.text))) + menuPadding();
  const x2 = (m.right - r.left - offX) * unitsPerPx;
  const x1 = x2 - widest * unitsPerPx;
  let edge = -Infinity;
  for (const segs of groundEdges) for (const [a, b, y] of segs) if (b >= x1 && a <= x2 && y > edge) edge = y;
  if (edge === -Infinity) return;
  const GAP = 10; // extra px between the ground's edge and the menu's box (its padding already adds a little)
  rangeMenu.style.bottom = `${r.height - (offY + edge * scale) - GAP - m.height}px`;
}
document.fonts?.ready.then(() => { sizeMenu(); placeMenu(); });

// ---------- Info popups ("blog", "contact") ----------

// Any button with class "popup-trigger" toggles the popup named in its
// aria-controls. Only one is open at a time; clicking elsewhere or Esc closes it.
const popupTriggers = [...document.querySelectorAll('.popup-trigger')];
const popupFor = (btn) => document.getElementById(btn.getAttribute('aria-controls'));

function setPopupOpen(btn, open) {
  const popup = popupFor(btn);
  popup.hidden = !open;
  btn.setAttribute('aria-expanded', String(open));
  if (!open) return;
  for (const other of popupTriggers) if (other !== btn) setPopupOpen(other, false);
  // keep the popup on screen: nudge it left if it would run off the right edge
  popup.style.translate = '';
  const overflow = popup.getBoundingClientRect().right - (document.documentElement.clientWidth - 16);
  if (overflow > 0) popup.style.translate = `${-overflow}px 0`;
}
for (const btn of popupTriggers) {
  btn.addEventListener('click', () => setPopupOpen(btn, popupFor(btn).hidden));
}
document.addEventListener('click', (e) => {
  for (const btn of popupTriggers) {
    if (!popupFor(btn).hidden && !btn.contains(e.target) && !popupFor(btn).contains(e.target)) setPopupOpen(btn, false);
  }
});
document.addEventListener('keydown', (e) => {
  if (e.key !== 'Escape') return;
  const open = popupTriggers.find((btn) => !popupFor(btn).hidden);
  if (open) { setPopupOpen(open, false); open.focus(); }
});

// ---------- Scroll wiring ----------

const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

if (reduceMotion) {
  measure();
  window.addEventListener('resize', measure);
  render(1);
} else {
  let ticking = false;
  const update = () => {
    if (ticking) return;
    ticking = true;
    requestAnimationFrame(() => { render(progress()); ticking = false; });
  };
  window.addEventListener('scroll', update, { passive: true });
  window.addEventListener('resize', () => { measure(); update(); });
  measure();
  render(progress());
}

// ---------- Rotating tagline ----------

const tagline = $('tagline');
// Timings come from taglines.js; the fade durations are handed to the CSS
const ROTATE_MS = TAGLINE_CHANGE_MS;
const FADE_MS = TAGLINE_FADE_OUT_MS + TAGLINE_PAUSE_MS; // until the text swaps
tagline.style.setProperty('--fade-out', `${TAGLINE_FADE_OUT_MS}ms`);
tagline.style.setProperty('--fade-in', `${TAGLINE_FADE_IN_MS}ms`);

// Shuffle-bag per list: every phrase is shown once, in random order, before
// any repeat. Blank entries are skipped.
function shuffleBag(list) {
  const phrases = list.filter((t) => t.trim());
  let bag = [];
  return () => {
    if (!bag.length) {
      bag = phrases.filter((t) => t !== tagline.textContent); // no back-to-back repeat
      for (let i = bag.length - 1; i > 0; i--) {
        const j = Math.floor(Math.random() * (i + 1));
        [bag[i], bag[j]] = [bag[j], bag[i]];
      }
    }
    return bag.pop() ?? phrases[0] ?? tagline.textContent;
  };
}
const autoPhrases = TAGLINES_AUTO.filter((t) => t.trim());
const drawAuto = shuffleBag(autoPhrases);
// "next" has its own list; falls back to the automatic one while it's empty
const drawNext = shuffleBag(TAGLINES_NEXT.some((t) => t.trim()) ? TAGLINES_NEXT : autoPhrases);

// "next" only works once the current phrase has fully faded in, so double
// clicks (or fast clicking) can't skip through phrases. No visual change.
let nextArmed = true;
let armTimer;

let fadeTimer;
function showPhrase(text) {
  clearTimeout(fadeTimer);
  clearTimeout(armTimer);
  nextArmed = false;
  armTimer = setTimeout(() => { nextArmed = true; },
    reduceMotion ? 300 : FADE_MS + TAGLINE_FADE_IN_MS);
  if (reduceMotion) { tagline.textContent = text; return; }
  tagline.classList.add('is-fading');
  fadeTimer = setTimeout(() => {
    tagline.textContent = text;
    tagline.classList.remove('is-fading');
  }, FADE_MS);
}

// Auto-change: the first change after `firstDelay`, then every ROTATE_MS
let rotateTimer;
function restartRotation(firstDelay = ROTATE_MS) {
  clearTimeout(rotateTimer);
  if (reduceMotion) return;
  const tick = () => { showPhrase(drawAuto()); rotateTimer = setTimeout(tick, ROTATE_MS); };
  rotateTimer = setTimeout(tick, firstDelay);
}

// "next": a phrase from the "next" list now; every 10th press shows the
// easter egg instead. The auto-change timer restarts (back to the tame list).
let nextPresses = 0;
$('nextTagline').addEventListener('click', () => {
  if (!nextArmed) return;  // a phrase is still changing: ignore (doesn't count)
  firstSeen?.disconnect(); // skip the opening hold if they press "next" first
  nextPresses++;
  showPhrase(nextPresses % 10 === 0 ? TAGLINE_EASTER_EGG : drawNext());
  restartRotation();
});

// Always open on the first phrase and hold it for TAGLINE_FIRST_MS, counted
// from when the tagline first scrolls into view (it starts below the sunset).
// IntersectionObserver is handled by the browser, so this costs nothing while
// scrolling; it fires once and then stops watching.
// (Pressing "next" before then switches straight to the normal behaviour.)
tagline.textContent = TAGLINE_FIRST;
let firstSeen = null;
if ('IntersectionObserver' in window) {
  firstSeen = new IntersectionObserver((entries) => {
    if (!entries.some((e) => e.isIntersecting)) return;
    firstSeen.disconnect();
    restartRotation(TAGLINE_FIRST_MS);
  }, { threshold: 0.5 });
  firstSeen.observe(tagline);
} else {
  restartRotation(TAGLINE_FIRST_MS); // very old browsers: count from page load
}
