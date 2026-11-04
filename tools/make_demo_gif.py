"""Render docs/demo.gif: a terminal that mines a contract and catches three drifts.

Drawn with Pillow rather than screened from a real terminal, so the timing and
the framing are deterministic and the file stays small enough for a README.

    python tools/make_demo_gif.py docs/demo.gif
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

W, H = 920, 524
PAD_X, PAD_TOP = 26, 26
LINE_H = 23
FPS = 75  # ms per frame

BG = (22, 23, 27)
BAR = (32, 33, 38)
TXT = (214, 219, 227)
DIM = (112, 120, 132)
GREEN = (76, 195, 138)
RED = (255, 92, 87)
AMBER = (243, 178, 60)
CYAN = (110, 200, 220)

FONT_CANDIDATES = [
    "C:/Windows/Fonts/consola.ttf",
    "/System/Library/Fonts/Menlo.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
]


def load_font(size: int) -> ImageFont.FreeTypeFont:
    for path in FONT_CANDIDATES:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    return ImageFont.load_default()


FONT = load_font(15)
FONT_BOLD = load_font(15)


def chrome() -> Image.Image:
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, 34], fill=BAR)
    for i, c in enumerate(((255, 95, 86), (255, 189, 46), (39, 201, 63))):
        d.ellipse([16 + i * 22, 12, 28 + i * 22, 24], fill=c)
    d.text((W - 150, 10), "agent-contract", font=FONT, fill=DIM)
    return img


def render(lines, cursor: bool = False, flash=None) -> Image.Image:
    img = chrome()
    if flash:
        overlay = Image.new("RGB", (W, H), flash)
        img = Image.blend(img, overlay, 0.12)
    d = ImageDraw.Draw(img)
    y = 34 + PAD_TOP
    for text, color in lines:
        d.text((PAD_X, y), text, font=FONT, fill=color)
        y += LINE_H
    if cursor and lines:
        last_text, _ = lines[-1]
        cx = PAD_X + FONT.getlength(last_text)
        cy = 34 + PAD_TOP + (len(lines) - 1) * LINE_H
        d.rectangle([cx + 1, cy + 1, cx + 9, cy + 16], fill=TXT)
    return img


CMD1 = "$ agent-contract mine --traces traces/ -o contract.json"
OUT1 = [
    ("mined 20 assertions from 40 traces  (shape 13, action 6, drift 1)", DIM),
    ("  every assertion carries the evidence that justified it", DIM),
]
CMD2 = "$ agent-contract run --contract contract.json --target traces-candidate/"
OUT2 = [
    ("", TXT),
    ("agent-contract · 20 assertions · 40 target traces", TXT),
    ("", TXT),
    ("RED   A10  shape.tool_result_not_empty   search_docs never returns empty", RED),
    ("          2/40 calls returned an empty result (5.0%)", DIM),
    ("RED   A16  action.path_within_root       read_file stays inside docs", RED),
    ("          1/40 paths escaped: ../secrets/key.pem", DIM),
    ("RED   A20  drift.batch                   answers stay the same", RED),
    ("          5/40 drifted · facts lost: ['duration:7days']", DIM),
    ("AMBER A14  action.tool_allowed           new tool: escalate_to_human", AMBER),
    ("", TXT),
    ("3 red · 2 amber · 15 green   →   FAIL", RED),
]
FLASH_ON = [3, 5, 7]  # indices in OUT2 that get a red flash


def build_frames():
    frames = []

    def push(lines, cursor=False, flash=None, hold=1):
        img = render(lines, cursor=cursor, flash=flash)
        for _ in range(hold):
            frames.append(img)

    base = [("last run: no crash, exit code 0", DIM), ("", TXT)]

    # typing command 1
    typed = ""
    for i in range(0, len(CMD1) + 1, 3):
        typed = CMD1[:i]
        push(base + [(typed, TXT)], cursor=True)
    push(base + [(CMD1, TXT)], cursor=False, hold=3)

    # output 1
    screen = base + [(CMD1, TXT)]
    for line in OUT1:
        screen = screen + [line]
        push(screen, hold=2)
    push(screen, hold=5)

    # typing command 2
    screen = screen + [("", TXT)]
    typed = ""
    for i in range(0, len(CMD2) + 1, 3):
        typed = CMD2[:i]
        push(screen + [(typed, TXT)], cursor=True)
    push(screen + [(CMD2, TXT)], hold=3)

    # output 2, one line at a time with flashes on the reds
    head = screen + [(CMD2, TXT)]
    shown = list(head)
    for idx, (text, color) in enumerate(OUT2):
        shown = shown + [(text, color)]
        flash = RED if idx in FLASH_ON else None
        push(shown, flash=flash, hold=2 if flash else 1)
    push(shown, hold=26)  # hold the verdict
    return frames


def main() -> int:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "docs/demo.gif")
    out.parent.mkdir(parents=True, exist_ok=True)
    frames = build_frames()
    pal = [f.convert("P", palette=Image.ADAPTIVE, colors=64) for f in frames]
    pal[0].save(out, save_all=True, append_images=pal[1:], duration=FPS, loop=0,
                optimize=True, disposal=2)
    print("wrote", out, out.stat().st_size // 1024, "KB,", len(frames), "frames")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())