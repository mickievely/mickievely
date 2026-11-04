"""프로필 통계 카드의 Total Commits에 비공개 커밋을 더한다."""

import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATS = ROOT / "github-stats.svg"
README = ROOT / "README.md"
CARD = (
    "https://github-readme-stats-one-bice.vercel.app/api"
    "?username=mickievely&show_icons=true&theme=radical&hide_border=true&include_all_commits=true"
)
RAW = "https://raw.githubusercontent.com/mickievely/mickievely/main/github-stats.svg"


def gh_graphql(token: str, query: str) -> dict:
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query}).encode(),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "mickievely-stats",
        },
    )
    with urllib.request.urlopen(req, timeout=60) as res:
        body = json.loads(res.read().decode())
    if body.get("errors"):
        raise SystemExit(body["errors"][0].get("message") or "graphql failed")
    return body["data"]


def commit_total(token: str) -> int:
    created = gh_graphql(token, '{ user(login: "mickievely") { createdAt } }')
    start = datetime.fromisoformat(
        created["user"]["createdAt"].replace("Z", "+00:00")
    ).year
    end = datetime.now(timezone.utc).year
    parts = []
    for year in range(start, end + 1):
        parts.append(
            f'y{year}: contributionsCollection(from: "{year}-01-01T00:00:00Z", '
            f'to: "{year + 1}-01-01T00:00:00Z") '
            "{ totalCommitContributions restrictedContributionsCount }"
        )
    data = gh_graphql(token, '{ user(login: "mickievely") { ' + " ".join(parts) + " } }")
    total = 0
    for year in range(start, end + 1):
        row = data["user"][f"y{year}"]
        total += int(row["totalCommitContributions"]) + int(row["restrictedContributionsCount"])
    return total


def current_shown() -> int | None:
    if not STATS.exists():
        return None
    match = re.search(r'data-testid="commits"[^>]*>\s*(\d+)', STATS.read_text(encoding="utf-8"))
    return int(match.group(1)) if match else None


def render(total: int) -> None:
    req = urllib.request.Request(CARD, headers={"User-Agent": "mickievely-stats"})
    with urllib.request.urlopen(req, timeout=60) as res:
        svg = res.read().decode()
    svg, commits_n = re.subn(
        r'(data-testid="commits"[^>]*>)\s*\d+',
        rf"\g<1>{total}",
        svg,
        count=1,
    )
    svg, desc_n = re.subn(
        r"Total Commits\s*:\s*\d+",
        f"Total Commits  : {total}",
        svg,
        count=1,
    )
    if commits_n != 1 or desc_n != 1:
        raise SystemExit("stats card layout changed")
    STATS.write_text(svg, encoding="utf-8")
    readme = README.read_text(encoding="utf-8")
    src = f"{RAW}?v={total}"
    readme, img_n = re.subn(
        r'src="https://(?:github-readme-stats-one-bice\.vercel\.app/api\?username=mickievely[^"]*|raw\.githubusercontent\.com/mickievely/mickievely/main/github-stats\.svg[^"]*)"',
        f'src="{src}"',
        readme,
        count=1,
    )
    if img_n != 1:
        raise SystemExit("stats image missing from README")
    README.write_text(readme, encoding="utf-8")


def main() -> None:
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not token:
        raise SystemExit("GH_TOKEN missing")
    total = commit_total(token)
    if current_shown() == total:
        print(f"unchanged {total}")
        return
    render(total)
    print(f"updated {total}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(exc, file=sys.stderr)
        raise
