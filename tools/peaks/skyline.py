#!/usr/bin/env python3
"""Washington skylines for the sunset scene: a real mountain at the back, with
generated hills in front (the same generator as the "mountains" range).

  python3 tools/peaks/skyline.py candidates <slug> [count]
      Make `count` (default 12) random versions of one view, plus a preview
      page to compare them: tools/peaks/candidates/<slug>/index.html. Each
      shows its seed. Take a whole one by copying its SVG over
      tools/peaks/svg/<slug>.svg, or set seeds in that view's settings below
      (seed=..., or mid_seed / near_seed / ground_seed to mix layers from
      different candidates) and run `generate`.

  python3 tools/peaks/skyline.py generate [slug ...] [--force]
      Write tools/peaks/svg/<slug>.svg for each view, using the seeds in its
      settings. An SVG that already exists is left alone (it may have hand
      edits) unless you pass --force.

  python3 tools/peaks/skyline.py build
      Read the SVGs (edited or not) and write peaks.js for the site.

The far layer is real: stand at the viewpoint, cast a sight line for every
column of the picture, and keep the highest point along it beyond `far_km`
(allowing for the Earth's curvature and atmospheric refraction). It's
computed once per view and cached, so making candidates is quick. The mid,
near and ground layers come from tools/mountains.py, so every view has the
same layered depth as the "mountains" range.

Editing the SVGs (Inkscape works well): each layer (far, mid, near, ground)
holds one path. Reshape them freely, but keep each one closed down to the
bottom of the picture. The "guides" layer is locked and ignored by `build`:
it shows the sun, the part of the scene phones can see, and the line the
ground should stay above on the right (so the range menu doesn't move).

Elevation data: AWS Terrain Tiles ("terrarium" format), public, no key needed.
Built from public-domain sources including USGS 3DEP and SRTM.
Uses only the Python standard library.
"""
import hashlib
import json
import math
import random
import re
import shutil
import struct
import sys
import urllib.request
import xml.etree.ElementTree as ET
import zlib
from array import array
from pathlib import Path

HERE = Path(__file__).resolve().parent
SVG_DIR = HERE / "svg"
CACHE = HERE / ".cache" / "terrarium"
FAR_CACHE = HERE / ".cache" / "far"
CANDIDATES = HERE / "candidates"
ROOT = HERE.parent.parent
OUT = ROOT / "peaks.js"

sys.path.insert(0, str(HERE.parent))
import mountains as hills  # noqa: E402  (tools/mountains.py: the "mountains" generator)

# ---------------------------------------------------------------- views ---
# Required:
#   slug:   short file name, giving tools/peaks/svg/<slug>.svg (must be unique).
#   name:   what the menu shows.
#   view, peak: latitude, longitude in decimal degrees. The peak automatically
#           snaps to the true summit within 600 m.
#   peak_x: where the summit sits across the 1600-wide picture. The sun is at
#           800; around 450-600 or 1000-1150 sets the sun beside the peak.
#           Phones see roughly 570-1030.
# Optional:
#   snap:   metres to move the viewpoint to the highest ground nearby. Use it
#           for summits, ridges and lookouts (300-500) so slightly-off
#           coordinates don't put you in a hollow. Leave it out for lakes.
#   fov:    how wide the view is in degrees (default 50). Wider = smaller mountain.
#   exaggeration: vertical stretch (default 1.0 = the mountain's real proportions;
#           1.3-1.5 adds a little drama). To make a peak bigger without
#           distorting it, zoom in with a narrower fov instead.
#   lift:   move the real mountain up (or down, if negative) by this many
#           picture units, without stretching it (default 0).
#   peak_y: put the summit at this height in the picture (smaller = higher)
#           and stretch to fit, instead of using exaggeration.
#   eye:    metres above the ground you're looking from (default 3).
#   max_km: how far the sight lines reach (default 150).
#   far_km: terrain from this distance on is the real far layer (default:
#           half the distance to the peak); anything closer is left out.
#   seed:   picks the generated mid, near and ground layers (default: one
#           fixed per view). mid_seed / near_seed / ground_seed override it
#           per layer, so you can mix layers from different candidates.
#   foreground: how tall the generated hills are compared with "mountains"
#           (default 0.5). Lower = flatter hills = more of the real mountain shows.
#   manual: True for a view you drew by hand: generate and candidates skip it,
#           so your drawing is never overwritten. Only slug and name are needed.
#   hills:  per-layer tweaks to the generator, e.g. hills=dict(mid=dict(height=120)).
#           Settings: see BASE in tools/mountains.py (applied after foreground).
#
# Example:
# python3 tools/peaks/skyline.py candidates rainier 12     # 12 random versions + a preview page
# python3 tools/peaks/skyline.py generate rainier --force   # use the seeds in rainier's settings
# python3 tools/peaks/skyline.py build                      # SVGs → peaks.js

VIEWS = [
    dict(slug="rainier",
        name="mt rainier",
        view=(46.6640, -121.8885), # from High Rock Lookout
        snap=500,
        peak=(46.8529, -121.7604),
        peak_x=800,
        eye=3.0,
        exaggeration=1.0,
        fov=85,
        foreground=0.7,
        max_km=150.0,
        seed=151715),
    dict(slug="baker",
        name="mt baker",
        view=(48.86928, -122.01599), # seen from slug mountain
        snap=500,
        peak=(48.77677, -121.81456),
        peak_x=770,
        eye=3.0,
        exaggeration=1.0,
        lift=-50,
        fov=50,
        foreground=0.8,
        max_km=150.0,
        seed=289711),
    dict(slug="pickets",
        name="n. cascades",
        manual=True,  # hand-drawn in Inkscape: generate and candidates leave it alone
        view=(48.70670, -122.35601), # a view of the pickets
        snap=500,
        peak=(48.77467, -121.29936),
        peak_x=770,
        eye=3.0,
        exaggeration=1.0,
        fov=50,
        foreground=0.8,
        max_km=150.0),
]
DEFAULTS = dict(fov=50.0, eye=3.0, exaggeration=1.0, max_km=150.0, foreground=0.5)
GROUND_LINE = 550  # the hills squash toward this height (the bottom of the ground layer)

# Picture layout (must match the site: viewBox 1600x1000, sun r=220 at 800,500)
W = 1600                      # picture width (height is 1000)
X0, X1, DX = -40, 1640, 5     # columns; slightly wider than the picture
FAR_BASE_Y = 440              # where the real skyline's low points sit (just above the hills)
GROUND_MAX_Y = 545            # ground never dips below this (keeps the menu put)
LAYERS = ["far", "mid", "near", "ground"]
COLOURS = dict(far="#9b5577", mid="#6e3d62", near="#4a2f4f", ground="#2a2232")

EARTH_R = 6371000.0
REFRACTION = 0.13             # standard atmospheric refraction coefficient

# ------------------------------------------------------- elevation tiles ---
_tiles = {}


def _decode_png(data):
    """8-bit RGB/RGBA PNG -> list of rows of bytes (no external libraries)."""
    pos, idat, w = 8, b"", None
    while pos < len(data):
        n, kind = struct.unpack(">I4s", data[pos:pos + 8])
        body = data[pos + 8:pos + 8 + n]
        pos += 12 + n
        if kind == b"IHDR":
            w, h, depth, colour = struct.unpack(">IIBB", body[:10])
            if depth != 8 or colour not in (2, 6):
                raise ValueError("unsupported PNG")
            bpp = 3 if colour == 2 else 4
        elif kind == b"IDAT":
            idat += body
    raw, stride, rows, prev, i = zlib.decompress(idat), w * bpp, [], bytearray(w * bpp), 0
    for _ in range(h):
        f, line = raw[i], bytearray(raw[i + 1:i + 1 + stride])
        i += 1 + stride
        for x in range(stride):
            a = line[x - bpp] if x >= bpp else 0
            b = prev[x]
            c = prev[x - bpp] if x >= bpp else 0
            if f == 1: line[x] = (line[x] + a) & 255
            elif f == 2: line[x] = (line[x] + b) & 255
            elif f == 3: line[x] = (line[x] + (a + b) // 2) & 255
            elif f == 4:
                p, pa, pb, pc = a + b - c, abs(b - c), abs(a - c), abs(a + b - 2 * c)
                line[x] = (line[x] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
        rows.append(line)
        prev = line
    return w, bpp, rows


def _tile(z, tx, ty):
    """Elevations (metres) of one 256x256 tile, downloaded once and cached."""
    key = (z, tx, ty)
    if key in _tiles:
        return _tiles[key]
    f32 = CACHE / str(z) / str(tx) / f"{ty}.f32"
    if f32.exists():
        elev = array("f")
        elev.frombytes(f32.read_bytes())
    else:
        url = f"https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{tx}/{ty}.png"
        req = urllib.request.Request(url, headers={"User-Agent": "skyline-generator"})
        with urllib.request.urlopen(req, timeout=30) as r:
            w, bpp, rows = _decode_png(r.read())
        elev = array("f", (row[x * bpp] * 256 + row[x * bpp + 1] + row[x * bpp + 2] / 256 - 32768
                           for row in rows for x in range(w)))
        f32.parent.mkdir(parents=True, exist_ok=True)
        f32.write_bytes(elev.tobytes())
    _tiles[key] = elev
    return elev


def elevation(lat, lon, z):
    """Bilinear-interpolated elevation at a point, from zoom-z tiles."""
    n = 2 ** z * 256
    gx = (lon + 180) / 360 * n
    s = math.sin(math.radians(lat))
    gy = (0.5 - math.log((1 + s) / (1 - s)) / (4 * math.pi)) * n
    x0, y0 = int(gx), int(gy)
    fx, fy = gx - x0, gy - y0

    def px(x, y):
        return _tile(z, x // 256, y // 256)[(y % 256) * 256 + x % 256]

    top = px(x0, y0) * (1 - fx) + px(x0 + 1, y0) * fx
    bottom = px(x0, y0 + 1) * (1 - fx) + px(x0 + 1, y0 + 1) * fx
    return top * (1 - fy) + bottom * fy


def zoom_for(d):
    return 12 if d < 25000 else 11 if d < 80000 else 10


# --------------------------------------------------------------- geometry ---
def bearing(a, b):
    la1, lo1, la2, lo2 = map(math.radians, (*a, *b))
    y = math.sin(lo2 - lo1) * math.cos(la2)
    x = math.cos(la1) * math.sin(la2) - math.sin(la1) * math.cos(la2) * math.cos(lo2 - lo1)
    return math.degrees(math.atan2(y, x)) % 360


def distance(a, b):
    la1, lo1, la2, lo2 = map(math.radians, (*a, *b))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * EARTH_R * math.asin(math.sqrt(h))


def destination(start, brg, d):
    la, lo, b, r = math.radians(start[0]), math.radians(start[1]), math.radians(brg), d / EARTH_R
    la2 = math.asin(math.sin(la) * math.cos(r) + math.cos(la) * math.sin(r) * math.cos(b))
    lo2 = lo + math.atan2(math.sin(b) * math.sin(r) * math.cos(la), math.cos(r) - math.sin(la) * math.sin(la2))
    return math.degrees(la2), math.degrees(lo2)


def snap_high(pt, radius_m, step_m=20.0):
    """The highest point within radius_m of pt, and its elevation."""
    lat0, lon0 = pt
    best_e, best = elevation(lat0, lon0, 12), pt
    n = int(radius_m // step_m)
    dlat, dlon = step_m / 111320, step_m / (111320 * math.cos(math.radians(lat0)))
    for i in range(-n, n + 1):
        for j in range(-n, n + 1):
            if i * i + j * j <= n * n:
                e = elevation(lat0 + i * dlat, lon0 + j * dlon, 12)
                if e > best_e:
                    best_e, best = e, (lat0 + i * dlat, lon0 + j * dlon)
    return best, best_e


def simplify(pts, tol=0.75):
    """Ramer-Douglas-Peucker: drop points that don't change the line by > tol."""
    if len(pts) < 3:
        return pts
    (ax, ay), (bx, by) = pts[0], pts[-1]
    dx, dy = bx - ax, by - ay
    norm = math.hypot(dx, dy) or 1
    i, dmax = 0, -1
    for k in range(1, len(pts) - 1):
        d = abs(dy * (pts[k][0] - ax) - dx * (pts[k][1] - ay)) / norm
        if d > dmax:
            i, dmax = k, d
    if dmax <= tol:
        return [pts[0], pts[-1]]
    return simplify(pts[:i + 1], tol)[:-1] + simplify(pts[i:], tol)


# ----------------------------------------------------------------- generate ---
def far_layer(v):
    """The real far layer for one view, as (x, y) points. Cached on disk."""
    cfg = {**DEFAULTS, **v}
    key_src = json.dumps({k: cfg.get(k) for k in
                          ("view", "peak", "snap", "fov", "eye", "exaggeration", "peak_y", "lift", "max_km", "far_km", "peak_x")},
                         sort_keys=True)
    cached = FAR_CACHE / f"{v['slug']}-{hashlib.sha1(key_src.encode()).hexdigest()[:12]}.json"
    if cached.exists():
        data = json.loads(cached.read_text())
        print(data["summary"])
        return [tuple(p) for p in data["points"]]

    fov, max_d = cfg["fov"], cfg["max_km"] * 1000
    peak, peak_e = snap_high(v["peak"], 600)
    if cfg.get("snap"):
        view, view_e = snap_high(v["view"], cfg["snap"])
    else:
        view, view_e = v["view"], elevation(*v["view"], 12)
    print(f"  {v['slug']}: standing at {view[0]:.5f}, {view[1]:.5f} ({view_e:.0f} m); "
          f"peak at {peak[0]:.5f}, {peak[1]:.5f} ({peak_e:.0f} m)")
    peak_d = distance(view, peak)
    far_from = cfg["far_km"] * 1000 if cfg.get("far_km") else 0.5 * peak_d
    centre = bearing(view, peak) - (v["peak_x"] - 800) / W * fov
    eye = view_e + cfg["eye"]

    # distances along each sight line (only the far part): steps grow further out
    steps, d = [], far_from
    while d < max_d:
        steps.append(d)
        d += max(15.0, d * 0.006)
    drop = [(s * s) / (2 * EARTH_R) * (1 - REFRACTION) for s in steps]

    cols = list(range(X0, X1 + 1, DX))
    angles = []
    for ci, x in enumerate(cols):
        az = centre + (x - 800) / W * fov
        best = -math.pi / 2
        for s, dr in zip(steps, drop):
            lat, lon = destination(view, az, s)
            a = math.atan2(elevation(lat, lon, zoom_for(s)) - dr - eye, s)
            if a > best:
                best = a
        angles.append(best)
        if ci % 60 == 0:
            print(f"  {v['slug']}: {100 * ci // len(cols)}%", flush=True)

    # angle -> picture height: the real skyline's low points (its lowest 10%)
    # sit at FAR_BASE_Y, just above the generated hills, and the mountain rises
    # from there at its real proportions (x exaggeration: the same scale as
    # across the picture), wherever it is left to right. `lift` moves it all
    # up (or down, if negative) without stretching; `peak_y` instead puts the
    # summit at a set height and stretches to fit.
    peak_a, centre_a = max(angles), angles[cols.index(800)]
    low_a = sorted(angles)[len(angles) // 10]
    base_y = FAR_BASE_Y - cfg.get("lift", 0)
    true_scale = W / math.radians(fov)              # picture units per radian, undistorted
    if cfg.get("peak_y") is not None:
        scale = (base_y - cfg["peak_y"]) / max(peak_a - low_a, 1e-4)
    else:
        scale = cfg["exaggeration"] * true_scale
    to_y = lambda a: base_y - (a - low_a) * scale
    summit_y, centre_y = to_y(peak_a), to_y(centre_a)
    sun = max(0.0, min(440.0, centre_y - 280))      # sun spans y 280-720; hills cover below ~420
    note = ("  (small: try a narrower fov, more lift, or some exaggeration)" if summit_y > 330 else
            "  (above the top of the picture: try a wider fov or less lift)" if summit_y < 0 else "")
    summary = (f"  {v['slug']}: peak {peak_d / 1000:.1f} km away, vertical exaggeration "
               f"x{scale / true_scale:.2f}, summit at y={summit_y:.0f}, "
               f"about {sun:.0f} of the sun shows above it at the centre{note}")
    print(summary)
    pts = simplify([(x, min(1000.0, max(-200.0, to_y(a)))) for x, a in zip(cols, angles)])
    cached.parent.mkdir(parents=True, exist_ok=True)
    cached.write_text(json.dumps({"summary": summary, "points": pts}))
    return pts


FRONT = ["mid", "near", "ground"]


def default_seed(slug):
    return zlib.crc32(slug.encode()) % 1_000_000


def front_seeds(v, seed=None):
    """The seed used for each generated layer of a view."""
    base = seed if seed is not None else v.get("seed", default_seed(v["slug"]))
    return {name: v.get(f"{name}_seed", base) if seed is None else seed for name in FRONT}


def front_layers(v, seeds):
    """Generated mid, near and ground paths, as in "mountains" (tools/mountains.py).
    Each layer's shape depends only on its own seed, so layers can be mixed."""
    out = {}
    for i, name in enumerate(FRONT):
        # squash the "mountains" hills toward the ground line by `foreground`
        # (same shapes, flatter), so they don't hide the real mountain
        f = v.get("foreground", DEFAULTS["foreground"])
        cfg = dict(hills.BASE[name])
        cfg["base"] = GROUND_LINE - (GROUND_LINE - cfg["base"]) * f
        cfg["height"] *= f
        cfg.update(v.get("hills", {}).get(name, {}))
        out[name] = hills.layer(seeds[name] * 7 + i + 1, **cfg)
    return out


def fmt(v):
    return f"{v:.1f}".rstrip("0").rstrip(".")


def path_d(pts):
    body = " ".join(f"L {fmt(x)} {fmt(y)}" for x, y in pts)
    return f"M {X0} 1000 {body} L {X1} 1000 Z"


SVG_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<!-- {name}: generated by tools/peaks/skyline.py ({seeds}),
     then free to edit by hand. Each layer holds one closed path;
     `skyline.py build` turns them into peaks.js. -->
<svg xmlns="http://www.w3.org/2000/svg"
     xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape"
     xmlns:sodipodi="http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd"
     width="1600" height="1000" viewBox="0 0 1600 1000">
  <title>{name}</title>
  <g id="guides" inkscape:groupmode="layer" inkscape:label="guides (ignored by build)" sodipodi:insensitive="true">
    <defs>
      <linearGradient id="sky" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0" stop-color="#231c45"/><stop offset="0.35" stop-color="#6b2f6e"/>
        <stop offset="0.55" stop-color="#d1496b"/><stop offset="0.65" stop-color="#f7934c"/>
      </linearGradient>
    </defs>
    <rect width="1600" height="1000" fill="url(#sky)"/>
    <circle cx="800" cy="500" r="220" fill="#ff6a3d"/>
    <rect x="569" y="0" width="462" height="1000" fill="none" stroke="#ffffff" stroke-opacity="0.35" stroke-dasharray="12 8" stroke-width="2"/>
    <text x="800" y="30" fill="#ffffff" fill-opacity="0.5" font-size="22" text-anchor="middle" font-family="monospace">what phones see</text>
    <line x1="1250" y1="{gmax}" x2="1600" y2="{gmax}" stroke="#ffffff" stroke-opacity="0.5" stroke-dasharray="6 6" stroke-width="2"/>
    <text x="1590" y="{gmax_label}" fill="#ffffff" fill-opacity="0.5" font-size="18" text-anchor="end" font-family="monospace">keep ground above this line</text>
  </g>
{layers}
</svg>
"""


def svg_text(v, paths, seeds):
    parts = []
    for name in LAYERS:
        parts.append(f'  <g id="{name}" inkscape:groupmode="layer" inkscape:label="{name}">\n'
                     f'    <path id="{name}-path" fill="{COLOURS[name]}" d="{paths[name]}"/>\n'
                     f'  </g>')
    seed_note = ", ".join(f"{k}_seed={s}" for k, s in seeds.items())
    return SVG_TEMPLATE.format(name=v["name"], seeds=seed_note, layers="\n".join(parts),
                               gmax=GROUND_MAX_Y + 6, gmax_label=GROUND_MAX_Y - 2)


def view_by_slug(slug):
    for v in VIEWS:
        if v["slug"] == slug:
            return v
    sys.exit(f"no view with slug {slug!r} (slugs: {', '.join(v['slug'] for v in VIEWS)})")


def generate(slugs, force):
    dupes = {v["slug"] for v in VIEWS if sum(w["slug"] == v["slug"] for w in VIEWS) > 1}
    if dupes:
        sys.exit(f"slugs must be unique; repeated: {', '.join(sorted(dupes))}")
    for v in VIEWS:
        if slugs and v["slug"] not in slugs:
            continue
        out = SVG_DIR / f"{v['slug']}.svg"
        if v.get("manual"):
            print(f"{v['slug']}: hand-drawn (manual=True); left alone")
            continue
        if out.exists() and not force:
            print(f"{v['slug']}: {out.relative_to(ROOT)} exists (may have edits); skipped. Use --force to redo it.")
            continue
        print(f"{v['slug']}: generating {v['name']}...")
        seeds = front_seeds(v)
        paths = {"far": path_d(far_layer(v)), **front_layers(v, seeds)}
        SVG_DIR.mkdir(parents=True, exist_ok=True)
        out.write_text(svg_text(v, paths, seeds))
        print(f"  wrote {out.relative_to(ROOT)} ({', '.join(f'{k}_seed={s}' for k, s in seeds.items())})")


CANDIDATE_PAGE = """<!doctype html>
<meta charset="utf-8">
<title>{name}: candidates</title>
<style>
  body {{ margin: 0; padding: 1.5rem; background: #17131b; color: #e8e0d4; font: 14px/1.5 ui-monospace, monospace; }}
  h1 {{ font-size: 1.1rem; font-weight: 400; margin: 0 0 .25rem; }}
  p {{ margin: 0 0 1.25rem; color: #a59cad; max-width: 60rem; }}
  .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(22rem, 1fr)); gap: 1.25rem; }}
  figure {{ margin: 0; }}
  img {{ width: 100%; display: block; border-radius: 6px; }}
  figcaption {{ margin-top: .4rem; }}
  code {{ color: #ffb35c; }}
</style>
<h1>{name}: {count} candidates</h1>
<p>Take a whole one: <code>cp tools/peaks/candidates/{slug}/SEED.svg tools/peaks/svg/{slug}.svg</code>,
then run <code>build</code>. Or set <code>seed=SEED</code> in the view's settings (or
<code>mid_seed</code> / <code>near_seed</code> / <code>ground_seed</code> to mix layers from
different candidates), then <code>generate {slug} --force</code> and <code>build</code>.</p>
<div class="grid">
{cards}
</div>
"""


def candidates(slug, count):
    v = view_by_slug(slug)
    if v.get("manual"):
        sys.exit(f"{slug} is hand-drawn (manual=True); no candidates to make")
    print(f"{slug}: making {count} candidates for {v['name']}...")
    far = path_d(far_layer(v))
    folder = CANDIDATES / slug
    if folder.exists():
        shutil.rmtree(folder)  # only ever holds generated candidates
    folder.mkdir(parents=True)
    cards = []
    for seed in random.sample(range(1_000_000), count):
        seeds = front_seeds(v, seed)
        (folder / f"{seed}.svg").write_text(svg_text(v, {"far": far, **front_layers(v, seeds)}, seeds))
        cards.append(f'<figure><img src="{seed}.svg" alt=""><figcaption>seed {seed}</figcaption></figure>')
    (folder / "index.html").write_text(CANDIDATE_PAGE.format(
        name=v["name"], slug=slug, count=count, cards="\n".join(cards)))
    print(f"  open {(folder / 'index.html').relative_to(ROOT)} in a browser to compare")


# -------------------------------------------------------------------- build ---
def parse_transform(t):
    """SVG transform attribute -> affine matrix (a, b, c, d, e, f)."""
    m = (1, 0, 0, 1, 0, 0)
    for name, args in re.findall(r"(\w+)\s*\(([^)]*)\)", t or ""):
        v = [float(x) for x in re.findall(r"-?[\d.]+(?:e-?\d+)?", args)]
        if name == "matrix": n = tuple(v)
        elif name == "translate": n = (1, 0, 0, 1, v[0], v[1] if len(v) > 1 else 0)
        elif name == "scale": n = (v[0], 0, 0, v[1] if len(v) > 1 else v[0], 0, 0)
        elif name == "rotate":
            r = math.radians(v[0]); cx, cy = (v[1], v[2]) if len(v) > 2 else (0, 0)
            cs, sn = math.cos(r), math.sin(r)
            n = (cs, sn, -sn, cs, cx - cs * cx + sn * cy, cy - sn * cx - cs * cy)
        elif name == "skewX": n = (1, 0, math.tan(math.radians(v[0])), 1, 0, 0)
        elif name == "skewY": n = (1, math.tan(math.radians(v[0])), 0, 1, 0, 0)
        else: continue
        m = mul(m, n)
    return m


def mul(m, n):
    a, b, c, d, e, f = m
    A, B, C, D, E, F = n
    return (a * A + c * B, b * A + d * B, a * C + c * D, b * C + d * D, a * E + c * F + e, b * E + d * F + f)


def normalize_path(d, m):
    """Any SVG path -> absolute M/L/C/Z only (what the site reads fastest),
    with transform m applied. Arcs become short straight segments."""
    toks = re.findall(r"[a-zA-Z]|-?(?:\d+\.?\d*|\.\d+)(?:e[-+]?\d+)?", d)
    out, i, cmd = [], 0, ""
    cx = cy = sx = sy = 0.0
    last_c = last_q = None

    def T(x, y):
        return (m[0] * x + m[2] * y + m[4], m[1] * x + m[3] * y + m[5])

    def emit(c, *pts):
        out.append(c + " " + " ".join(f"{fmt(px)} {fmt(py)}" for px, py in (T(*p) for p in pts)))

    def num():
        nonlocal i
        i += 1
        return float(toks[i - 1])

    while i < len(toks):
        if re.match(r"[a-zA-Z]", toks[i]):
            cmd = toks[i]; i += 1
        rel, C = cmd.islower(), cmd.upper()
        ox, oy = (cx, cy) if rel else (0, 0)
        if C == "Z":
            out.append("Z"); cx, cy = sx, sy; last_c = last_q = None; continue
        if C == "M":
            cx, cy = num() + ox, num() + oy; sx, sy = cx, cy; emit("M", (cx, cy))
            cmd = "l" if rel else "L"; last_c = last_q = None; continue
        if C in "LHV":
            x = num() + ox if C in "LH" else cx
            y = (num() + oy if C == "L" else cy) if C != "V" else num() + oy
            cx, cy = x, y; emit("L", (cx, cy)); last_c = last_q = None; continue
        if C in "CS":
            if C == "C": p1 = (num() + ox, num() + oy)
            else: p1 = (2 * cx - last_c[0], 2 * cy - last_c[1]) if last_c else (cx, cy)
            p2 = (num() + ox, num() + oy); p3 = (num() + ox, num() + oy)
            emit("C", p1, p2, p3); last_c, last_q = p2, None; cx, cy = p3; continue
        if C in "QT":
            if C == "Q": q = (num() + ox, num() + oy)
            else: q = (2 * cx - last_q[0], 2 * cy - last_q[1]) if last_q else (cx, cy)
            p3 = (num() + ox, num() + oy)
            p1 = (cx + 2 / 3 * (q[0] - cx), cy + 2 / 3 * (q[1] - cy))
            p2 = (p3[0] + 2 / 3 * (q[0] - p3[0]), p3[1] + 2 / 3 * (q[1] - p3[1]))
            emit("C", p1, p2, p3); last_q, last_c = q, None; cx, cy = p3; continue
        if C == "A":
            rx, ry, rot, large, sweep = num(), num(), num(), num(), num()
            ex, ey = num() + ox, num() + oy
            for p in arc_points(cx, cy, rx, ry, rot, large, sweep, ex, ey):
                emit("L", p)
            cx, cy = ex, ey; last_c = last_q = None; continue
        raise ValueError(f"unknown path command {cmd!r}")
    return " ".join(out)


def arc_points(x1, y1, rx, ry, rot, large, sweep, x2, y2, segs=12):
    """Endpoints of short lines approximating an SVG elliptical arc."""
    if rx == 0 or ry == 0:
        return [(x2, y2)]
    phi = math.radians(rot)
    cp, sp = math.cos(phi), math.sin(phi)
    dx, dy = (x1 - x2) / 2, (y1 - y2) / 2
    x1p, y1p = cp * dx + sp * dy, -sp * dx + cp * dy
    rx, ry = abs(rx), abs(ry)
    lam = x1p ** 2 / rx ** 2 + y1p ** 2 / ry ** 2
    if lam > 1:
        rx, ry = rx * math.sqrt(lam), ry * math.sqrt(lam)
    num_ = rx ** 2 * ry ** 2 - rx ** 2 * y1p ** 2 - ry ** 2 * x1p ** 2
    co = math.sqrt(max(0, num_ / (rx ** 2 * y1p ** 2 + ry ** 2 * x1p ** 2))) * (-1 if large == sweep else 1)
    cxp, cyp = co * rx * y1p / ry, -co * ry * x1p / rx
    ccx = cp * cxp - sp * cyp + (x1 + x2) / 2
    ccy = sp * cxp + cp * cyp + (y1 + y2) / 2
    ang = lambda ux, uy, vx, vy: math.atan2(ux * vy - uy * vx, ux * vx + uy * vy)
    t1 = ang(1, 0, (x1p - cxp) / rx, (y1p - cyp) / ry)
    dt = ang((x1p - cxp) / rx, (y1p - cyp) / ry, (-x1p - cxp) / rx, (-y1p - cyp) / ry)
    if not sweep and dt > 0: dt -= 2 * math.pi
    if sweep and dt < 0: dt += 2 * math.pi
    pts = []
    for k in range(1, segs + 1):
        t = t1 + dt * k / segs
        pts.append((ccx + rx * math.cos(t) * cp - ry * math.sin(t) * sp,
                    ccy + rx * math.cos(t) * sp + ry * math.sin(t) * cp))
    return pts


INK = "{http://www.inkscape.org/namespaces/inkscape}"
SVGNS = "{http://www.w3.org/2000/svg}"


def read_layers(svg_file):
    """{layer name: path data} from an SVG, with all transforms applied."""
    root = ET.parse(svg_file).getroot()
    found = {}

    def walk(el, m, layer):
        m = mul(m, parse_transform(el.get("transform")))
        label = el.get(INK + "label") or el.get("id")
        if el.tag == SVGNS + "g" and label in LAYERS:
            layer = label
        if el.tag == SVGNS + "path" and layer:
            found.setdefault(layer, []).append(normalize_path(el.get("d", ""), m))
        for child in el:
            walk(child, m, layer)

    walk(root, (1, 0, 0, 1, 0, 0), None)
    return {k: " ".join(v) for k, v in found.items()}


def checks(name, layers):
    """Warn about things that would look wrong on the site."""
    def points(d):
        nums = [float(x) for x in re.findall(r"-?\d+(?:\.\d+)?", d)]
        return list(zip(nums[0::2], nums[1::2]))
    right = [y for x, y in points(layers.get("ground", "")) if x >= 1250 and y < 999]
    if right and max(right) > GROUND_MAX_Y + 6:
        print(f"  ! {name}: ground dips to y={max(right):.0f} on the right (keep it above "
              f"{GROUND_MAX_Y + 6}), or the range menu moves down for every range")
    far = sorted(points(layers.get("far", "")), key=lambda p: abs(p[0] - 800))
    if far:
        shown = max(0, far[0][1] - 280)
        print(f"  {name}: about {shown:.0f} of the sun's 440 height shows above the far layer at the centre")


def build():
    entries = []
    for v in VIEWS:
        svg = SVG_DIR / f"{v['slug']}.svg"
        if not svg.exists():
            print(f"{v['slug']}: no SVG yet (run `generate` first); skipped")
            continue
        layers = read_layers(svg)
        missing = [n for n in LAYERS if n not in layers]
        if missing:
            print(f"{v['slug']}: missing layer(s) {', '.join(missing)}; skipped")
            continue
        checks(v["name"], layers)
        entries.append((v["name"], layers))
    lines = ["// Generated by tools/peaks/skyline.py build: edit the SVGs in tools/peaks/svg/",
             "// and re-run it instead of editing this file.",
             "// (The site lists \"mountains\" from ranges.js first, then these, then the egg.)",
             "const PEAKS = ["]
    for name, layers in entries:
        lines.append("  {")
        lines.append(f'    name: "{name}",')
        lines += [f'    {k}: "{layers[k]}",' for k in LAYERS]
        lines.append("  },")
    lines.append("];")
    OUT.write_text("\n".join(lines) + "\n")
    print(f"wrote {len(entries)} views to {OUT.relative_to(ROOT)} ({OUT.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args or args[0] not in ("generate", "candidates", "build"):
        sys.exit(__doc__)
    if args[0] == "generate":
        generate([a for a in args[1:] if not a.startswith("--")], "--force" in args)
    elif args[0] == "candidates":
        if len(args) < 2:
            sys.exit("usage: skyline.py candidates <slug> [count]")
        candidates(args[1], int(args[2]) if len(args) > 2 else 12)
    else:
        build()
