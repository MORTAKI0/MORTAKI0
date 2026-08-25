from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
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
