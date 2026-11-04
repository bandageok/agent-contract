"""Draw the architecture diagram in a hand-sketched style.

Everything is emitted as plain SVG presentation attributes (no <style>, no
filters), because GitHub sanitises SVG in READMEs and strips both. The hand
drawn feel comes from jittered bezier edges and doubled strokes, so it survives
sanitisation and any viewer.

    python tools/make_diagram.py docs/architecture.svg
"""

from __future__ import annotations

import math
import random
import sys
from pathlib import Path

W, H = 1000, 640
PAPER = "#FFFDF7"
INK = "#2A2A2A"
BLUE = "#2C6E9B"
RED = "#C94A3F"
GREEN = "#2E7D4F"
FADE = "#8A8378"
HILITE = "#FFE9A8"
FONT = "'Patrick Hand','Segoe Print','Bradley Hand','Comic Sans MS',cursive"

_seed = random.Random(20261104)


def jitter(amount: float = 1.3) -> float:
    return _seed.uniform(-amount, amount)


def rough_rect(x: float, y: float, w: float, h: float, *, bow: float = 2.2) -> str:
    """A rectangle whose edges bow slightly, like a pen drawn box."""
    pts = [(x + jitter(), y + jitter()), (x + w + jitter(), y + jitter()),
           (x + w + jitter(), y + h + jitter()), (x + jitter(), y + h + jitter())]
    parts = []
    for i in range(4):
        ax, ay = pts[i]
        bx, by = pts[(i + 1) % 4]
        mx, my = (ax + bx) / 2, (ay + by) / 2
        dx, dy = bx - ax, by - ay
        length = math.hypot(dx, dy) or 1.0
        nx, ny = -dy / length, dx / length
        off = jitter(bow)
        cx, cy = mx + nx * off, my + ny * off
        parts.append("M%.1f,%.1f Q%.1f,%.1f %.1f,%.1f" % (ax, ay, cx, cy, bx, by))
    parts.append("Z")
    return " ".join(parts)


def sketch(inner: str, stroke: str = INK, width: float = 2.0, fill: str = "none",
           dash: str = "") -> str:
    """Draw the same shape twice with a slight offset, the way a pen doubles back."""
    d = ' stroke-dasharray="%s"' % dash if dash else ""
    return (
        '<path d="%s" fill="%s" stroke="%s" stroke-width="%.1f" stroke-linejoin="round" '
        'stroke-linecap="round"%s/>' % (inner, fill, stroke, width, d)
        + '<path d="%s" fill="none" stroke="%s" stroke-width="%.1f" opacity="0.35" '
          'transform="translate(0.9,0.7)" stroke-linecap="round"%s/>'
        % (inner, stroke, max(0.8, width * 0.6), d)
    )


def box(x, y, w, h, *, stroke=BLUE, fill="none", width=2.0, dash="") -> str:
    return sketch(rough_rect(x, y, w, h), stroke=stroke, width=width, fill=fill, dash=dash)


def arrow(x1, y1, x2, y2, *, stroke=INK, width=1.9, dash="", head=9.0) -> str:
    ang = math.atan2(y2 - y1, x2 - x1)
    out = ['<path d="M%.1f,%.1f Q%.1f,%.1f %.1f,%.1f" fill="none" stroke="%s" '
           'stroke-width="%.1f" stroke-linecap="round"%s/>'
           % (x1, y1, (x1 + x2) / 2 + jitter(1.6), (y1 + y2) / 2 + jitter(1.6), x2, y2,
              stroke, width, ' stroke-dasharray="%s"' % dash if dash else "")]
    for side in (0.42, -0.42):
        hx = x2 - head * math.cos(ang - side)
        hy = y2 - head * math.sin(ang - side)
        out.append('<path d="M%.1f,%.1f L%.1f,%.1f" fill="none" stroke="%s" '
                   'stroke-width="%.1f" stroke-linecap="round"/>' % (hx, hy, x2, y2, stroke, width))
    return "".join(out)


def curve(x1, y1, x2, y2, c1x, c1y, c2x, c2y, *, stroke=GREEN, dash="5 5") -> str:
    return ('<path d="M%.1f,%.1f C%.1f,%.1f %.1f,%.1f %.1f,%.1f" fill="none" stroke="%s" '
            'stroke-width="1.8" stroke-dasharray="%s" stroke-linecap="round"/>'
            % (x1, y1, c1x, c1y, c2x, c2y, x2, y2, stroke, dash))


def text(x, y, s, *, size=14, color=INK, weight="normal", anchor="start", tilt=0.0,
         family=FONT) -> str:
    rot = ' transform="rotate(%.2f %.1f %.1f)"' % (tilt, x, y) if tilt else ""
    return ('<text x="%.1f" y="%.1f" font-family="%s" font-size="%d" fill="%s" '
            'font-weight="%s" text-anchor="%s"%s>%s</text>'
            % (x, y, family, size, color, weight, anchor, rot, s))


def marker(x, y, w, h, *, fill=HILITE, opacity=0.6, tilt=-0.7) -> str:
    """A highlighter swipe, slightly off-axis."""
    return ('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" fill="%s" opacity="%.2f" '
            'transform="rotate(%.2f %.1f %.1f)"/>'
            % (x, y, w, h, fill, opacity, tilt, x + w / 2, y + h / 2))


def doc_icon(x, y, w, h, *, stroke=BLUE) -> str:
    """A page with a folded corner and a few ruled lines."""
    fold = 14
    body = ("M%.1f,%.1f L%.1f,%.1f L%.1f,%.1f L%.1f,%.1f L%.1f,%.1f Z"
            % (x, y, x + w - fold, y, x + w, y + fold, x + w, y + h, x, y + h))
    out = [sketch(body, stroke=stroke, width=2.0, fill="none")]
    out.append('<path d="M%.1f,%.1f L%.1f,%.1f L%.1f,%.1f" stroke="%s" stroke-width="1.5" '
               'fill="none" stroke-linejoin="round"/>'
               % (x + w - fold, y, x + w - fold, y + fold, x + w, y + fold, stroke))
    return "".join(out)


def dot(cx, cy, r, color) -> str:
    return '<circle cx="%.1f" cy="%.1f" r="%.1f" fill="%s" opacity="0.85"/>' % (cx, cy, r, color)


def build() -> str:
    s = []
    s.append('<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" '
             'viewBox="0 0 %d %d" role="img" '
             'aria-label="Where agent-contract sits: outside the request path">' % (W, H, W, H))
    s.append('<rect width="%d" height="%d" fill="%s"/>' % (W, H, PAPER))

    # ---- title
    s.append(marker(40, 24, 424, 22, opacity=0.45))
    s.append(text(40, 40, "where agent-contract sits", size=31, weight="bold", tilt=-0.4))
    s.append(text(40, 70, "outside the request path — it only reads what you already log",
                  size=15, color=FADE, tilt=-0.2))

    # ---- lane A: baseline
    s.append(box(30, 92, 940, 200, stroke="#C9C2B4", width=1.6, dash="7 6"))
    s.append(text(44, 116, "① once — learn what correct looks like", size=16, color=BLUE,
                  weight="bold", tilt=-0.3))

    s.append(box(55, 132, 178, 124, stroke=INK))
    s.append(text(68, 156, "agent loop", size=16, weight="bold", tilt=-0.3))
    for i, line in enumerate(("prompt + model", "tool calls", "memory")):
        s.append(text(72, 182 + i * 22, "· " + line, size=13, color="#4A4A4A"))
    s.append(text(144, 250, "yours, unchanged", size=11, color=FADE, anchor="middle"))

    s.append(arrow(238, 194, 268, 194))
    s.append(text(253, 182, "writes", size=11, color=FADE, anchor="middle"))

    s.append(doc_icon(272, 148, 165, 92))
    s.append(text(354, 172, "traces/*.jsonl", size=14, anchor="middle", weight="bold"))
    s.append(text(354, 192, "input · steps · output", size=11, color=FADE, anchor="middle"))
    s.append(text(354, 212, "your existing logs", size=11, color=FADE, anchor="middle"))

    s.append(arrow(442, 194, 474, 194))
    s.append(box(478, 154, 104, 80, stroke=INK, fill="#FFFFFF"))
    s.append(text(530, 186, "mine", size=17, anchor="middle", weight="bold"))
    s.append(text(530, 208, "no model call", size=11, color=GREEN, anchor="middle"))

    s.append(arrow(588, 194, 618, 194))
    s.append(doc_icon(622, 142, 200, 104, stroke=GREEN))
    s.append(text(722, 170, "contract.json", size=14, anchor="middle", weight="bold"))
    s.append(text(722, 190, "+ baseline sidecar", size=11, color=FADE, anchor="middle"))
    s.append(text(722, 208, "every input captured", size=11, color=FADE, anchor="middle"))
    s.append(text(722, 230, "reviewed like code", size=11, color=GREEN, anchor="middle"))

    s.append(text(958, 150, "read-only.", size=15, color=RED, weight="bold", anchor="end", tilt=-2.0))
    s.append(text(958, 174, "never touches", size=13, color=RED, anchor="end", tilt=-2.0))
    s.append(text(958, 194, "your code.", size=13, color=RED, anchor="end", tilt=-2.0))

    # ---- lane B: every change
    s.append(box(30, 322, 940, 244, stroke="#C9C2B4", width=1.6, dash="7 6"))
    s.append(text(44, 346, "② every change — swap the model, edit a prompt, bump a dependency",
                  size=16, color=BLUE, weight="bold", tilt=-0.3))

    s.append(box(55, 372, 178, 124, stroke=INK))
    s.append(text(68, 396, "same prompts", size=15, weight="bold", tilt=-0.3))
    s.append(text(68, 420, "new model", size=13, color="#4A4A4A"))
    s.append(text(68, 440, "or new prompt", size=13, color="#4A4A4A"))
    s.append(text(68, 460, "or new dep", size=13, color="#4A4A4A"))
    s.append(text(144, 486, "a replay", size=11, color=FADE, anchor="middle"))

    s.append(arrow(238, 434, 268, 434))
    s.append(text(253, 422, "writes", size=11, color=FADE, anchor="middle"))

    s.append(doc_icon(272, 388, 165, 92))
    s.append(text(354, 412, "candidate traces", size=14, anchor="middle", weight="bold"))
    s.append(text(354, 432, "same inputs,", size=11, color=FADE, anchor="middle"))
    s.append(text(354, 450, "different answers?", size=11, color=FADE, anchor="middle"))

    s.append(arrow(442, 434, 474, 434))
    s.append(box(478, 394, 104, 80, stroke=INK, fill="#FFFFFF"))
    s.append(text(530, 426, "run", size=17, anchor="middle", weight="bold"))
    s.append(text(530, 448, "no model call", size=11, color=GREEN, anchor="middle"))

    s.append(arrow(588, 434, 618, 434))
    s.append(box(622, 378, 158, 112, stroke=INK, fill="#FFFFFF"))
    s.append(text(701, 402, "report", size=15, anchor="middle", weight="bold"))
    for i, (c, label) in enumerate(((RED, "red"), ("#D69A2D", "amber"), (GREEN, "green"))):
        s.append(dot(652 + i * 41, 424, 7, c))
        s.append(text(652 + i * 41, 450, label, size=9, color=FADE, anchor="middle"))
    s.append(text(701, 472, "which behaviour moved", size=10, color=FADE, anchor="middle"))

    s.append(arrow(786, 434, 812, 434))
    s.append(box(816, 404, 138, 62, stroke=RED, fill="#FFFFFF"))
    s.append(text(885, 428, "CI gate", size=15, anchor="middle", weight="bold"))
    s.append(text(885, 448, "merge / block", size=11, color=RED, anchor="middle"))

    # ---- contract feeds run
    s.append(curve(722, 250, 542, 390, 722, 322, 542, 322))
    s.append(text(530, 486, "uses contract.json", size=11, color=GREEN, anchor="middle"))

    # ---- bottom note
    s.append(marker(30, 586, 470, 10, opacity=0.45, tilt=-0.3))
    s.append(text(34, 598, "no latency added · no calls intercepted · no data leaves the machine",
                  size=14, tilt=-0.2))
    s.append(text(950, 598, "v0.1.0", size=12, color=FADE, anchor="end"))

    s.append("</svg>")
    return "".join(s)


def _find_chrome() -> str:
    import os
    import shutil

    candidates = [
        os.environ.get("CHROME_PATH", ""),
        r"C:/Program Files/Google/Chrome/Application/chrome.exe",
        r"C:/Program Files (x86)/Google/Chrome/Application/chrome.exe",
        r"C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/usr/bin/google-chrome",
        "/usr/bin/chromium",
        "/usr/bin/chromium-browser",
    ]
    for path in candidates:
        if path and Path(path).exists():
            return path
    for name in ("google-chrome", "chromium", "chrome", "msedge"):
        found = shutil.which(name)
        if found:
            return found
    return ""


def render_png(svg_path: Path, png_path: Path, scale: int = 2) -> bool:
    """Screenshot the SVG with a headless browser.

    A browser is used instead of an SVG rasteriser because the diagram depends
    on a handwriting font stack that only a full renderer resolves.
    """
    import subprocess
    import tempfile

    chrome = _find_chrome()
    if not chrome:
        print("no chrome/chromium found; set CHROME_PATH to render the png")
        return False
    svg = svg_path.read_text(encoding="utf-8")
    html = ("<!doctype html><html><head><meta charset='utf-8'></head>"
            "<body style='margin:0;background:#FFFDF7'>%s</body></html>" % svg)
    with tempfile.TemporaryDirectory(dir=str(svg_path.parent.resolve())) as tmp:
        page = Path(tmp) / "page.html"
        page.write_text(html, encoding="utf-8")
        png_path.parent.mkdir(parents=True, exist_ok=True)
        profile = (Path(tmp) / "profile").as_posix()
        cmd = [chrome, "--headless=new", "--disable-gpu", "--hide-scrollbars",
               "--no-first-run", "--user-data-dir=%s" % profile,
               "--force-device-scale-factor=%d" % scale,
               "--window-size=%d,%d" % (W, H),
               "--screenshot=%s" % png_path.resolve().as_posix(),
               page.resolve().as_posix().replace("file:", "")]
        cmd[-1] = "file:///" + cmd[-1].lstrip("/")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120,
                               encoding="utf-8", errors="replace")
        if not png_path.exists():
            print("render failed:", (result.stderr or result.stdout).strip()[:300])
            return False
    print("wrote", png_path, png_path.stat().st_size, "bytes")
    return True


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Draw the architecture diagram.")
    parser.add_argument("out", nargs="?", default="docs/architecture.svg")
    parser.add_argument("--png", nargs="?", const="__auto__", default=None,
                        help="also render a PNG (defaults to the SVG path with .png)")
    parser.add_argument("--scale", type=int, default=2)
    args = parser.parse_args()

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build(), encoding="utf-8")
    print("wrote", out, out.stat().st_size, "bytes")

    if args.png is not None:
        png = out.with_suffix(".png") if args.png == "__auto__" else Path(args.png)
        render_png(out, png, scale=args.scale)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())