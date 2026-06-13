# Praxia Update

A daily orthopaedic literature digest. Each morning it pulls newly **indexed**
articles from your chosen journals via PubMed, then publishes:

- a browsable **web app** (journal picker, search, abstracts, PubMed/DOI links),
- a dated **PDF** — "the current issue", with a per-journal masthead, and
- a subscribable **calendar feed** — one event per day whose link opens that day's PDF.

Everything is static files served from GitHub Pages; only the once-a-day build runs
server-side (GitHub Actions). No backend, no database.

---

## How it works

```
            ┌─ GitHub Actions (daily cron) ─────────────────────────┐
            │ build_issue.py                                         │
 PubMed  ◄──┤   esearch (per journal, edat window)  → PMIDs         │
 E-utils    │   efetch  (XML: title/abstract/authors/DOI/issue)     │
            │   render  → issues/<date>.json + <date>.pdf           │
            │   rebuild → index.json, calendar.ics, subscriptions   │
            └───────────────────────┬───────────────────────────────┘
                                    │ commit + deploy
                                    ▼
            GitHub Pages (static):  public/
              index.html ............ the app (fetches issues/<date>.json)
              issues/<date>.pdf ..... the day's issue
              issues/calendar.ics ... subscribe once; auto-refreshes
```

`config/journals.json` is the single source of truth for **which** journals are
fetched. Change it in the app or with `manage_journals.py`.

---

## Quick start (local)

```bash
pip install -r requirements.txt

# Build today's issue into public/issues/ (uses your subscribed journals)
python3 build_issue.py --base-url "http://localhost:8000"

# Preview the app
python3 -m http.server 8000 --directory public
# open http://localhost:8000
```

Useful build flags:

```bash
python3 build_issue.py --date 2026-06-12     # a specific day
python3 build_issue.py --back 2              # widen the window (PubMed lag)
python3 build_issue.py --journals ajsm,bjj   # subset, by key
```

---

## Deploy (GitHub Pages + Actions)

1. Push this folder to a GitHub repo.
2. **Settings → Pages → Build and deployment → Source: GitHub Actions.**
3. (Optional) **Settings → Secrets and variables → Actions:**
   - Variable `PRAXIA_BASE_URL` — only if you use a custom domain. Otherwise the
     workflow auto-derives `https://<you>.github.io/<repo>`.
   - Secret `PUBMED_API_KEY` — optional [NCBI key](https://www.ncbi.nlm.nih.gov/account/)
     to raise the rate limit (3→10 req/s).
4. **Actions → "Praxia Update — daily issue" → Run workflow** to publish the first
   issue now. After that it runs every day at 07:00 UTC.

The job builds the issue, commits it to the repo (so the archive accumulates), and
deploys `public/` to Pages.

---

## Subscribe in your calendar

Open the app → **Subscribe**, copy the feed URL
(`…/issues/calendar.ics`), and add it once:

- **Apple Calendar:** File → New Calendar Subscription → paste.
- **Google Calendar:** Other calendars → From URL → paste.
- **Outlook:** Add calendar → Subscribe from web → paste.

Each day appears as an event listing the new articles (titles, abstract snippets,
PubMed/DOI links); the event link opens that day's PDF. The feed auto-refreshes.

---

## Email digest (Resend)

Send the daily issue by email — recipients give only their **address** (no passwords).

1. Create a free [Resend](https://resend.com) account and **verify a sending domain**.
2. Set the sender in `config/subscribers.json` → `from_email` (e.g. `updates@yourdomain`).
3. Add the Resend API key as a GitHub Actions **secret** named `RESEND_API_KEY`
   (Settings → Secrets and variables → Actions). The daily build then emails the list.
4. Add recipients: `python3 mail_issue.py --add you@example.com` (commit the change),
   `--remove`, or `--list`.

Preview locally without sending: `python3 mail_issue.py --send --dry-run`
(writes the HTML to `public/issues/email-<date>.html`).

---

## Choose your journals

The 11 orthopaedic journals ship by default, but you can track **any**
PubMed-indexed journal.

**In the app:** open **Journals → Add a journal**, search by name (or paste a
journal URL), and **Add**. The app resolves it via the NLM Catalog. New additions
are marked *pending* — tap **Copy subscription file** and commit it to
`config/journals.json` (or use the CLI below) so the daily build starts fetching it.

**From the terminal:**

```bash
python3 manage_journals.py --list
python3 manage_journals.py --search "foot ankle international"
python3 manage_journals.py --add    "Foot & Ankle International"
python3 manage_journals.py --add    "https://www.thelancet.com"     # URL also works
python3 manage_journals.py --remove foot_ankle_international
```

If a name is ambiguous, `--add` lists the matches and you re-run with the exact
abbreviation, e.g. `--add-ta "J Hand Surg Am" --name "Journal of Hand Surgery (American)"`.

---

## Share a PDF

In the app: **Share** opens the native share sheet (AirDrop, WhatsApp, Files,
Praxia, Praxia Docs, …) on devices that support it (e.g. iOS Safari); **Download**
saves the PDF. **Open PDF** views it in the browser.

---

## File map

| File | Role |
|------|------|
| `config/journals.json` | Your subscribed journals (the fetch list) |
| `build_issue.py` | Daily job: fetch → JSON + PDF → index/calendar/subscriptions |
| `pubmed.py` | PubMed E-utilities client (esearch / efetch) |
| `nlm_catalog.py` | Resolve a journal name/URL → PubMed `[TA]` |
| `manage_journals.py` | CLI to add/remove/list journals |
| `render.py` | PDF rendering (reportlab) + ICS calendar feed |
| `journals.py` | Load/save the journal config |
| `public/` | The static site (app + generated issues) |
| `.github/workflows/daily.yml` | Daily build + Pages deploy |

---

## Notes

- **Indexing lag.** "Day of issue" = the day PubMed indexes an article, which can
  trail the publisher by 1–2 days. `--back` widens the catch-up window.
- **Rate limits.** Without a key NCBI allows ~3 req/s; the client throttles itself.
  Set `PUBMED_API_KEY` for 10 req/s.
- **Archive growth.** Each day commits a JSON + PDF (~100 KB). Prune old
  `public/issues/*` periodically if the repo gets large.
- **Data source.** U.S. National Library of Medicine (PubMed). An alerting aid, not
  a substitute for the primary sources.
