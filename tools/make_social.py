"""Render the 1280x640 social preview card (GitHub repo → Settings → Social preview).

Same hand-sketched vocabulary as the architecture diagram, so the repo looks
like one thing rather than a pile of assets.

    python tools/make_social.py docs/social.png
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from make_diagram import (  # noqa: E402
    GREEN, INK, PAPER, FADE, RED, marker, sketch, rough_rect, text, dot,
)

AMBER = "#D69A2D"

W, H = 1280, 640


def build() -> str:
    s = []
    s.append('<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" '
             'viewBox="0 0 %d %d">' % (W, H, W, H))
    s.append('<rect width="%d" height="%d" fill="%s"/>' % (W, H, PAPER))

    # frame
    s.append(sketch(rough_rect(26, 26, W - 52, H - 52, bow=3.0), stroke="#D8D0BE", width=1.8))

    s.append(text(72, 118, "agent-contract", size=64, weight="bold", tilt=-0.5))
    s.append(marker(70, 60, 560, 26, opacity=0.45, tilt=-0.3))

    s.append(text(74, 172, "silent failures, caught before the merge",
                  size=26, color="#3C3A35", tilt=-0.2))

    # the hook
    s.append(text(74, 268, "your agent changed.", size=34, color=INK, tilt=-0.3))
    s.append(text(74, 316, "nothing crashed.", size=34, color=INK, tilt=-0.3))
    s.append(text(74, 364, "every answer is wrong.", size=34, color=RED, weight="bold", tilt=-0.4))

    # traffic lights
    for i, (c, label) in enumerate(((RED, "red"), ("#D69A2D", "amber"), (GREEN, "green"))):
        s.append(dot(96 + i * 92, 452, 17, c))
        s.append(text(96 + i * 92, 496, label, size=19, color=FADE, anchor="middle"))

    s.append(text(74, 556, "mine a contract from your traces · run it on every model swap",
                  size=20, color="#5A564E", tilt=-0.2))

    # right: a sketch of the terminal verdict
    s.append(sketch(rough_rect(720, 170, 480, 300, bow=2.6), stroke=INK, width=2.2, fill="#FFFFFF"))
    s.append(text(748, 214, "$ agent-contract run", size=21, weight="bold", tilt=-0.3))
    s.append(text(748, 244, "--contract contract.json", size=17, color="#6B665C"))
    s.append(sketch(rough_rect(748, 262, 424, 1.2, bow=0.4), stroke="#D8D0BE", width=1.2))
    rows = [
        ("RED    A16  path escaped docs", RED),
        ("RED    A20  7 days → 3 days", RED),
        ("AMBER  A14  new tool surfaced", AMBER),
    ]
    for i, (line, color) in enumerate(rows):
        s.append(text(752, 302 + i * 38, line, size=20, color=color))
    s.append(sketch(rough_rect(748, 400, 424, 1.2, bow=0.4), stroke="#D8D0BE", width=1.2))
    s.append(text(752, 442, "3 red · 2 amber · 15 green", size=20, color="#3C3A35"))

    s.append(text(1210, 588, "github.com/bandageok/agent-contract", size=17,
                  color=FADE, anchor="end"))
    s.append("</svg>")
    return "".join(s)


def main() -> int:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "docs/social.png")
    out.parent.mkdir(parents=True, exist_ok=True)
    svg = out.with_suffix(".svg")
    svg.write_text(build(), encoding="utf-8")
    print("wrote", svg)

    from make_diagram import render_png
    # render_png uses the diagram's own W/H window; social is 1280x640
    import make_diagram
    make_diagram.W, make_diagram.H = W, H
    render_png(svg, out, scale=1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())