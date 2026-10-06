from __future__ import annotations

import os
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "assets" / "info-card.svg"
STATIC = os.environ.get("STATIC") == "1"

ROWS = [
    ("user", "Abdelilah MORTAKI"),
    ("handle", "@MORTAKI0"),
    ("role", "AI / Full-Stack Developer"),
    ("focus", "agentic systems + developer tooling"),
    ("build", "EGAWILLDOIT"),
    ("stack", "TS · Python · Next.js · FastAPI"),
    ("data", "Supabase · PostgreSQL"),
    ("infra", "Linux · GitHub Actions · Vercel"),
    ("ship", "EGA House · EGA Skills · ShipLoop"),
]


def main() -> None:
    width = 490
    height = 330
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">',
        '<title id="title">Abdelilah MORTAKI terminal profile</title>',
        '<desc id="desc">Neofetch-style profile card with current focus, stack, and projects.</desc>',
        '<rect width="490" height="330" rx="14" fill="#0d1117" stroke="#30363d"/>',
        '<circle cx="18" cy="18" r="5" fill="#ff5f56"/><circle cx="36" cy="18" r="5" fill="#ffbd2e"/><circle cx="54" cy="18" r="5" fill="#27c93f"/>',
        '<text x="245" y="22" fill="#8b949e" font-size="10" text-anchor="middle" font-family="ui-monospace,SFMono-Regular,Menlo,Consolas,monospace">mortaki@github:~</text>',
        '<style>',
        "text{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}",
        ".key{fill:#58a6ff;font-weight:700}.value{fill:#c9d1d9}.prompt{fill:#39d353}",
        "@keyframes linein{0%{opacity:0;transform:translateX(-8px)}100%{opacity:1;transform:translateX(0)}}",
        ".line{animation:linein .32s ease-out both}",
        '</style>',
        '<text x="20" y="50" class="prompt" font-size="12">$ neofetch --profile</text>',
    ]

    for idx, (key, value) in enumerate(ROWS):
        y = 82 + idx * 25
        delay = 0 if STATIC else 0.18 + idx * 0.10
        opacity = '1' if STATIC else '0'
        out.append(f'<g class="line" style="animation-delay:{delay:.2f}s;opacity:{opacity}">')
        out.append(f'<text x="22" y="{y}" class="key" font-size="11">{escape(f"{key:<8}")}</text>')
        out.append(f'<text x="92" y="{y}" class="value" font-size="11">{escape(value)}</text>')
        out.append('</g>')

    out.append('<text x="20" y="315" class="prompt" font-size="11">$</text>')
    if not STATIC:
        out.append('<rect x="31" y="305" width="7" height="12" fill="#c9d1d9"><animate attributeName="opacity" values="1;0;1" dur="1s" repeatCount="indefinite"/></rect>')
    else:
        out.append('<rect x="31" y="305" width="7" height="12" fill="#c9d1d9"/>')
    out.append('</svg>')

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"wrote {OUTPUT}")


if __name__ == "__main__":
    main()
