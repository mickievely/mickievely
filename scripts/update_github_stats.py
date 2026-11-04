"""프로필 통계에 비공개 저장소 커밋과 언어를 포함한다."""

import json
import os
import re
import sys
import urllib.request
import zlib
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATS = ROOT / "github-stats.svg"
LANGS = ROOT / "github-langs.svg"
README = ROOT / "README.md"
CARD = (
    "https://github-readme-stats-one-bice.vercel.app/api"
    "?username=mickievely&show_icons=true&theme=radical&hide_border=true&include_all_commits=true"
)
RAW = "https://raw.githubusercontent.com/mickievely/mickievely/main/github-stats.svg"
LANGS_RAW = "https://raw.githubusercontent.com/mickievely/mickievely/main/github-langs.svg"


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


def language_bytes(token: str) -> list[tuple[str, int, str]]:
    data = gh_graphql(
        token,
        """
        {
          user(login: "mickievely") {
            repositories(first: 100, ownerAffiliations: OWNER) {
              nodes {
                languages(first: 30, orderBy: {field: SIZE, direction: DESC}) {
                  edges { size node { name color } }
                }
              }
            }
          }
        }
        """,
    )
    totals: dict[str, list] = {}
    for repo in data["user"]["repositories"]["nodes"]:
        for edge in repo["languages"]["edges"]:
            name = edge["node"]["name"]
            size = int(edge["size"])
            color = edge["node"]["color"] or "#8b949e"
            prev = totals.get(name)
            if prev:
                prev[0] += size
            else:
                totals[name] = [size, color]
    ranked = sorted(totals.items(), key=lambda item: item[1][0], reverse=True)
    return [(name, size, color) for name, (size, color) in ranked if size > 0]


def visible_languages(rows: list[tuple[str, int, str]]) -> list[tuple[str, float, str]]:
    """전체 저장소 바이트 합 기준. 잘린 나머지는 그 외."""
    if not rows:
        return []
    grand = sum(size for _, size, _ in rows) or 1
    named: list[tuple[str, float, str]] = []
    other = 0.0
    for name, size, color in rows:
        pct = size / grand * 100
        if pct >= 0.05 and len(named) < 12:
            named.append((name, pct, color))
        else:
            other += pct
    if other >= 0.05:
        named.append(("그 외", other, "#8b949e"))
    return named


def langs_signature(items: list[tuple[str, float, str]]) -> str:
    return "|".join(f"{name} {pct:.2f}%" for name, pct, _ in items)


def current_langs_signature() -> str | None:
    if not LANGS.exists():
        return None
    names = re.findall(r'data-testid="lang-name">\s*([^<]+?)\s*<', LANGS.read_text(encoding="utf-8"))
    return "|".join(name.strip() for name in names)


def render_langs(items: list[tuple[str, float, str]]) -> None:
    cols = 2 if len(items) > 1 else 1
    rows = (len(items) + cols - 1) // cols
    labels = [f"{name} {pct:.2f}%" for name, pct, _ in items]
    col_w = max(160, int(max(len(label) for label in labels) * 6.7) + 28)
    bar_w = col_w * cols - 10
    width = 25 + col_w * cols + 15
    height = 55 + 25 + rows * 25 + 20
    parts = [
        f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" fill="none" xmlns="http://www.w3.org/2000/svg" role="img">',
        "<title>Most Used Languages</title>",
        f'<desc>{" , ".join(labels)}</desc>',
        """<style>
          .header { font: 600 18px 'Segoe UI', Ubuntu, Sans-Serif; fill: #fe428e; }
          .lang-name { font: 400 11px 'Segoe UI', Ubuntu, Sans-Serif; fill: #a9fef7; }
          @keyframes slideInAnimation { from { width: 0; } to { width: calc(100% - 100px); } }
          @keyframes growWidthAnimation { from { width: 0; } to { width: 100%; } }
          @keyframes fadeInAnimation { from { opacity: 0; } to { opacity: 1; } }
          .stagger { opacity: 0; animation: fadeInAnimation 0.3s ease-in-out forwards; }
          #rect-mask rect { animation: slideInAnimation 1s ease-in-out forwards; }
          .lang-progress { animation: growWidthAnimation 0.6s ease-in-out forwards; }
        </style>""",
        f'<rect x="0.5" y="0.5" rx="4.5" height="99%" width="{width - 1}" fill="#141321" stroke="#e4e2e2" stroke-opacity="0"/>',
        '<g transform="translate(25, 35)"><text x="0" y="0" class="header">Most Used Languages</text></g>',
        '<g transform="translate(0, 55)"><svg x="25">',
        f'<mask id="rect-mask"><rect x="0" y="0" width="{bar_w}" height="8" fill="white" rx="5"/></mask>',
    ]
    cursor = 0.0
    for index, (name, pct, color) in enumerate(items):
        span = max(bar_w - cursor, 0) if index == len(items) - 1 else bar_w * pct / 100
        parts.append(
            f'<rect mask="url(#rect-mask)" class="lang-progress" x="{cursor:.2f}" y="0" width="{span:.2f}" height="8" fill="{color}"/>'
        )
        cursor += span
    for col in range(cols):
        chunk = items[col * rows : (col + 1) * rows]
        parts.append(f'<g transform="translate({col * col_w}, 25)">')
        for row, (name, pct, color) in enumerate(chunk):
            delay = 450 + row * 150
            label = f"{name} {pct:.2f}%".replace("&", "&amp;").replace("<", "&lt;")
            parts.append(
                f'<g transform="translate(0, {row * 25})"><g class="stagger" style="animation-delay: {delay}ms">'
                f'<circle cx="5" cy="6" r="5" fill="{color}"/>'
                f'<text data-testid="lang-name" x="15" y="10" class="lang-name">{label}</text>'
                "</g></g>"
            )
        parts.append("</g>")
    parts.append("</svg></g></svg>\n")
    LANGS.write_text("".join(parts), encoding="utf-8")
    readme = README.read_text(encoding="utf-8")
    src = f"{LANGS_RAW}?v={zlib.crc32(langs_signature(items).encode()) & 0xFFFFFFFF:x}"
    readme, img_n = re.subn(
        r'(<img height=")\d+(" src=")https://(?:github-readme-stats-one-bice\.vercel\.app/api/top-langs/[^"]*|raw\.githubusercontent\.com/mickievely/mickievely/main/github-langs\.svg[^"]*)(")',
        rf"\g<1>{height}\g<2>{src}\g<3>",
        readme,
        count=1,
    )
    if img_n != 1:
        raise SystemExit("language image missing from README")
    README.write_text(readme, encoding="utf-8")


def main() -> None:
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not token:
        raise SystemExit("GH_TOKEN missing")
    total = commit_total(token)
    if current_shown() == total:
        print(f"commits unchanged {total}")
    else:
        render(total)
        print(f"commits updated {total}")
    items = visible_languages(language_bytes(token))
    if not items:
        raise SystemExit("no languages")
    signature = langs_signature(items)
    if current_langs_signature() == signature:
        print(f"langs unchanged {signature}")
        return
    render_langs(items)
    print(f"langs updated {signature}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(exc, file=sys.stderr)
        raise
