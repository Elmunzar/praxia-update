#!/usr/bin/env python3
"""Email the day's issue to subscribers via Resend, and manage the subscriber list.

  python3 mail_issue.py --list
  python3 mail_issue.py --add you@example.com
  python3 mail_issue.py --remove you@example.com
  python3 mail_issue.py --send                 # email the latest issue to everyone
  python3 mail_issue.py --send --date 2026-06-13
  python3 mail_issue.py --send --dry-run        # render + print, don't send

Sending needs the env var RESEND_API_KEY (set it as a GitHub Actions secret), and a
verified sender domain configured in config/subscribers.json (from_email). No
passwords are ever handled — subscribers give only their address.
"""

import os
import sys
import html
import json
import argparse
import datetime
import urllib.request
import urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG = os.path.join(HERE, "config", "subscribers.json")
ISSUES_DIR = os.path.join(HERE, "public", "issues")
RESEND_ENDPOINT = "https://api.resend.com/emails"

NAVY = "#13264A"
TEAL = "#2BB8C4"
MUTED = "#5b6470"


def load_config():
    with open(CONFIG, encoding="utf-8") as f:
        return json.load(f)


def save_config(cfg):
    with open(CONFIG, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
        f.write("\n")


def cmd_list():
    cfg = load_config()
    subs = cfg.get("subscribers", [])
    print(f"{len(subs)} subscriber(s); sender: {cfg.get('from_name')} <{cfg.get('from_email')}>")
    for s in subs:
        print(" ", s)


def cmd_add(email):
    cfg = load_config()
    email = email.strip().lower()
    if "@" not in email:
        print(f"Not an email address: {email}"); sys.exit(1)
    subs = cfg.setdefault("subscribers", [])
    if email in subs:
        print(f"Already subscribed: {email}"); return
    subs.append(email); save_config(cfg)
    print(f"Added: {email}")


def cmd_remove(email):
    cfg = load_config()
    email = email.strip().lower()
    subs = cfg.get("subscribers", [])
    if email not in subs:
        print(f"Not in list: {email}"); sys.exit(1)
    subs.remove(email); save_config(cfg)
    print(f"Removed: {email}")


def load_issue(date):
    name = f"{date}.json" if date else "latest.json"
    path = os.path.join(ISSUES_DIR, name)
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def base_url():
    env = os.environ.get("PRAXIA_BASE_URL", "").strip().rstrip("/")
    if env:
        return env
    try:
        with open(os.path.join(ISSUES_DIR, "index.json"), encoding="utf-8") as f:
            return (json.load(f).get("base_url") or "").rstrip("/")
    except Exception:  # noqa: BLE001
        return "https://example.github.io/praxia-update"


def _esc(s):
    return html.escape(s or "")


def render_email(issue, base):
    """Return (subject, html) for one issue — a clean, inline-styled digest."""
    date = issue["date"]
    pretty = datetime.date.fromisoformat(date).strftime("%A, %d %B %Y")
    n = issue["counts"]["articles"]
    jn = issue["counts"]["journals_with_articles"]
    subject = f"Praxia Update — {pretty}: {n} new article{'s' if n != 1 else ''}"
    pdf_url = f"{base}/issues/{date}.pdf"
    app_url = f"{base}/?date={date}"

    blocks = []
    for g in issue["groups"]:
        if not g.get("count"):
            continue
        rows = []
        for a in g["articles"]:
            authors = ", ".join(a.get("authors", [])[:8]) + (" et al." if len(a.get("authors", [])) > 8 else "")
            links = []
            if a.get("pubmed_url"):
                links.append(f'<a href="{a["pubmed_url"]}" style="color:{TEAL};text-decoration:none">PubMed</a>')
            if a.get("doi_url"):
                links.append(f'<a href="{a["doi_url"]}" style="color:{TEAL};text-decoration:none">DOI</a>')
            page_bits = ["Pages " + _esc(a["pages"])] if a.get("pages") else []
            meta = " &middot; ".join(page_bits + links)
            authors_html = ""
            if authors:
                authors_html = (f'<div style="font:italic 13px/1.4 Arial,sans-serif;'
                                f'color:{MUTED};margin-top:2px">{_esc(authors)}</div>')
            title = _esc(a["title"])
            rows.append(
                f'<div style="margin:0 0 14px">'
                f'<div style="font:600 15px/1.35 -apple-system,Segoe UI,Roboto,Arial,sans-serif;color:#16202e">{title}</div>'
                f'{authors_html}'
                f'<div style="font:13px/1.4 Arial,sans-serif;color:{MUTED};margin-top:3px">{meta}</div>'
                f'</div>')
        blocks.append(
            f'<tr><td style="padding:18px 24px 4px">'
            f'<div style="font:700 16px/1.3 Arial,sans-serif;color:{NAVY};border-bottom:2px solid {NAVY};padding-bottom:6px;margin-bottom:12px">'
            f'{_esc(g["journal"])} <span style="color:{MUTED};font-weight:400">({g["count"]})</span></div>'
            f'{"".join(rows)}</td></tr>')

    body = "".join(blocks) or (
        f'<tr><td style="padding:24px;color:{MUTED};font:14px Arial,sans-serif">'
        "No newly indexed articles in your journals today.</td></tr>")

    html_doc = f"""<!DOCTYPE html>
<html><body style="margin:0;background:#f6f7f9">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f6f7f9">
<tr><td align="center" style="padding:24px 12px">
<table role="presentation" width="600" cellpadding="0" cellspacing="0" style="max-width:600px;background:#fff;border-radius:12px;overflow:hidden">
  <tr><td style="background:{NAVY};padding:22px 24px">
    <div style="font:700 22px Arial,sans-serif;color:#fff">Praxia Update</div>
    <div style="font:13px Arial,sans-serif;color:#aebbd2;margin-top:2px">Daily orthopaedic literature digest</div>
  </td></tr>
  <tr><td style="padding:18px 24px 0">
    <div style="font:700 16px Arial,sans-serif;color:{NAVY}">{pretty}</div>
    <div style="font:13px Arial,sans-serif;color:{MUTED};margin-top:2px">{n} new article{'s' if n != 1 else ''} across {jn} journal{'s' if jn != 1 else ''}
      &nbsp;&middot;&nbsp; <a href="{app_url}" style="color:{TEAL};text-decoration:none">Open in browser</a>
      &nbsp;&middot;&nbsp; <a href="{pdf_url}" style="color:{TEAL};text-decoration:none">PDF</a></div>
  </td></tr>
  {body}
  <tr><td style="padding:18px 24px 24px;border-top:1px solid #e6e9ed">
    <div style="font:11px/1.5 Arial,sans-serif;color:{MUTED}">
      An alerting aid built on PubMed (U.S. National Library of Medicine) — not a substitute for the
      primary source or clinical judgement. You're receiving this because you subscribed at {_esc(base)}.
    </div>
  </td></tr>
</table>
</td></tr></table>
</body></html>"""
    return subject, html_doc


def send_one(api_key, sender, to, subject, html_doc):
    payload = json.dumps({"from": sender, "to": [to], "subject": subject, "html": html_doc}).encode()
    req = urllib.request.Request(RESEND_ENDPOINT, data=payload, method="POST", headers={
        "Authorization": f"Bearer {api_key}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def cmd_send(date, dry_run):
    cfg = load_config()
    # Recipients = config list + the SUBSCRIBERS secret (comma-separated), so real
    # addresses can stay out of a public repo. Deduped, order preserved.
    env_subs = [e.strip() for e in os.environ.get("SUBSCRIBERS", "").split(",") if e.strip()]
    subs = list(dict.fromkeys(cfg.get("subscribers", []) + env_subs))
    if not subs:
        print("No subscribers. Add one: python3 mail_issue.py --add you@example.com"); return
    issue = load_issue(date)
    subject, html_doc = render_email(issue, base_url())
    sender = f"{cfg.get('from_name', 'Praxia Update')} <{cfg.get('from_email')}>"

    if dry_run:
        out = os.path.join(HERE, "public", "issues", f"email-{issue['date']}.html")
        with open(out, "w", encoding="utf-8") as f:
            f.write(html_doc)
        print(f"[dry-run] subject: {subject}")
        print(f"[dry-run] {len(subs)} recipient(s); sender {sender}")
        print(f"[dry-run] HTML written to {os.path.relpath(out, HERE)} ({len(html_doc)} bytes)")
        return

    api_key = os.environ.get("RESEND_API_KEY", "").strip()
    if not api_key:
        print("RESEND_API_KEY not set — cannot send. (Set it as a GitHub Actions secret.)"); sys.exit(1)
    sent = 0
    for to in subs:
        try:
            send_one(api_key, sender, to, subject, html_doc); sent += 1
        except urllib.error.HTTPError as e:
            print(f"  failed {to}: {e.code} {e.read().decode('utf-8', 'replace')[:200]}", file=sys.stderr)
        except Exception as e:  # noqa: BLE001
            print(f"  failed {to}: {e}", file=sys.stderr)
    print(f"Sent {sent}/{len(subs)} — {subject}")


def main():
    p = argparse.ArgumentParser(description="Email the daily issue / manage subscribers.")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--list", action="store_true")
    g.add_argument("--add", metavar="EMAIL")
    g.add_argument("--remove", metavar="EMAIL")
    g.add_argument("--send", action="store_true")
    p.add_argument("--date", default=None, help="Issue date YYYY-MM-DD (default: latest).")
    p.add_argument("--dry-run", action="store_true", help="Render but don't send.")
    args = p.parse_args()
    if args.list: cmd_list()
    elif args.add: cmd_add(args.add)
    elif args.remove: cmd_remove(args.remove)
    elif args.send: cmd_send(args.date, args.dry_run)


if __name__ == "__main__":
    main()
