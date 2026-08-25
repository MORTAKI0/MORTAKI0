from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

USERNAME = "MORTAKI0"
ORG = "egawilldoit"
PROFILE_REPO = f"{USERNAME}/{USERNAME}"
README_PATH = Path(__file__).resolve().parents[1] / "README.md"
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


def activity_stage(repo: dict[str, Any], now: datetime) -> tuple[str, int | None]:
    if repo.get("archived"):
        return "📦 Archived", None

    age = days_since(repo.get("pushed_at") or repo.get("updated_at"), now)
    if age is None:
        return "⚪ Quiet", None
    if age <= 7:
        return "🔥 Shipping now", age
    if age <= 30:
        return "🟢 Active build", age
    if age <= 90:
        return "🟡 Recent", age
    return "⚪ Quiet", age


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


def build_stage_radar() -> str:
    repos = load_public_builds()
    now = datetime.now(timezone.utc)

    staged: list[tuple[dict[str, Any], str, int | None]] = []
    counts = Counter()
    active_languages = Counter()

    for repo in repos:
        stage, age = activity_stage(repo, now)
        staged.append((repo, stage, age))
        counts[stage] += 1
        if age is not None and age <= 90 and repo.get("language"):
            active_languages[str(repo["language"])] += 1

    staged.sort(
        key=lambda item: (
            item[2] is None,
            item[2] if item[2] is not None else 10**9,
            -(int(item[0].get("stargazers_count", 0))),
        )
    )

    active_90d = sum(1 for _, _, age in staged if age is not None and age <= 90)
    momentum = round((active_90d / len(staged)) * 100) if staged else 0
    blocks = min(10, max(0, round(momentum / 10)))
    bar = "█" * blocks + "░" * (10 - blocks)

    stage_summary = " · ".join(
        [
            f"🔥 **{counts['🔥 Shipping now']}** shipping",
            f"🟢 **{counts['🟢 Active build']}** active",
            f"🟡 **{counts['🟡 Recent']}** recent",
            f"⚪ **{counts['⚪ Quiet']}** quiet",
        ]
    )

    stack_summary = " · ".join(
        f"`{language}` ×{count}"
        for language, count in active_languages.most_common(5)
    ) or "_No active-language signal yet._"

    lines = [
        f"**Momentum:** `{bar}` **{momentum}%** of public original repos pushed in the last 90 days",
        "",
        stage_summary,
        "",
        f"**Active stack signal:** {stack_summary}",
        "",
        "| Project | Owner | Stage | Last push | Lang | ⭐ | 🍴 | Open |",
        "| --- | --- | --- | --- | --- | ---: | ---: | ---: |",
    ]

    for repo, stage, age in staged[:8]:
        full_name = repo["full_name"]
        owner = repo.get("owner", {}).get("login", "")
        name = repo.get("name", full_name)
        url = repo.get("html_url") or f"https://github.com/{full_name}"
        language = repo.get("language") or "—"
        stars = int(repo.get("stargazers_count", 0))
        forks = int(repo.get("forks_count", 0))
        open_items = int(repo.get("open_issues_count", 0))
        lines.append(
            f"| [`{name}`]({url}) | `{owner}` | **{stage}** | {age_label(age)} | "
            f"`{language}` | {stars} | {forks} | {open_items} |"
        )

    lines.extend(
        [
            "",
            "<sub>Stage is derived only from public GitHub push recency: "
            "🔥 ≤7d · 🟢 ≤30d · 🟡 ≤90d · ⚪ >90d. "
            "It is an activity signal, not a claim about product maturity or production readiness.</sub>",
        ]
    )
    return "\n".join(lines)


def build_ega_stats() -> str:
    repos = github_get(f"/orgs/{ORG}/repos?type=public&sort=updated&per_page=100")
    repos = [repo for repo in repos if not repo.get("archived")]

    stars = sum(int(repo.get("stargazers_count", 0)) for repo in repos)
    forks = sum(int(repo.get("forks_count", 0)) for repo in repos)

    cutoff = datetime.now(timezone.utc) - timedelta(days=90)
    active = sum(
        1
        for repo in repos
        if (pushed_at := parse_github_time(repo.get("pushed_at"))) and pushed_at >= cutoff
    )

    freshest = sorted(
        repos,
        key=lambda repo: repo.get("pushed_at") or repo.get("updated_at") or "",
        reverse=True,
    )[:3]

    recent_links = " · ".join(
        f"[`{repo['name']}`]({repo['html_url']})"
        for repo in freshest
    ) or "No public repositories yet."

    return "\n".join(
        [
            "| 🗂️ Public repos | ⭐ Stars | 🍴 Forks | 🔄 Active (90d) |",
            "| ---: | ---: | ---: | ---: |",
            f"| **{len(repos)}** | **{stars}** | **{forks}** | **{active}** |",
            "",
            f"**Freshest builds:** {recent_links}",
        ]
    )


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
        size = int(payload.get("size", 0))
        noun = "commit" if size == 1 else "commits"
        text = f"⚡ Pushed **{size} {noun}** to {repo_md}"
    elif event_type == "PullRequestEvent":
        pr = payload.get("pull_request") or {}
        url = pr.get("html_url") or repo_url
        number = pr.get("number") or payload.get("number")
        title = (pr.get("title") or "pull request").replace("|", "¦")
        verb = (action or "updated").capitalize()
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


def build_recent_activity() -> str:
    events = github_get(f"/users/{USERNAME}/events/public?per_page=50")
    lines: list[str] = []
    seen: set[str] = set()

    for event in events:
        line = event_line(event)
        if not line or line in seen:
            continue
        seen.add(line)
        lines.append(line)
        if len(lines) >= 6:
            break

    if not lines:
        return "_No recent public GitHub activity to show yet._"
    return "\n".join(lines)


def main() -> None:
    readme = README_PATH.read_text(encoding="utf-8")

    try:
        readme = replace_section(readme, EGA_START, EGA_END, build_ega_stats())
    except (urllib.error.URLError, urllib.error.HTTPError) as exc:
        print(f"warning: could not refresh EGA stats: {exc}")

    try:
        readme = replace_section(readme, STAGES_START, STAGES_END, build_stage_radar())
    except (urllib.error.URLError, urllib.error.HTTPError) as exc:
        print(f"warning: could not refresh build stages: {exc}")

    try:
        readme = replace_section(
            readme,
            ACTIVITY_START,
            ACTIVITY_END,
            build_recent_activity(),
        )
    except (urllib.error.URLError, urllib.error.HTTPError) as exc:
        print(f"warning: could not refresh recent activity: {exc}")

    README_PATH.write_text(readme.rstrip() + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
