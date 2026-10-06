from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

USERNAME = "MORTAKI0"
ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data" / "contributions.json"
URL = f"https://github.com/users/{USERNAME}/contributions"
COUNT_RE = re.compile(r"([0-9][0-9,]*)\s+contribution", re.I)


def parse_count(cell, soup: BeautifulSoup) -> int | None:
    raw = cell.get("data-count")
    if raw and raw.isdigit():
        return int(raw)

    described_by = cell.get("aria-describedby")
    if described_by:
        tooltip = soup.find(id=described_by)
        if tooltip:
            text = tooltip.get_text(" ", strip=True)
            if "no contributions" in text.lower():
                return 0
            match = COUNT_RE.search(text)
            if match:
                return int(match.group(1).replace(",", ""))

    label = cell.get("aria-label") or ""
    if "no contributions" in label.lower():
        return 0
    match = COUNT_RE.search(label)
    if match:
        return int(match.group(1).replace(",", ""))

    return None


def streaks(days: list[dict]) -> tuple[int, int]:
    if not days:
        return 0, 0

    longest = current_run = 0
    for item in days:
        if item["count"] > 0:
            current_run += 1
            longest = max(longest, current_run)
        else:
            current_run = 0

    current = 0
    for item in reversed(days):
        if item["count"] > 0:
            current += 1
        else:
            break
    return current, longest


def main() -> None:
    response = requests.get(
        URL,
        headers={
            "User-Agent": "MORTAKI0-profile-art/1.0",
            "Accept": "text/html,application/xhtml+xml",
        },
        timeout=30,
    )
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")

    parsed: dict[str, dict] = {}
    unresolved_nonzero: list[str] = []

    for cell in soup.select("[data-date][data-level]"):
        day = cell.get("data-date")
        level_raw = cell.get("data-level")
        if not day or not level_raw:
            continue
        try:
            date.fromisoformat(day)
            level = max(0, min(5, int(level_raw)))
        except (TypeError, ValueError):
            continue

        count = parse_count(cell, soup)
        if count is None:
            if level == 0:
                count = 0
            else:
                unresolved_nonzero.append(day)
                continue

        parsed[day] = {"date": day, "count": count, "level": level}

    if len(parsed) < 300:
        raise RuntimeError(
            f"Contribution markup changed or fetch was incomplete: only {len(parsed)} days parsed."
        )
    if unresolved_nonzero:
        preview = ", ".join(unresolved_nonzero[:5])
        raise RuntimeError(
            "Could not resolve exact contribution counts for non-zero days: " + preview
        )

    days = [parsed[key] for key in sorted(parsed)]
    # Keep the 53-week GitHub-style window at most.
    days = days[-371:]

    current_streak, longest_streak = streaks(days)
    total = sum(item["count"] for item in days)
    best = max(days, key=lambda item: item["count"], default={"date": None, "count": 0})

    monthly: dict[str, int] = defaultdict(int)
    for item in days:
        monthly[item["date"][:7]] += item["count"]

    payload = {
        "username": USERNAME,
        "source": URL,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "days": days,
        "stats": {
            "total": total,
            "current_streak": current_streak,
            "longest_streak": longest_streak,
            "best_day": best,
            "monthly_totals": dict(sorted(monthly.items())),
        },
    }

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUTPUT} with {len(days)} days and {total} contributions")


if __name__ == "__main__":
    main()
