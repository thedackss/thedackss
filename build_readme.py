#!/usr/bin/env python3
"""Rebuild the profile card SVGs (card-dark.svg / card-light.svg).

Neofetch-style layout with dot-leader lines: label left, value right-aligned,
dots filling the gap (recomputed per run since values change length).
Runs daily in GitHub Actions with the default GITHUB_TOKEN.
"""
import datetime
import json
import os
import string
import time
import urllib.request
from xml.sax.saxutils import escape

TOKEN = os.environ["GITHUB_TOKEN"]
USER = os.environ.get("USER_NAME", "thedackss")
API = "https://api.github.com"

WIDTH = 66        # line width in characters
COL_X = 300       # x of the stats column
Y0, DY = 42, 21   # first baseline, line height

THEMES = {
    "card-dark.svg": {
        "bg": "#0d1117", "border": "#30363d", "fg": "#c9d1d9",
        "accent": "#58a6ff", "label": "#ffa657", "muted": "#8b949e",
        "plus": "#3fb950", "minus": "#f85149",
    },
    "card-light.svg": {
        "bg": "#ffffff", "border": "#d0d7de", "fg": "#24292f",
        "accent": "#0969da", "label": "#953800", "muted": "#6e7781",
        "plus": "#1a7f37", "minus": "#cf222e",
    },
}


def call(url, payload=None):
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {TOKEN}",
        "Accept": "application/vnd.github+json",
        "User-Agent": USER,
    })
    if payload is not None:
        req.data = json.dumps(payload).encode()
        req.method = "POST"
    with urllib.request.urlopen(req) as resp:
        if resp.status == 202:  # stats still being computed
            return None
        return json.loads(resp.read() or "{}")


def graphql(query):
    return call(f"{API}/graphql", {"query": query})["data"]


def uptime(created_at):
    created = datetime.datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    now = datetime.datetime.now(datetime.timezone.utc)
    years = now.year - created.year
    anniversary = created.replace(year=created.year + years)
    if anniversary > now:
        years -= 1
        anniversary = created.replace(year=created.year + years)
    return f"{years} years, {(now - anniversary).days} days"


def total_commits(created_at):
    total = 0
    for year in range(int(created_at[:4]), datetime.date.today().year + 1):
        data = graphql(f'''query {{ user(login: "{USER}") {{
            contributionsCollection(
                from: "{year}-01-01T00:00:00Z", to: "{year}-12-31T23:59:59Z"
            ) {{ totalCommitContributions restrictedContributionsCount }} }} }}''')
        coll = data["user"]["contributionsCollection"]
        total += coll["totalCommitContributions"] + coll["restrictedContributionsCount"]
    return total


def contributed_count():
    data = graphql(f'''query {{ user(login: "{USER}") {{
        repositoriesContributedTo(contributionTypes: [COMMIT, PULL_REQUEST])
        {{ totalCount }} }} }}''')
    return data["user"]["repositoriesContributedTo"]["totalCount"]


def lines_of_code(repos):
    added = deleted = 0
    for repo in repos:
        stats = None
        for _ in range(4):  # 202 = GitHub still computing; retry
            stats = call(f"{API}/repos/{USER}/{repo}/stats/contributors")
            if stats is not None:
                break
            time.sleep(3)
        for contributor in stats or []:
            if contributor["author"] and contributor["author"]["login"] == USER:
                for week in contributor["weeks"]:
                    added += week["a"]
                    deleted += week["d"]
    return added, deleted


# ---- line rendering ------------------------------------------------------

def tspan(text, cls=None):
    c = f' class="{cls}"' if cls else ""
    return f"<tspan{c}>{escape(text)}</tspan>"


def leader(label, parts):
    """'. label: .... value' — parts is [(text, cls), ...] for the value."""
    value_len = sum(len(t) for t, _ in parts)
    dots = max(3, WIDTH - 2 - len(label) - 2 - value_len - 1)
    return (tspan(". ", "muted") + tspan(label, "label")
            + tspan(": " + "." * dots + " ", "muted")
            + "".join(tspan(t, c) for t, c in parts))


def header(title, cls="accent"):
    dashes = max(3, WIDTH - len(title) - 1)
    return tspan(title, cls) + tspan(" " + "─" * (dashes - 1) + "-", "muted")


def spacer():
    return tspan(".", "muted")


def main():
    user = call(f"{API}/users/{USER}")
    repo_list = call(f"{API}/users/{USER}/repos?per_page=100")
    added, deleted = lines_of_code([r["name"] for r in repo_list])
    commits = total_commits(user["created_at"])
    contributed = contributed_count()
    today = datetime.date.today().isoformat()

    v = lambda t: [(t, None)]
    rows = [
        header("diego@zar.mx"),
        leader("OS", v("Debian 13, Hyprland")),
        leader("Host", v("Geoil Company, Frontend Developer")),
        leader("Uptime", v(f"{uptime(user['created_at'])} on GitHub")),
        leader("IDE", v("VSCode, DataGrip")),
        spacer(),
        leader("Languages.Programming", v("TypeScript, JavaScript, SQL")),
        leader("Frameworks", v("React, Astro, NestJS, Angular, Vite")),
        leader("Languages.Real", v("Spanish, English")),
        leader("Infra", v("Docker Swarm, Traefik, Cloudflare, AWS")),
        spacer(),
        header("- Contact", None),
        leader("Email", v("diego@zar.mx")),
        leader("Web", v("zar.mx")),
        leader("LinkedIn", v("in/diegozar02")),
        spacer(),
        header("- GitHub Stats", None),
        leader("Repos", v(f"{user['public_repos']} public")),
        leader("Followers", v(str(user["followers"]))),
        leader("Commits", v(f"{commits:,}")),
        leader("Lines of Code", [
            (f"{added - deleted:,} ( ", None),
            (f"{added:,}++", "plus"), (", ", None),
            (f"{deleted:,}--", "minus"), (" )", None),
        ]),
        spacer(),
        leader("Updated", v(today)),
    ]

    lines_xml = "\n".join(
        f'  <text x="{COL_X}" y="{Y0 + i * DY}" class="t">{row}</text>'
        for i, row in enumerate(rows)
    )

    template = string.Template(open("template.svg", encoding="utf-8").read())
    for filename, theme in THEMES.items():
        with open(filename, "w", encoding="utf-8") as f:
            f.write(template.substitute(**theme, LINES=lines_xml))
        print(f"wrote {filename}")
    print(f"stats: {commits:,} commits, +{added:,}/-{deleted:,}, contributed {contributed}")


if __name__ == "__main__":
    main()
