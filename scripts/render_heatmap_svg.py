from __future__ import annotations

import json
from datetime import date, timedelta
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "data" / "contributions.json"
OUTPUT = ROOT / "assets" / "contrib-heatmap.svg"
PALETTE = ["#161b22", "#0e4429", "#006d32", "#26a641", "#39d353", "#69f0a0"]

WIDTH = 860
HEIGHT = 188
LEFT = 42
TOP = 42
CELL = 10
GAP = 3
STEP = CELL + GAP


def format_number(value: int) -> str:
    return f"{value:,}"


def main() -> None:
    payload = json.loads(INPUT.read_text(encoding="utf-8"))
    days = {item["date"]: item for item in payload["days"]}
    if not days:
        raise RuntimeError("No contribution days available")

    last = date.fromisoformat(max(days))
    week_start = last - timedelta(days=(last.weekday() + 1) % 7)  # Sunday
    first = week_start - timedelta(weeks=52)

    stats = payload.get("stats", {})
    total = int(stats.get("total", 0))
    current = int(stats.get("current_streak", 0))
    longest = int(stats.get("longest_streak", 0))

    out: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}" role="img" aria-labelledby="title desc">',
        f'<title id="title">{escape(payload.get("username", "GitHub"))} contribution heatmap</title>',
        f'<desc id="desc">{format_number(total)} contributions across the last 53 weeks.</desc>',
        '<rect width="860" height="188" rx="14" fill="#0d1117" stroke="#30363d"/>',
        '<style>',
        "text{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}",
        ".muted{fill:#8b949e}.main{fill:#c9d1d9}",
        "@keyframes reveal{0%{opacity:0;transform:translateY(7px)}100%{opacity:1;transform:translateY(0)}}",
        ".day{opacity:0;animation:reveal .34s cubic-bezier(.2,.7,.2,1) forwards;transform-box:fill-box;transform-origin:center}",
        '</style>',
        '<text x="22" y="24" class="main" font-size="12" font-weight="700">github contribution activity</text>',
    ]

    month_labels: set[tuple[int, int]] = set()
    cursor = first
    for col in range(53):
        week = first + timedelta(weeks=col)
        for row in range(7):
            day = week + timedelta(days=row)
            if day > last:
                continue
            item = days.get(day.isoformat(), {"count": 0, "level": 0})
            level = max(0, min(5, int(item.get("level", 0))))
            x = LEFT + col * STEP
            y = TOP + row * STEP
            delay = 0.035 * (col + row)
            title = f'{day.isoformat()}: {item.get("count", 0)} contribution' + ("" if item.get("count", 0) == 1 else "s")
            out.append(
                f'<rect class="day" x="{x}" y="{y}" width="{CELL}" height="{CELL}" rx="2" fill="{PALETTE[level]}" style="animation-delay:{delay:.3f}s"><title>{escape(title)}</title></rect>'
            )
        month_key = (week.year, week.month)
        if month_key not in month_labels and week.day <= 7:
            month_labels.add(month_key)
            out.append(
                f'<text x="{LEFT + col * STEP}" y="35" class="muted" font-size="9">{week.strftime("%b")}</text>'
            )

    for label, row in [("Mon", 1), ("Wed", 3), ("Fri", 5)]:
        out.append(f'<text x="10" y="{TOP + row * STEP + 8}" class="muted" font-size="8">{label}</text>')

    legend_y = 151
    out.append(f'<text x="22" y="{legend_y}" class="muted" font-size="9">Less</text>')
    for idx, color in enumerate(PALETTE):
        out.append(f'<rect x="{52 + idx * 15}" y="{legend_y - 9}" width="10" height="10" rx="2" fill="{color}"/>')
    out.append(f'<text x="{52 + len(PALETTE) * 15}" y="{legend_y}" class="muted" font-size="9">More</text>')

    footer = f"{format_number(total)} contributions · current streak {current}d · longest {longest}d"
    out.append(f'<text x="838" y="151" class="main" font-size="10" text-anchor="end">{escape(footer)}</text>')
    out.append('<text x="22" y="174" class="muted" font-size="8">generated from github.com/users/MORTAKI0/contributions · refreshed daily</text>')
    out.append('</svg>')

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"wrote {OUTPUT}")


if __name__ == "__main__":
    main()
