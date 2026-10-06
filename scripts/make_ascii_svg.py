from __future__ import annotations

import argparse
from html import escape
from pathlib import Path

from PIL import Image, ImageEnhance, ImageOps

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "data" / "source-prepped.png"
DEFAULT_OUTPUT = ROOT / "assets" / "mortaki-ascii.svg"
RAMP = " .`:-=+*cs#%@"

FALLBACK = [
    "              .:-=++++=-:.              ",
    "          .-+*c##########c*+-.          ",
    "        :+c##################c+:        ",
    "      :c#########%%%%##########c:      ",
    "     +########%@@@@@@@@%########+     ",
    "    *#######%@@%#c**c#%@@%#######*    ",
    "   c#######%@#*=:.  .:=*#@%#######c   ",
    "  +#######%@c:.        .:c@%#######+  ",
    "  c######%@*.    .::.    .*@%######c  ",
    "  #######%@-   .+####+.   -@%#######  ",
    "  #######%@-   :######:   -@%#######  ",
    "  c######%@*.   -+##+-   .*@%######c  ",
    "  +#######%@c:.  ..  .:c@%#######+  ",
    "   c#######%@@#*=----=*#@@%#######c   ",
    "    *########%@@@@@@@@%########*    ",
    "     +##########%%%%##########+     ",
    "      :c####################c:      ",
    "        :+c################c+:        ",
    "          .-+*c########c*+-.          ",
    "              .:-====-:.              ",
    "",
    "            M O R T A K I 0            ",
]


def image_rows(path: Path, cols: int = 76, rows: int = 42) -> list[str]:
    image = Image.open(path).convert("L")
    image = ImageOps.autocontrast(image)
    image = ImageEnhance.Contrast(image).enhance(1.25)
    image = image.resize((cols, rows), Image.Resampling.LANCZOS)

    lines: list[str] = []
    for y in range(rows):
        chars = []
        for x in range(cols):
            value = image.getpixel((x, y))
            density = (255 - value) / 255
            idx = round(density * (len(RAMP) - 1))
            char = RAMP[max(0, min(len(RAMP) - 1, idx))]
            # Clear very bright pixels completely.
            if value > 238:
                char = " "
            chars.append(char)
        lines.append("".join(chars).rstrip())
    return lines


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert a prepared portrait to a self-typing ASCII SVG")
    parser.add_argument("--input", default=str(DEFAULT_INPUT))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--fallback", action="store_true", help="emit built-in terminal identity art")
    args = parser.parse_args()

    source = Path(args.input)
    rows = FALLBACK if args.fallback or not source.exists() else image_rows(source)

    width = 370
    line_h = 7.1
    top = 23
    height = int(top + len(rows) * line_h + 18)
    text_x = 12
    wipe_w = width - 24
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">',
        '<title id="title">Abdelilah MORTAKI ASCII portrait</title>',
        '<desc id="desc">Monochrome terminal-style portrait that types itself row by row.</desc>',
        f'<rect width="{width}" height="{height}" rx="14" fill="#0d1117" stroke="#30363d"/>',
        '<text x="12" y="15" fill="#8b949e" font-size="8" font-family="ui-monospace,SFMono-Regular,Menlo,Consolas,monospace">./identity --render ascii</text>',
        '<defs>',
    ]

    for idx in range(len(rows)):
        begin = idx * 0.045
        y = top + idx * line_h
        out.append(f'<clipPath id="r{idx}"><rect x="{text_x}" y="{y - 6}" width="0" height="8"><animate attributeName="width" from="0" to="{wipe_w}" dur=".32s" begin="{begin:.3f}s" fill="freeze"/></rect></clipPath>')
    out.append('</defs>')

    for idx, row in enumerate(rows):
        begin = idx * 0.045
        y = top + idx * line_h
        out.append(f'<text x="{text_x}" y="{y:.1f}" fill="#c9d1d9" font-size="6.2" font-family="ui-monospace,SFMono-Regular,Menlo,Consolas,monospace" xml:space="preserve" clip-path="url(#r{idx})">{escape(row)}</text>')
        out.append(f'<rect x="{text_x}" y="{y - 5.8:.1f}" width="3" height="6.3" fill="#58a6ff" opacity="0"><animate attributeName="opacity" values="0;1;1;0" keyTimes="0;.05;.86;1" dur=".36s" begin="{begin:.3f}s" fill="freeze"/><animate attributeName="x" from="{text_x}" to="{text_x + wipe_w - 3}" dur=".32s" begin="{begin:.3f}s" fill="freeze"/></rect>')

    out.append('</svg>')
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"wrote {output}")


if __name__ == "__main__":
    main()
