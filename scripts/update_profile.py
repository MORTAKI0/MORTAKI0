from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
import urllib.parse
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from html import escape
from pathlib import Path
from typing import Any

USERNAME = "MORTAKI0"
ORG = "egawilldoit"
PROFILE_REPO = f"{USERNAME}/{USERNAME}"
ROOT = Path(__file__).resolve().parents[1]
README_PATH = ROOT / "README.md"
ASSET_PATH = ROOT / "assets" / "live-build-radar.svg"
API_ROOT = "https://api.github.com"

EGA_START = "<!-- EGA_STATS:START -->"
EGA_END = "<!-- EGA_STATS:END -->"
STAGES_START = "<!-- BUILD_STAGES:START -->"
STAGES_END = "<!-- BUILD_STAGES:END -->"
ACTIVITY_START = "<!-- RECENT_ACTIVITY:START -->"
ACTIVITY_END = "<!-- RECENT_ACTIVITY:END -->"


def github_get(path: str) -> Any:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": f"{USERNAME}-profile-updater",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"

    request = urllib.request.Request(f"{API_ROOT}{path}", headers=headers)
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def replace_section(text: str, start: str, end: str, body: str) -> str:
    pattern = re.compile(re.escape(start) + r".*?" + re.escape(end), re.DOTALL)
    replacement = f"{start}\n{body.strip()}\n{end}"
    if not pattern.search(text):
        raise RuntimeError(f"README section markers not found: {start} / {end}")
    return pattern.sub(lambda _: replacement, text, count=1)


def parse_github_time(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def days_since(value: str | None, now: datetime) -> int | None:
    pushed_at = parse_github_time(value)
    if not pushed_at:
        return None
    return max(0, (now - pushed_at).days)


def age_label(age: int | None) -> str:
    if age is None:
        return "unknown"
    if age == 0:
        return "today"
    if age == 1:
        return "1 day ago"
    return f"{age} days ago"


def load_public_builds() -> list[dict[str, Any]]:
    personal = github_get(
        f"/users/{USERNAME}/repos?type=owner&sort=pushed&direction=desc&per_page=100"
    )
    org = github_get(
        f"/orgs/{ORG}/repos?type=public&sort=pushed&direction=desc&per_page=100"
    )

    builds: dict[str, dict[str, Any]] = {}
    for repo in [*personal, *org]:
        full_name = repo.get("full_name")
        if (
            not full_name
            or full_name == PROFILE_REPO
            or repo.get("fork")
            or repo.get("archived")
        ):
            continue
        builds[full_name] = repo
    return list(builds.values())


def load_public_events(max_pages: int = 3) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for page in range(1, max_pages + 1):
        batch = github_get(
            f"/users/{USERNAME}/events/public?per_page=100&page={page}"
        )
        if not batch:
            break
        events.extend(batch)
        if len(batch) < 100:
            break
    return events


def build_event_index(
    events: list[dict[str, Any]], now: datetime
) -> tuple[dict[str, Counter], Counter]:
    per_repo: dict[str, Counter] = defaultdict(Counter)
    totals = Counter()
    seen_pr_30d: set[tuple[str, Any]] = set()
    seen_pr_7d: set[tuple[str, Any]] = set()

    cutoff_30 = now - timedelta(days=30)
    cutoff_7 = now - timedelta(days=7)

    for event in events:
        created = parse_github_time(event.get("created_at"))
        repo_name = event.get("repo", {}).get("name", "")
        if not created or not repo_name or repo_name == PROFILE_REPO:
            continue

        payload = event.get("payload") or {}
        event_type = event.get("type", "")
        in_30 = created >= cutoff_30
        in_7 = created >= cutoff_7

        if in_30:
            per_repo[repo_name]["events_30d"] += 1
            totals["events_30d"] += 1

        if event_type == "PushEvent":
            if in_30:
                per_repo[repo_name]["pushes_30d"] += 1
                totals["pushes_30d"] += 1
            if in_7:
                totals["pushes_7d"] += 1

        elif event_type == "PullRequestEvent":
            pr = payload.get("pull_request") or {}
            number = pr.get("number") or payload.get("number")
            key = (repo_name, number)
            if in_30 and key not in seen_pr_30d:
                seen_pr_30d.add(key)
                per_repo[repo_name]["pr_30d"] += 1
                totals["pr_30d"] += 1
            if in_7 and key not in seen_pr_7d:
                seen_pr_7d.add(key)
                totals["pr_7d"] += 1

        elif event_type == "IssuesEvent":
            if in_30:
                per_repo[repo_name]["issues_30d"] += 1
                totals["issues_30d"] += 1

        elif event_type == "CreateEvent":
            if in_30 and payload.get("ref_type") == "branch":
                per_repo[repo_name]["branches_30d"] += 1
                totals["branches_30d"] += 1

        elif event_type == "ReleaseEvent":
            if in_30:
                per_repo[repo_name]["releases_30d"] += 1
                totals["releases_30d"] += 1

    return per_repo, totals


def load_recent_commit_counts(
    repos: list[dict[str, Any]], now: datetime
) -> dict[str, int]:
    since = (now - timedelta(days=30)).isoformat().replace("+00:00", "Z")
    query = urllib.parse.urlencode({"since": since, "per_page": 100})
    counts: dict[str, int] = {}

    for repo in repos:
        full_name = repo.get("full_name")
        if not full_name:
            continue

        age = days_since(repo.get("pushed_at") or repo.get("updated_at"), now)
        if age is None or age > 90:
            counts[full_name] = 0
            continue

        total = 0
        for page in range(1, 11):
            page_query = f"{query}&page={page}"
            commits = github_get(f"/repos/{full_name}/commits?{page_query}")
            total += len(commits)
            if len(commits) < 100:
                break
        counts[full_name] = total

    return counts


def velocity_score(
    repo: dict[str, Any],
    repo_events: Counter,
    commit_count_30d: int,
    now: datetime,
) -> tuple[int, int | None]:
    age = days_since(repo.get("pushed_at") or repo.get("updated_at"), now)

    if age is None:
        recency = 0
    elif age <= 1:
        recency = 45
    elif age <= 7:
        recency = 40
    elif age <= 14:
        recency = 34
    elif age <= 30:
        recency = 26
    elif age <= 60:
        recency = 14
    elif age <= 90:
        recency = 7
    else:
        recency = 0

    event_points = min(30, int(repo_events.get("events_30d", 0)) * 5)
    commit_points = min(25, commit_count_30d * 3)

    return min(100, recency + event_points + commit_points), age


def score_stage(score: int) -> tuple[str, str, str]:
    if score >= 75:
        return "🚀 Hot", "HOT", "#f97316"
    if score >= 55:
        return "🔥 Shipping", "SHIPPING", "#ef4444"
    if score >= 35:
        return "🟢 Active", "ACTIVE", "#22c55e"
    if score >= 15:
        return "🟡 Cooling", "COOLING", "#eab308"
    return "⚪ Quiet", "QUIET", "#64748b"


def rank_builds(
    repos: list[dict[str, Any]],
    per_repo: dict[str, Counter],
    commit_counts: dict[str, int],
    now: datetime,
) -> list[dict[str, Any]]:
    ranked: list[dict[str, Any]] = []

    for repo in repos:
        full_name = repo["full_name"]
        commit_count = int(commit_counts.get(full_name, 0))
        score, age = velocity_score(repo, per_repo.get(full_name, Counter()), commit_count, now)
        stage, stage_short, stage_color = score_stage(score)
        metrics = per_repo.get(full_name, Counter())

        ranked.append(
            {
                "repo": repo,
                "score": score,
                "age": age,
                "stage": stage,
                "stage_short": stage_short,
                "stage_color": stage_color,
                "events_30d": int(metrics.get("events_30d", 0)),
                "commits_30d": commit_count,
                "pr_30d": int(metrics.get("pr_30d", 0)),
            }
        )

    ranked.sort(
        key=lambda item: (
            -item["score"],
            item["age"] is None,
            item["age"] if item["age"] is not None else 10**9,
            -int(item["repo"].get("stargazers_count", 0)),
        )
    )
    return ranked


def build_stage_radar(
    ranked: list[dict[str, Any]], totals: Counter
) -> str:
    if not ranked:
        return "_No public original repositories found._"

    counts = Counter(item["stage"] for item in ranked)
    active = [item for item in ranked if item["score"] >= 15]
    active_languages = Counter(
        str(item["repo"]["language"])
        for item in active
        if item["repo"].get("language")
    )

    top_for_index = ranked[: min(8, len(ranked))]
    motion_index = round(
        sum(item["score"] for item in top_for_index) / len(top_for_index)
    )

    blocks = min(10, max(0, round(motion_index / 10)))
    bar = "█" * blocks + "░" * (10 - blocks)

    stage_summary = " · ".join(
        [
            f"🚀 **{counts['🚀 Hot']}** hot",
            f"🔥 **{counts['🔥 Shipping']}** shipping",
            f"🟢 **{counts['🟢 Active']}** active",
            f"🟡 **{counts['🟡 Cooling']}** cooling",
            f"⚪ **{counts['⚪ Quiet']}** quiet",
        ]
    )

    stack_summary = " · ".join(
        f"`{language}` ×{count}"
        for language, count in active_languages.most_common(5)
    ) or "_No active-language signal yet._"

    lines = [
        f"**Motion index:** `{bar}` **{motion_index}/100** across the 8 hottest public builds",
        "",
        f"**30-day pulse:** **{totals['commits_30d']} commits** · "
        f"**{totals['pr_30d']} PRs touched** · **{totals['branches_30d']} branches** · "
        f"**{totals['releases_30d']} releases**",
        "",
        stage_summary,
        "",
        f"**Active stack signal:** {stack_summary}",
        "",
        "| Project | Stage | Score | 30d commits | 30d events | Last push | Lang |",
        "| --- | --- | ---: | ---: | ---: | --- | --- |",
    ]

    for item in ranked[:8]:
        repo = item["repo"]
        full_name = repo["full_name"]
        name = repo.get("name", full_name)
        url = repo.get("html_url") or f"https://github.com/{full_name}"
        language = repo.get("language") or "—"
        lines.append(
            f"| [`{name}`]({url}) | **{item['stage']}** | **{item['score']}** | "
            f"{item['commits_30d']} | {item['events_30d']} | {age_label(item['age'])} | "
            f"`{language}` |"
        )

    lines.extend(
        [
            "",
            "<sub>Motion score is derived from public GitHub signals: up to 45 points "
            "for push recency, 25 for commits in the last 30 days, and 30 for recent "
            "public events. It measures current engineering motion, not product maturity "
            "or production readiness.</sub>",
        ]
    )
    return "\n".join(lines)


def svg_text(value: Any) -> str:
    return escape(str(value), quote=True)


def render_velocity_svg(
    ranked: list[dict[str, Any]],
    totals: Counter,
    generated_at: datetime,
) -> str:
    width = 1200
    rows = ranked[:6]
    height = 196 + len(rows) * 64 + 54

    if ranked:
        top_for_index = ranked[: min(8, len(ranked))]
        motion_index = round(
            sum(item["score"] for item in top_for_index) / len(top_for_index)
        )
    else:
        motion_index = 0

    active_count = sum(1 for item in ranked if item["score"] >= 15)
    ega_active = sum(
        1
        for item in ranked
        if item["score"] >= 15
        and item["repo"].get("owner", {}).get("login", "").lower() == ORG.lower()
    )

    metric_cards = [
        ("MOTION", f"{motion_index}/100"),
        ("ACTIVE BUILDS", str(active_count)),
        ("30D COMMITS", str(totals["commits_30d"])),
        ("30D PRs", str(totals["pr_30d"])),
        ("EGA ACTIVE", str(ega_active)),
    ]

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">',
        '<title id="title">Live Build Velocity</title>',
        '<desc id="desc">Automatically generated project velocity dashboard from public GitHub activity.</desc>',
        "<defs>",
        '<linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">',
        '<stop offset="0%" stop-color="#0d1117"/>',
        '<stop offset="100%" stop-color="#111827"/>',
        "</linearGradient>",
        '<linearGradient id="bar" x1="0" y1="0" x2="1" y2="0">',
        '<stop offset="0%" stop-color="#2563eb"/>',
        '<stop offset="55%" stop-color="#7c3aed"/>',
        '<stop offset="100%" stop-color="#06b6d4"/>',
        "</linearGradient>",
        "<style>",
        "text{font-family:'Segoe UI',Ubuntu,Arial,sans-serif}",
        ".muted{fill:#8b949e}.main{fill:#f0f6fc}.label{fill:#93c5fd;font-weight:700}",
        ".row{animation:fade .7s ease both}@keyframes fade{from{opacity:.25}to{opacity:1}}",
        "</style>",
        "</defs>",
        f'<rect width="{width}" height="{height}" rx="24" fill="url(#bg)" stroke="#30363d"/>',
        '<circle cx="44" cy="43" r="6" fill="#22c55e">',
        '<animate attributeName="opacity" values="1;.35;1" dur="1.8s" repeatCount="indefinite"/>',
        "</circle>",
        '<text x="62" y="50" class="main" font-size="27" font-weight="800">LIVE BUILD VELOCITY</text>',
        '<text x="62" y="76" class="muted" font-size="14">MORTAKI0 + EGAWILLDOIT · generated from public GitHub signals</text>',
        f'<text x="1138" y="50" class="muted" font-size="13" text-anchor="end">{svg_text(generated_at.strftime("%Y-%m-%d %H:%M UTC"))}</text>',
    ]

    card_y = 96
    card_gap = 12
    card_w = (width - 64 - card_gap * 4) / 5
    for idx, (label, value) in enumerate(metric_cards):
        x = 32 + idx * (card_w + card_gap)
        parts.extend(
            [
                f'<rect x="{x:.1f}" y="{card_y}" width="{card_w:.1f}" height="70" rx="14" fill="#161b22" stroke="#30363d"/>',
                f'<text x="{x + 18:.1f}" y="{card_y + 26}" class="muted" font-size="11" font-weight="700">{svg_text(label)}</text>',
                f'<text x="{x + 18:.1f}" y="{card_y + 54}" class="main" font-size="23" font-weight="800">{svg_text(value)}</text>',
            ]
        )

    header_y = 195
    parts.extend(
        [
            f'<text x="42" y="{header_y}" class="muted" font-size="11" font-weight="700">PROJECT</text>',
            f'<text x="405" y="{header_y}" class="muted" font-size="11" font-weight="700">STAGE</text>',
            f'<text x="595" y="{header_y}" class="muted" font-size="11" font-weight="700">30D</text>',
            f'<text x="730" y="{header_y}" class="muted" font-size="11" font-weight="700">VELOCITY</text>',
            f'<text x="1138" y="{header_y}" class="muted" font-size="11" font-weight="700" text-anchor="end">SCORE</text>',
        ]
    )

    for idx, item in enumerate(rows):
        repo = item["repo"]
        y = 214 + idx * 64
        owner = repo.get("owner", {}).get("login", "")
        full_name = repo.get("full_name", "")
        name = repo.get("name", full_name)
        if len(name) > 31:
            name = name[:28] + "..."
        owner_label = "EGA" if owner.lower() == ORG.lower() else "ME"
        score = int(item["score"])
        fill_w = round(360 * score / 100)
        events = item["events_30d"]
        commits = item["commits_30d"]

        parts.extend(
            [
                f'<g class="row" style="animation-delay:{idx * 0.08:.2f}s">',
                f'<rect x="30" y="{y}" width="1140" height="52" rx="12" fill="#0f1720" stroke="#21262d"/>',
                f'<text x="48" y="{y + 22}" class="main" font-size="16" font-weight="700">{svg_text(name)}</text>',
                f'<text x="48" y="{y + 40}" class="muted" font-size="11">{svg_text(owner_label)} · {svg_text(age_label(item["age"]))}</text>',
                f'<circle cx="414" cy="{y + 26}" r="5" fill="{item["stage_color"]}"/>',
                f'<text x="429" y="{y + 31}" class="main" font-size="12" font-weight="700">{svg_text(item["stage_short"])}</text>',
                f'<text x="595" y="{y + 31}" class="muted" font-size="12">{commits}c · {events}e</text>',
                f'<rect x="730" y="{y + 19}" width="360" height="12" rx="6" fill="#21262d"/>',
                f'<rect x="730" y="{y + 19}" width="{fill_w}" height="12" rx="6" fill="url(#bar)">',
                f'<animate attributeName="opacity" values=".55;1" dur="{1.0 + idx * 0.1:.1f}s" fill="freeze"/>',
                "</rect>",
                f'<text x="1138" y="{y + 31}" class="main" font-size="14" font-weight="800" text-anchor="end">{score}</text>',
                "</g>",
            ]
        )

    footer_y = height - 22
    parts.extend(
        [
            f'<text x="32" y="{footer_y}" class="muted" font-size="11">score = recency (45) + 30d commits (25) + public activity events (30)</text>',
            f'<text x="1168" y="{footer_y}" class="muted" font-size="11" text-anchor="end">auto-refresh: every 6h</text>',
            "</svg>",
        ]
    )
    return "\n".join(parts) + "\n"


def build_ega_stats(ranked: list[dict[str, Any]]) -> str:
    ega = [
        item
        for item in ranked
        if item["repo"].get("owner", {}).get("login", "").lower() == ORG.lower()
    ]
    stars = sum(int(item["repo"].get("stargazers_count", 0)) for item in ega)
    forks = sum(int(item["repo"].get("forks_count", 0)) for item in ega)
    active = sum(1 for item in ega if item["score"] >= 15)

    freshest = ega[:3]
    recent_links = " · ".join(
        f"[`{item['repo']['name']}`]({item['repo']['html_url']})"
        for item in freshest
    ) or "No public repositories yet."

    avg_velocity = (
        round(sum(item["score"] for item in ega) / len(ega))
        if ega
        else 0
    )

    return "\n".join(
        [
            "| 🗂️ Public repos | ⭐ Stars | 🍴 Forks | ⚡ Moving | 📈 Avg velocity |",
            "| ---: | ---: | ---: | ---: | ---: |",
            f"| **{len(ega)}** | **{stars}** | **{forks}** | **{active}** | **{avg_velocity}/100** |",
            "",
            f"**Freshest builds:** {recent_links}",
        ]
    )


def event_identity(event: dict[str, Any]) -> tuple[Any, ...]:
    event_type = event.get("type", "")
    repo_name = event.get("repo", {}).get("name", "")
    payload = event.get("payload") or {}

    if event_type == "PullRequestEvent":
        pr = payload.get("pull_request") or {}
        return ("pr", repo_name, pr.get("number") or payload.get("number"))
    if event_type == "IssuesEvent":
        issue = payload.get("issue") or {}
        return ("issue", repo_name, issue.get("number"))
    if event_type == "PushEvent":
        return ("push", repo_name)
    return (event_type, repo_name, event.get("id"))


def event_line(event: dict[str, Any]) -> str | None:
    event_type = event.get("type", "")
    repo_name = event.get("repo", {}).get("name", "")
    if not repo_name or repo_name == PROFILE_REPO:
        return None

    repo_url = f"https://github.com/{repo_name}"
    repo_md = f"[`{repo_name}`]({repo_url})"
    payload = event.get("payload") or {}
    action = payload.get("action")
    created = parse_github_time(event.get("created_at"))
    when = created.strftime("%b %d, %Y") if created else ""

    if event_type == "PushEvent":
        size = max(0, int(payload.get("size", 0)))
        if size == 0:
            text = f"⚡ Updated {repo_md}"
        else:
            noun = "commit" if size == 1 else "commits"
            text = f"⚡ Pushed **{size} {noun}** to {repo_md}"

    elif event_type == "PullRequestEvent":
        pr = payload.get("pull_request") or {}
        number = pr.get("number") or payload.get("number")
        title = pr.get("title")
        url = pr.get("html_url")
        merged = bool(pr.get("merged"))

        if number and (not title or not url):
            try:
                detail = github_get(f"/repos/{repo_name}/pulls/{number}")
                title = title or detail.get("title")
                url = url or detail.get("html_url")
                merged = merged or bool(detail.get("merged_at"))
            except (urllib.error.URLError, urllib.error.HTTPError):
                pass

        title = (title or "pull request").replace("|", "¦")
        url = url or repo_url
        verb = "Merged" if merged else (action or "updated").capitalize()
        text = f"🔀 {verb} PR [**#{number} {title}**]({url}) in {repo_md}"

    elif event_type == "IssuesEvent":
        issue = payload.get("issue") or {}
        url = issue.get("html_url") or repo_url
        number = issue.get("number")
        title = (issue.get("title") or "issue").replace("|", "¦")
        verb = (action or "updated").capitalize()
        text = f"🎯 {verb} issue [**#{number} {title}**]({url}) in {repo_md}"

    elif event_type == "CreateEvent":
        ref_type = payload.get("ref_type") or "repository"
        ref = payload.get("ref")
        target = f" `{ref}`" if ref else ""
        text = f"🌱 Created {ref_type}{target} in {repo_md}"

    elif event_type == "ReleaseEvent":
        release = payload.get("release") or {}
        url = release.get("html_url") or repo_url
        tag = release.get("tag_name") or release.get("name") or "release"
        verb = (action or "published").capitalize()
        text = f"🚀 {verb} release [**{tag}**]({url}) in {repo_md}"

    elif event_type == "WatchEvent":
        text = f"⭐ Starred {repo_md}"

    elif event_type == "ForkEvent":
        forkee = payload.get("forkee") or {}
        target = forkee.get("full_name")
        target_url = forkee.get("html_url")
        if target and target_url:
            text = f"🍴 Forked {repo_md} to [`{target}`]({target_url})"
        else:
            text = f"🍴 Forked {repo_md}"

    else:
        return None

    return f"- {text}" + (f" — _{when}_" if when else "")


def build_recent_activity(events: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    seen: set[tuple[Any, ...]] = set()

    for event in events:
        identity = event_identity(event)
        if identity in seen:
            continue

        line = event_line(event)
        if not line:
            continue

        seen.add(identity)
        lines.append(line)
        if len(lines) >= 6:
            break

    if not lines:
        return "_No recent public GitHub activity to show yet._"
    return "\n".join(lines)


def main() -> None:
    readme = README_PATH.read_text(encoding="utf-8")
    now = datetime.now(timezone.utc)

    try:
        repos = load_public_builds()
        events = load_public_events()
        per_repo, totals = build_event_index(events, now)
        commit_counts = load_recent_commit_counts(repos, now)
        totals["commits_30d"] = sum(commit_counts.values())
        ranked = rank_builds(repos, per_repo, commit_counts, now)
    except (urllib.error.URLError, urllib.error.HTTPError) as exc:
        raise RuntimeError(f"could not load public GitHub signals: {exc}") from exc

    try:
        readme = replace_section(readme, EGA_START, EGA_END, build_ega_stats(ranked))
    except RuntimeError as exc:
        print(f"warning: could not refresh EGA stats: {exc}")

    try:
        readme = replace_section(
            readme,
            STAGES_START,
            STAGES_END,
            build_stage_radar(ranked, totals),
        )
    except RuntimeError as exc:
        print(f"warning: could not refresh build stages: {exc}")

    try:
        readme = replace_section(
            readme,
            ACTIVITY_START,
            ACTIVITY_END,
            build_recent_activity(events),
        )
    except RuntimeError as exc:
        print(f"warning: could not refresh recent activity: {exc}")

    ASSET_PATH.parent.mkdir(parents=True, exist_ok=True)
    ASSET_PATH.write_text(render_velocity_svg(ranked, totals, now), encoding="utf-8")
    README_PATH.write_text(readme.rstrip() + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
