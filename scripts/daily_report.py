# scripts/daily_report.py
import json
import os
import re
import subprocess
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests

REPO_OWNER = os.getenv("GITHUB_REPOSITORY_OWNER", "")  # set automatically in Actions
REPO_FULL = os.getenv("GITHUB_REPOSITORY", "")        # e.g., owner/name
GH_TOKEN = os.getenv("GH_TOKEN") or os.getenv("GITHUB_TOKEN")

README = Path("README.md")
START = "<!-- DAILY-SECTION:START -->"
END = "<!-- DAILY-SECTION:END -->"

def gh_headers():
    h = {"Accept": "application/vnd.github+json"}
    if GH_TOKEN:
        h["Authorization"] = f"Bearer {GH_TOKEN}"
    return h

def fetch_json(url, params=None):
    r = requests.get(url, headers=gh_headers(), params=params, timeout=30)
    r.raise_for_status()
    return r.json()

def list_public_repos(limit=5):
    url = f"https://api.github.com/users/{REPO_OWNER}/repos"
    repos = fetch_json(url, params={"sort": "updated", "per_page": 100})
    # exclude forks for signal
    repos = [r for r in repos if not r.get("fork")]
    repos = sorted(repos, key=lambda r: r["pushed_at"], reverse=True)[:limit]
    lines = []
    for r in repos:
        name = r["name"]
        desc = r["description"] or ""
        stars = r["stargazers_count"]
        pushed = r["pushed_at"].replace("T", " ").replace("Z", " UTC")
        lines.append(f"- [{name}](https://github.com/{REPO_OWNER}/{name}) — ★{stars} — _last push {pushed}_  \n  {desc}")
    return "### 🔧 Recent Repos\n" + ("\n".join(lines) if lines else "_No public repos found._")

def top_languages(limit=6):
    # approximate by sampling your repos' language breakdowns
    url = f"https://api.github.com/users/{REPO_OWNER}/repos"
    repos = fetch_json(url, params={"per_page": 100})
    agg = {}
    for r in repos:
        if r.get("fork"):
            continue
        langs_url = r["languages_url"]
        try:
            langs = fetch_json(langs_url)
        except Exception:
            langs = {}
        for lang, bytes_ in langs.items():
            agg[lang] = agg.get(lang, 0) + bytes_
    if not agg:
        return "### 🧪 Languages\n_No data._"
    top = sorted(agg.items(), key=lambda kv: kv[1], reverse=True)[:limit]
    total = sum(v for _, v in top)
    bars = []
    for lang, bytes_ in top:
        pct = 0 if total == 0 else round(bytes_ * 100 / total, 1)
        bars.append(f"- **{lang}**: {pct}%")
    return "### 🧪 Languages (approx)\n" + "\n".join(bars)

def recent_activity(limit=5, days=7):
    # events API—public activity only
    url = f"https://api.github.com/users/{REPO_OWNER}/events/public"
    events = fetch_json(url, params={"per_page": 100})
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    items, count = [], 0
    for e in events:
        created = datetime.fromisoformat(e["created_at"].replace("Z", "+00:00"))
        if created < cutoff:
            continue
        t = e["type"]
        repo = e["repo"]["name"]
        if t in ("PushEvent", "PullRequestEvent", "CreateEvent", "ReleaseEvent", "IssuesEvent", "WatchEvent"):
            summary = t.replace("Event", "")
            items.append(f"- {created.strftime('%Y-%m-%d %H:%M UTC')} — **{summary}** in `{repo}`")
            count += 1
            if count >= limit:
                break
    return "### ⚡ Recent Activity (7d)\n" + ("\n".join(items) if items else "_No public activity in the last week._")

def stars_last_30d(limit=5):
    # naive approach: search repos owned by you, sort by stars desc; not exact "last 30d" but good signal
    url = "https://api.github.com/search/repositories"
    q = f"user:{REPO_OWNER} fork:false"
    data = fetch_json(url, params={"q": q, "sort": "stars", "order": "desc", "per_page": 10})
    items = []
    for r in data.get("items", [])[:limit]:
        items.append(f"- [{r['name']}](https://github.com/{r['full_name']}) — ★{r['stargazers_count']}")
    return "### ⭐ Top Starred Repos\n" + ("\n".join(items) if items else "_No repos._")

def rss_digest(feed_url="https://news.ycombinator.com/rss", limit=5):
    # lightweight RSS read without extra deps: use a simple regex fallback
    try:
        xml = requests.get(feed_url, timeout=20).text
        titles = re.findall(r"<title>([^<]+)</title>", xml)[2:limit+2]  # skip feed title
        links = re.findall(r"<link>(https?://[^<]+)</link>", xml)[1:limit+1]
        items = [f"- [{t}]({l})" for t, l in zip(titles, links)]
        return "### 📰 Today’s Headlines (HN)\n" + ("\n".join(items) if items else "_No items._")
    except Exception:
        return "### 📰 Today’s Headlines\n_Failed to fetch feed._"

def til_prompt():
    return (
        "### 🧠 TIL (fill me in)\n"
        "> Add one thing you learned today. Replace this line with a short note and commit.\n"
    )

def assemble():
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    parts = [
        f"_Last update: **{now}**_\n",
        top_languages(),
        stars_last_30d(),
        list_public_repos(),
        recent_activity(),
        rss_digest(),
        til_prompt(),
    ]
    return "\n\n".join(parts)

def ensure_readme_section(content: str):
    if not README.exists():
        README.write_text(f"# {REPO_FULL}\n\n{START}\n{content}\n{END}\n", encoding="utf-8")
        return True

    txt = README.read_text(encoding="utf-8")
    if START in txt and END in txt:
        new = re.sub(
            rf"{re.escape(START)}.*?{re.escape(END)}",
            f"{START}\n{content}\n{END}",
            txt,
            flags=re.DOTALL,
        )
    else:
        # append section at end
        new = txt.rstrip() + f"\n\n{START}\n{content}\n{END}\n"

    if new != txt:
        README.write_text(new, encoding="utf-8")
        return True
    return False

def main():
    md = assemble()
    changed = ensure_readme_section(md)
    print("Updated README section." if changed else "No changes needed.")

if __name__ == "__main__":
    main()
