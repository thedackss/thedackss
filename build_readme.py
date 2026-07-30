#!/usr/bin/env python3
"""Rebuild the profile card SVGs with live GitHub stats.

Runs daily in GitHub Actions with the default GITHUB_TOKEN (public data only;
restrictedContributionsCount covers private commit totals since the profile
has private contributions enabled).
"""
import datetime
import json
import os
import string
import time
import urllib.request

TOKEN = os.environ["GITHUB_TOKEN"]
USER = os.environ.get("USER_NAME", "thedackss")
API = "https://api.github.com"

THEMES = {
    "card-dark.svg": {
        "bg": "#0d1117", "border": "#30363d", "fg": "#c9d1d9",
        "accent": "#58a6ff", "muted": "#8b949e", "bolt": "#f1e05a",
    },
    "card-light.svg": {
        "bg": "#ffffff", "border": "#d0d7de", "fg": "#24292f",
        "accent": "#0969da", "muted": "#57606a", "bolt": "#b08800",
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
    days = (now - anniversary).days
    return f"{years} years, {days} days"


def total_commits(created_at):
    first_year = int(created_at[:4])
    this_year = datetime.date.today().year
    total = 0
    for year in range(first_year, this_year + 1):
        data = graphql(f'''query {{ user(login: "{USER}") {{
            contributionsCollection(
                from: "{year}-01-01T00:00:00Z", to: "{year}-12-31T23:59:59Z"
            ) {{ totalCommitContributions restrictedContributionsCount }} }} }}''')
        coll = data["user"]["contributionsCollection"]
        total += coll["totalCommitContributions"] + coll["restrictedContributionsCount"]
    return total


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


def main():
    user = call(f"{API}/users/{USER}")
    repo_list = call(f"{API}/users/{USER}/repos?per_page=100")
    stars = sum(r["stargazers_count"] for r in repo_list)
    added, deleted = lines_of_code([r["name"] for r in repo_list])

    values = {
        "uptime": uptime(user["created_at"]),
        "repos": user["public_repos"],
        "stars": stars,
        "followers": user["followers"],
        "commits": f"{total_commits(user['created_at']):,}",
        "loc_add": f"{added:,}",
        "loc_del": f"{deleted:,}",
        "loc_net": f"{added - deleted:,}",
        "updated": datetime.date.today().isoformat(),
    }

    template = string.Template(open("template.svg", encoding="utf-8").read())
    for filename, theme in THEMES.items():
        with open(filename, "w", encoding="utf-8") as f:
            f.write(template.substitute(**theme, **values))
        print(f"wrote {filename}")
    print(json.dumps(values, indent=2))


if __name__ == "__main__":
    main()
