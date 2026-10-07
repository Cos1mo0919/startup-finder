"""Read-only checks against an actual deployed URL; records IDs for restart comparison."""

import argparse
import json
from pathlib import Path
import re
from urllib.parse import urljoin
import httpx


def verify(base, allow_http=False):
    if not base.startswith("https://") and not (allow_http and base.startswith("http://127.0.0.1:")):
        raise ValueError("Use an HTTPS deployment URL (or --local for an internal loopback check)")
    with httpx.Client(base_url=base.rstrip("/"), timeout=30, follow_redirects=True) as client:

        def get(path):
            response = client.get(path)
            response.raise_for_status()
            return response

        assert get("/api/health").json()["status"] == "ok"
        html = get("/").text
        assert 'lang="uz"' in html
        for asset in re.findall(r'(?:src|href)="([^"]+\.(?:js|css))"', html):
            get(urljoin(base, asset))
        assert 'lang="uz"' in get("/status").text
        status = get("/api/status").json()
        if status["scheduler_enabled"]:
            assert status["next_run"]
        today = get("/api/projects?period=today").json()
        rows = []
        page = 1
        while True:
            data = get(f"/api/projects?period=all&page_size=50&page={page}").json()
            rows.extend(data["items"])
            if len(rows) >= data["total"]:
                break
            page += 1
        for row in rows:
            detail = get("/api/projects/" + row["id"]).json()
            assert detail["name"] == row["name"] and detail["sources"]
            year = row["published_at"][:4]
            assert get(f"/api/projects?period=all&year={year}").json()["total"] > 0
            searched = client.get("/api/projects", params={"period": "all", "q": row["name"]})
            searched.raise_for_status()
            assert searched.json()["total"] > 0
            assert 'lang="uz"' in get("/loyiha/" + row["id"]).text
        return {
            "base_url": base,
            "scheduler_enabled": status["scheduler_enabled"],
            "next_run": status["next_run"],
            "today_count": today["total"],
            "visible_records": [
                {k: r[k] for k in ("id", "name", "published_at", "first_seen")} for r in rows
            ],
        }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("url")
    parser.add_argument("--local", action="store_true")
    parser.add_argument("--save", type=Path)
    parser.add_argument("--compare", type=Path)
    args = parser.parse_args()
    result = verify(args.url, args.local)
    if args.compare:
        old = json.loads(args.compare.read_text())
        previous = {r["id"]: r for r in old["visible_records"]}
        current = {r["id"]: r for r in result["visible_records"]}
        assert all(current.get(k) == v for k, v in previous.items()), (
            "Stored project identity or dates changed after restart"
        )
        result["restart_preservation"] = "passed"
    if args.save:
        args.save.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
