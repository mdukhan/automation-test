# scripts/daily_report.py
import os
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests

REPO_OWNER = os.getenv("GITHUB_REPOSITORY_OWNER", "")
REPO_FULL = os.getenv("GITHUB_REPOSITORY", "")  # e.g., owner/name
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

# ----- Blocks -----

def top_languages(limit=6):
    url = f"https://api.github.com/users/{REPO_OWNER}/repos"
    repos = fetch_json(url, params={"per_page": 100})
    agg = {}
    for r in repos:
        if r.get("fork"):
            continue
        try:
            langs = fetch_json(r["languages_url"])
        except Exception:
            langs = {}
        for lang, bytes_ in langs.items():
            agg[lang] = agg.get(lang, 0) + bytes_
    if not agg:
        return "### 🧪 Languages\n_No data._"
    top = sorted(agg.items(), key=lambda kv: kv[1], reverse=True)[:limit]
    total = sum(v for _, v in top) or 1
    lines = [f"- **{lang}**: {round(v * 100 / total, 1)}%" for lang, v in top]
    return "### 🧪 Languages (approx)\n" + "\n".join(lines)

def list_public_repos(limit=5):
    url = f"https://api.github.com/users/{REPO_OWNER}/repos"
    repos = fetch_json(url, params={"sort": "updated", "per_page": 100})
    repos = [r for r in repos if not r.get("fork")]
    repos = sorted(repos, key=lambda r: r["pushed_at"], reverse=True)[:limit]
    if not repos:
        return "### 🔧 Recent Repos\n_No public repos found._"
    lines = []
    for r in repos:
        name = r["name"]
        desc = r["description"] or ""
        stars = r["stargazers_count"]
        pushed = r["pushed_at"].replace("T", " ").replace("Z", " UTC")
        lines.append(f"- [{name}](https://github.com/{REPO_OWNER}/{name}) — ★{stars} — _last push {pushed}_  \n  {desc}")
    return "### 🔧 Recent Repos\n" + "\n".join(lines)

def recent_activity(limit=5, days=7):
    url = f"https://api.github.com/users/{REPO_OWNER}/events/public"
    events = fetch_json(url, params={"per_page": 100})
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    items = []
    for e in events:
        created = datetime.fromisoformat(e["created_at"].replace("Z", "+00:00"))
        if created < cutoff:
            continue
        t = e["type"].replace("Event", "")
        repo = e["repo"]["name"]
        items.append(f"- {created.strftime('%Y-%m-%d %H:%M UTC')} — **{t}** in `{repo}`")
        if len(items) >= limit:
            break
    return "### ⚡ Recent Activity (7d)\n" + ("\n".join(items) if items else "_No public activity in the last week._")

def rss_digest(feed_url="https://news.ycombinator.com/rss", limit=5):
    try:
        xml = requests.get(feed_url, timeout=20).text
        titles = re.findall(r"<title>([^<]+)</title>", xml)[2:limit+2]
        links = re.findall(r"<link>(https?://[^<]+)</link>", xml)[1:limit+1]
        items = [f"- [{t}]({l})" for t, l in zip(titles, links)]
        return "### 📰 Today’s Headlines (HN)\n" + ("\n".join(items) if items else "_No items._")
    except Exception:
        return "### 📰 Today’s Headlines\n_Failed to fetch feed._"

def help_wanted(limit=5):
    try:
        url = "https://api.github.com/search/issues"
        q = f"label:%22help wanted%22 user:{REPO_OWNER} state:open type:issue"
        data = fetch_json(url, params={"q": q, "sort": "updated", "order": "desc", "per_page": 10})
        items = []
        for it in data.get("items", [])[:limit]:
            title = it["title"]
            html = it["html_url"]
            repo = it["repository_url"].split("/")[-1]
            items.append(f"- [{title}]({html}) in `{repo}`")
        return "### 🆘 Help Wanted\n" + ("\n".join(items) if items else "_No labeled issues._")
    except Exception:
        return "### 🆘 Help Wanted\n_Failed to fetch._"

def markets_snapshot():
    import requests as rq
    fx_pairs = os.getenv("FX_PAIRS", "EURUSD;EURGBP").split(";")
    lines = []

    # FX rates
    try:
        for p in fx_pairs:
            p = p.strip().upper()
            if len(p) == 6:
                base, quote = p[:3], p[3:]
                r = rq.get(f"https://api.exchangerate.host/latest?base={base}&symbols={quote}", timeout=15).json()
                rate = r.get("rates", {}).get(quote)
                if rate:
                    lines.append(f"- **{base}/{quote}**: {round(rate, 4)}")
    except Exception:
        lines.append("- FX: _failed to fetch_")

    # BTC/EUR
    try:
        c = rq.get("https://api.coindesk.com/v1/bpi/currentprice/EUR.json", timeout=15).json()
        eur = c.get("bpi", {}).get("EUR", {}).get("rate_float")
        if eur:
            lines.append(f"- **BTC/EUR**: {int(eur):,}".replace(",", " "))
    except Exception:
        lines.append("- Crypto: _failed to fetch_")

    return "### 💹 Markets\n" + ("\n".join(lines) if lines else "_No data._")

def stackoverflow_digest():
    tags = os.getenv("SO_TAGS", "python;java").replace(";", "+")
    url = f"https://stackoverflow.com/feeds/tag?tagnames={tags}&sort=newest"
    try:
        xml = requests.get(url, timeout=20).text
        titles = re.findall(r"<title>([^<]+)</title>", xml)[2:7]
        links = re.findall(r"<link rel=\"alternate\" type=\"text/html\" href=\"([^\"]+)\"", xml)[:5]
        items = [f"- [{t}]({l})" for t, l in zip(titles, links)]
        return "### 🧩 Stack Overflow (newest)\n" + ("\n".join(items) if items else "_No items._")
    except Exception:
        return "### 🧩 Stack Overflow\n_Failed to fetch._"

def weather_block():
    lat = os.getenv("WEATHER_LAT", "53.5511")  # Hamburg
    lon = os.getenv("WEATHER_LON", "9.9937")
    try:
        url = "https://api.open-meteo.com/v1/forecast"
        params = {
            "latitude": lat,
            "longitude": lon,
            "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum",
            "current_weather": "true",
            "timezone": "auto",
        }
        data = requests.get(url, params=params, timeout=20).json()
        cur = data.get("current_weather", {})
        daily = data.get("daily", {})
        if not cur:
            return "### 🌤️ Weather\n_Failed to fetch._"
        line_now = f"Now: {cur.get('temperature','?')}°C, wind {cur.get('windspeed','?')} km/h"
        tmax = daily.get("temperature_2m_max", [None])[0]
        tmin = daily.get("temperature_2m_min", [None])[0]
        prcp = daily.get("precipitation_sum", [None])[0]
        line_today = f"Today: {tmin}–{tmax}°C, precip {prcp} mm"
        return "### 🌤️ Weather (local)\n" + f"- {line_now}\n- {line_today}"
    except Exception:
        return "### 🌤️ Weather\n_Failed to fetch._"

def til_prompt():
    return (
        "### 🧠 TIL (fill me in)\n"
        "> Add one thing you learned today. Replace this line with a short note and commit.\n"
    )

# ----- Assemble & write -----

def assemble():
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    parts = [
        f"_Last update: **{now}**_\n",
        top_languages(),
        list_public_repos(),
        recent_activity(),
        help_wanted(),
        markets_snapshot(),
        stackoverflow_digest(),
        weather_block(),
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
