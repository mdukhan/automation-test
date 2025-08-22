# scripts/heartbeat.py
from datetime import datetime, timezone
from pathlib import Path

HEARTBEAT = Path("HEARTBEAT.md")

now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S %Z")
content = [
    "# Daily Heartbeat\n",
    "This file is automatically updated once per day by a workflow.\n\n",
    f"Last update: **{now}**\n",
]

# Only rewrite if changed (keeps the repo clean)
old = HEARTBEAT.read_text(encoding="utf-8") if HEARTBEAT.exists() else ""
new = "".join(content)
if old != new:
    HEARTBEAT.write_text(new, encoding="utf-8")
    print("Heartbeat updated.")
else:
    print("No change; heartbeat already up to date.")
