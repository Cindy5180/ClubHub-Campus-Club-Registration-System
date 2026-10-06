import os, re, sys, json, time, random, pathlib, requests

TOKEN = os.environ["REPO_TOKEN"]
REPOS = [r.strip() for r in os.environ["TARGET_REPOS"].split(",") if r.strip()]
MAX_RETRIES = int(os.environ.get("MAX_RETRIES", 5))
CACHE = pathlib.Path(".cache/activity.json")
README = pathlib.Path("README.md")
START, END = "<!-- ACTIVITY:START -->", "<!-- ACTIVITY:END -->"
H = {"Authorization": f"Bearer {TOKEN}",
     "Accept": "application/vnd.github+json",
     "X-GitHub-Api-Version": "2022-11-28"}

def gh_get(url, params=None):
    for n in range(MAX_RETRIES):
        r = requests.get(url, headers=H, params=params, timeout=20)
        if r.status_code == 200:
            return r.json()
        limited = r.status_code in (403, 429) and (
            r.headers.get("X-RateLimit-Remaining") == "0" or "Retry-After" in r.headers)
        if limited:
            reset = int(r.headers.get("X-RateLimit-Reset", time.time() + 60))
            wait = min(int(r.headers.get("Retry-After", max(reset - time.time(), 1))), 120)
        elif r.status_code >= 500:
            wait = 2 ** n + random.random()
        else:
            r.raise_for_status()
        print(f"retry {n+1}/{MAX_RETRIES} in {wait:.0f}s (HTTP {r.status_code})")
        time.sleep(wait)
    raise RuntimeError("GitHub API failed after retries")

def fetch(repo):
    data = gh_get(f"https://api.github.com/repos/{repo}/commits", {"per_page": 10})
    out = []
    for c in data:
        msg = c["commit"]["message"].splitlines()[0]
        if msg.startswith("chore(bot):"):
            continue
        out.append({"repo": repo, "sha": c["sha"][:7], "msg": msg,
                    "date": c["commit"]["author"]["date"], "url": c["html_url"]})
    return out[:5]

def main():
    text = README.read_text(encoding="utf-8")
    if START not in text or END not in text:
        sys.exit("README markers missing")
    items = []
    for repo in REPOS:
        try:
            items += fetch(repo)
        except Exception as e:
            print(f"skip {repo}: {type(e).__name__}")
    if items:
        CACHE.parent.mkdir(exist_ok=True)
        CACHE.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    elif CACHE.exists():
        items = json.loads(CACHE.read_text(encoding="utf-8"))
    items = sorted(items, key=lambda x: x["date"], reverse=True)[:10]
    body = "\n".join(f"- [`{i['sha']}`]({i['url']}) **{i['repo']}** — {i['msg']} ({i['date'][:10]})"
                     for i in items) or "_No activity_"
    new = re.sub(f"{re.escape(START)}.*?{re.escape(END)}",
                 lambda m: f"{START}\n{body}\n{END}", text, flags=re.S)
    README.write_text(new, encoding="utf-8")

if __name__ == "__main__":
    main()
