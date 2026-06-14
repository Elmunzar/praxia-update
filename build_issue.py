#!/usr/bin/env python3
"""Build one day's Praxia Update issue: JSON + PDF, refresh latest.* and the ICS feed.

Run daily (cron / GitHub Actions). Defaults to today's indexing window.

  python3 build_issue.py                  # today
  python3 build_issue.py --date 2026-06-12
  python3 build_issue.py --back 2         # widen window to last 2 days (catch indexing lag)
  python3 build_issue.py --base-url https://elmunzarr.github.io/praxia-update

Outputs under public/issues/:
  YYYY-MM-DD.json, YYYY-MM-DD.pdf, latest.json, latest.pdf, index.json, calendar.ics
"""

import os
import re
import sys
import json
import glob
import argparse
import datetime

import journals
import pubmed
from render import render_pdf, build_ics

HERE = os.path.dirname(os.path.abspath(__file__))
PUBLIC_DIR = os.path.join(HERE, "public")
ISSUES_DIR = os.path.join(PUBLIC_DIR, "issues")
DEFAULT_BASE_URL = os.environ.get("PRAXIA_BASE_URL", "https://example.github.io/praxia-update")


def write_subscriptions(base_url):
    """Publish the subscribed-journal list so the app can show 'Your journals'."""
    out = {"base_url": base_url.rstrip("/"), "journals": journals.load()}
    with open(os.path.join(PUBLIC_DIR, "subscriptions.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)


def _page_sort(pages):
    """Sort key from a page string ('739-746' -> 739) for table-of-contents order."""
    m = re.match(r"[A-Za-z]?(\d+)", pages or "")
    return int(m.group(1)) if m else 10 ** 9


def _prev_issue_map():
    """{journal key: (volume, issue)} from the last snapshot, to detect new issues."""
    try:
        with open(os.path.join(ISSUES_DIR, "latest.json"), encoding="utf-8") as f:
            prev = json.load(f)
        return {g["key"]: (g.get("volume", ""), g.get("issue", ""))
                for g in prev.get("groups", [])}
    except Exception:  # noqa: BLE001 - first run / missing file
        return {}


def build_issue(date, back_days, selected_keys):
    """Snapshot each subscribed journal's *current full issue* (its table of contents).

    Journals publish ~monthly with nothing added between issues, so we track the
    current issue rather than a daily diff. A journal is flagged `is_new` when its
    (volume, issue) differs from the previous snapshot. `back_days` is unused now
    (kept for CLI compatibility).
    """
    subscribed = journals.load()
    prev = _prev_issue_map()
    groups, total, new_issues = [], 0, 0

    for j in subscribed:
        if selected_keys is not None and j["key"] not in selected_keys:
            continue
        volume, issue, year, month, ids = pubmed.current_issue_ids(j["ta"])
        articles = pubmed.efetch_articles(ids) if ids else []
        for a in articles:
            a["journal_key"] = j["key"]
        articles.sort(key=lambda a: _page_sort(a.get("pages")))  # table-of-contents order

        prev_vi = prev.get(j["key"])
        is_new = bool(issue) and prev_vi is not None and prev_vi != (volume, issue)
        new_issues += 1 if is_new else 0
        total += len(articles)
        groups.append({
            "key": j["key"], "journal": j["name"], "ta": j["ta"],
            "volume": volume, "issue": issue, "pub_year": year, "pub_month": month,
            "is_new": is_new,
            "count": len(articles), "articles": articles,
        })
        tag = "NEW" if is_new else "   "
        print(f"  {tag} {j['name']:<44} Vol {volume or '?'} Iss {issue or '?'}: "
              f"{len(articles):>3} article(s)")

    journals_with = sum(1 for g in groups if g["count"] > 0)
    return {
        "date": date,
        "generated_at": datetime.datetime.now(datetime.timezone.utc)
                                 .strftime("%Y-%m-%dT%H:%M:%SZ"),
        "counts": {"articles": total, "journals_with_articles": journals_with,
                   "journals_searched": len(groups), "new_issues": new_issues},
        "groups": groups,
    }


def write_outputs(issue, base_url):
    os.makedirs(ISSUES_DIR, exist_ok=True)
    date = issue["date"]

    json_path = os.path.join(ISSUES_DIR, f"{date}.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(issue, f, ensure_ascii=False, indent=2)

    pdf_path = os.path.join(ISSUES_DIR, f"{date}.pdf")
    render_pdf(issue, pdf_path)

    # latest.* mirrors the most recent build for stable "current issue" URLs.
    for name, src in (("latest.json", json_path), ("latest.pdf", pdf_path)):
        dst = os.path.join(ISSUES_DIR, name)
        with open(src, "rb") as a, open(dst, "wb") as b:
            b.write(a.read())

    rebuild_index_and_calendar(base_url)
    write_subscriptions(base_url)
    return json_path, pdf_path


# Embed full article detail in the calendar for this many most-recent issues;
# older events stay as summary + PDF link so the .ics doesn't grow without bound.
CALENDAR_DETAIL_ISSUES = 45


def rebuild_index_and_calendar(base_url):
    """Scan all dated issues; rebuild index.json (front-end archive) and calendar.ics."""
    issues = []  # full issue dicts, newest first
    for path in sorted(glob.glob(os.path.join(ISSUES_DIR, "20*-*-*.json"))):
        try:
            with open(path, encoding="utf-8") as f:
                issues.append(json.load(f))
        except Exception as e:  # noqa: BLE001
            print(f"  skip {path}: {e}", file=sys.stderr)
    issues.sort(key=lambda d: d["date"], reverse=True)

    base = base_url.rstrip("/")

    # index.json: lightweight per-issue rows (loaded by the app on every visit).
    entries = []
    for d in issues:
        entries.append({
            "date": d["date"],
            "generated_at": d.get("generated_at"),
            "count": d["counts"]["articles"],
            "journals_with_articles": d["counts"]["journals_with_articles"],
            "pdf_url": f"{base}/issues/{d['date']}.pdf",
            "json_url": f"{base}/issues/{d['date']}.json",
            "app_url": f"{base}/?date={d['date']}",
        })
    with open(os.path.join(ISSUES_DIR, "index.json"), "w", encoding="utf-8") as f:
        json.dump({"base_url": base, "issues": entries}, f, ensure_ascii=False, indent=2)

    # Publish the current subscription list so the app's manager shows the live set.
    public_dir = os.path.dirname(ISSUES_DIR)
    with open(os.path.join(public_dir, "subscriptions.json"), "w", encoding="utf-8") as f:
        json.dump({"base_url": base, "journals": journals.load()}, f,
                  ensure_ascii=False, indent=2)

    # calendar.ics: recent events carry full per-article detail (abstracts + links).
    events = []
    for i, (entry, d) in enumerate(zip(entries, issues)):
        ev = dict(entry)
        if i < CALENDAR_DETAIL_ISSUES:
            ev["groups"] = d.get("groups", [])
        events.append(ev)

    build_ics(events, base, os.path.join(ISSUES_DIR, "calendar.ics"))
    print(f"  index.json + calendar.ics rebuilt ({len(entries)} issue(s))")


def main():
    p = argparse.ArgumentParser(description="Build a Praxia Update issue.")
    p.add_argument("--date", default=datetime.date.today().isoformat(),
                   help="Issue date YYYY-MM-DD (default: today).")
    p.add_argument("--back", type=int, default=1,
                   help="Indexing window size in days, to absorb PubMed lag (default: 1).")
    p.add_argument("--base-url", default=DEFAULT_BASE_URL,
                   help="Public base URL used in PDF/JSON/ICS links.")
    p.add_argument("--journals", default="",
                   help="Comma-separated journal keys to subset (default: all subscribed).")
    args = p.parse_args()

    selected = ([k.strip() for k in args.journals.split(",") if k.strip()]
                if args.journals else None)

    n = len(selected) if selected else len(journals.load())
    print(f"Praxia Update — building issue {args.date} "
          f"(window: last {args.back} day(s), {n} journals)")
    issue = build_issue(args.date, args.back, selected)
    json_path, pdf_path = write_outputs(issue, args.base_url)
    print(f"\nDone: {issue['counts']['articles']} article(s) -> "
          f"{os.path.relpath(json_path, HERE)}, {os.path.relpath(pdf_path, HERE)}")


if __name__ == "__main__":
    main()
