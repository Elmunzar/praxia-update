"""Render a day's issue to a PDF and maintain the subscribable ICS feed."""

import re
import html
import datetime

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.colors import HexColor, white
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, HRFlowable, PageBreak, Flowable,
    Table, TableStyle, KeepTogether,
)
from reportlab.pdfbase.pdfmetrics import stringWidth

NAVY = HexColor("#13264A")       # Praxia brand navy
ACCENT = HexColor("#C7452B")     # orthopaedic accent
MUTED = HexColor("#5b6470")

# Muted, professional palette for per-journal monogram badges (cycled by key).
BADGE_PALETTE = [
    "#13264A", "#2F6F62", "#9C6B2E", "#6E5BA6", "#A6453A",
    "#2C6B8F", "#5B7553", "#8A5A83", "#3F6C3A", "#9A7B2E", "#445A7A",
]
_MONTHS = {"01": "January", "02": "February", "03": "March", "04": "April",
           "05": "May", "06": "June", "07": "July", "08": "August",
           "09": "September", "10": "October", "11": "November", "12": "December",
           "jan": "January", "feb": "February", "mar": "March", "apr": "April",
           "may": "May", "jun": "June", "jul": "July", "aug": "August",
           "sep": "September", "oct": "October", "nov": "November", "dec": "December"}
_STOPWORDS = {"the", "of", "and", "for", "in", "&", "a", "an"}


def _initials(name):
    words = [w for w in re.split(r"[^A-Za-z]+", name) if w and w.lower() not in _STOPWORDS]
    # Keep existing acronyms (all-caps words like "JBJS") whole; otherwise take initials.
    letters = "".join(w if (w.isupper() and len(w) > 1) else w[0].upper() for w in words)
    return (letters or (name[:2].upper() if name else "?"))[:4]


def _journal_color(key):
    h = sum(ord(c) for c in (key or "x"))
    return HexColor(BADGE_PALETTE[h % len(BADGE_PALETTE)])


def _month_name(m):
    if not m:
        return ""
    return _MONTHS.get(m.lower()[:3], _MONTHS.get(m, m))


def _issue_label(articles, count):
    """A concise issue line: volume/issue when uniform, else month/year, + new count."""
    vols = {a.get("volume", "") for a in articles if a.get("volume")}
    issues = {a.get("issue", "") for a in articles if a.get("issue")}
    yms = [(a.get("pub_year", ""), _month_name(a.get("pub_month", "")))
           for a in articles if a.get("pub_year")]

    bits = []
    if len(vols) == 1:
        vol = next(iter(vols))
        seg = f"Volume {vol}"
        if len(issues) == 1:
            seg += f", Issue {next(iter(issues))}"
        bits.append(seg)
    # Most common year/month among the section's articles.
    if yms:
        ym = max(set(yms), key=yms.count)
        label = " ".join(x for x in (ym[1], ym[0]) if x).strip()
        if label:
            bits.append(label)
    if not vols:
        bits.append("online ahead of print")
    bits.append(f"{count} new article{'s' if count != 1 else ''}")
    return "  ·  ".join(bits)


class JournalBadge(Flowable):
    """A small rounded tile showing a journal's monogram in its accent colour."""

    def __init__(self, initials, color, size=15 * mm):
        super().__init__()
        self.initials = initials
        self.color = color
        self.size = size
        self.width = self.height = size

    def draw(self):
        c = self.canv
        c.setFillColor(self.color)
        c.roundRect(0, 0, self.size, self.size, self.size * 0.22, stroke=0, fill=1)
        fs = self.size * (0.42 if len(self.initials) <= 3 else 0.32)
        c.setFillColor(white)
        c.setFont("Helvetica-Bold", fs)
        tw = stringWidth(self.initials, "Helvetica-Bold", fs)
        c.drawString((self.size - tw) / 2, (self.size - fs) / 2 + fs * 0.30, self.initials)


def _styles():
    ss = getSampleStyleSheet()
    base = ss["BodyText"]
    return {
        "masthead": ParagraphStyle("masthead", parent=base, fontName="Helvetica-Bold",
                                   fontSize=24, textColor=NAVY, leading=27, spaceAfter=2),
        "dateline": ParagraphStyle("dateline", parent=base, fontName="Helvetica",
                                   fontSize=10, textColor=MUTED, spaceAfter=14),
        "journal": ParagraphStyle("journal", parent=base, fontName="Helvetica-Bold",
                                  fontSize=16, textColor=NAVY, leading=18, spaceBefore=0, spaceAfter=1),
        "journal_meta": ParagraphStyle("journal_meta", parent=base, fontName="Helvetica",
                                       fontSize=9, textColor=MUTED, leading=11, spaceAfter=0),
        "title": ParagraphStyle("title", parent=base, fontName="Helvetica-Bold",
                                fontSize=11, textColor=HexColor("#16202e"), leading=14, spaceAfter=2),
        "authors": ParagraphStyle("authors", parent=base, fontName="Helvetica-Oblique",
                                  fontSize=9, textColor=MUTED, leading=12, spaceAfter=3),
        "abstract": ParagraphStyle("abstract", parent=base, fontName="Helvetica",
                                   fontSize=9.5, textColor=HexColor("#222a35"), leading=13,
                                   alignment=TA_LEFT, spaceAfter=3),
        "links": ParagraphStyle("links", parent=base, fontName="Helvetica",
                               fontSize=8.5, textColor=ACCENT, spaceAfter=12),
        "empty": ParagraphStyle("empty", parent=base, fontName="Helvetica-Oblique",
                               fontSize=10, textColor=MUTED, spaceAfter=10),
    }


def _esc(s):
    return html.escape(s or "")


def _journal_masthead(group, arts, st):
    """Badge + journal name + issue/volume/date line, laid out like a masthead."""
    badge = JournalBadge(_initials(group["journal"]), _journal_color(group["key"]))
    name = Paragraph(_esc(group["journal"]), st["journal"])
    meta = Paragraph(_esc(_issue_label(arts, len(arts))), st["journal_meta"])
    tbl = Table([[badge, [name, meta]]], colWidths=[18 * mm, 156 * mm], hAlign="LEFT")
    tbl.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (0, 0), 0),
        ("LEFTPADDING", (1, 0), (1, 0), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    return tbl


def _article_flowables(a, st):
    out = [Paragraph(_esc(a["title"]), st["title"])]
    if a["authors"]:
        authors = ", ".join(a["authors"][:8]) + (" et al." if len(a["authors"]) > 8 else "")
        out.append(Paragraph(_esc(authors), st["authors"]))
    if a["abstract"]:
        body = a["abstract"]
        if len(body) > 1400:
            body = body[:1400].rstrip() + " […]"
        for para in body.split("\n\n"):
            out.append(Paragraph(_esc(para), st["abstract"]))
    links = []
    if a["pubmed_url"]:
        links.append(f'<link href="{a["pubmed_url"]}">PubMed</link>')
    if a["doi_url"]:
        links.append(f'<link href="{a["doi_url"]}">DOI</link>')
    if links:
        out.append(Paragraph(" &nbsp;·&nbsp; ".join(links), st["links"]))
    return out


def render_pdf(issue, out_path):
    """issue = {date, generated_at, groups: [{journal, articles:[...]}], counts}."""
    st = _styles()
    doc = SimpleDocTemplate(
        out_path, pagesize=A4,
        leftMargin=18 * mm, rightMargin=18 * mm,
        topMargin=16 * mm, bottomMargin=16 * mm,
        title=f"Praxia Update — {issue['date']}", author="Praxia Update",
    )
    flow = []
    pretty = datetime.date.fromisoformat(issue["date"]).strftime("%A, %d %B %Y")
    flow.append(Paragraph("Praxia Update", st["masthead"]))
    flow.append(Paragraph(
        f"Daily orthopaedic literature digest &nbsp;·&nbsp; {pretty} "
        f"&nbsp;·&nbsp; {issue['counts']['articles']} new articles across "
        f"{issue['counts']['journals_with_articles']} journals",
        st["dateline"]))
    flow.append(HRFlowable(width="100%", thickness=1.2, color=NAVY, spaceAfter=8))

    any_articles = False
    for group in issue["groups"]:
        arts = group["articles"]
        if not arts:
            continue
        any_articles = True
        masthead = [
            Spacer(1, 14),
            _journal_masthead(group, arts, st),
            HRFlowable(width="100%", thickness=1.0, color=_journal_color(group["key"]),
                       spaceBefore=4, spaceAfter=8),
        ]
        # Keep the masthead with its first article so a header never sits alone at a page end.
        flow.append(KeepTogether(masthead + _article_flowables(arts[0], st)))
        for a in arts[1:]:
            flow.extend(_article_flowables(a, st))

    if not any_articles:
        flow.append(Paragraph(
            "No newly indexed articles in the selected journals for this date. "
            "PubMed indexing can lag publication by 1–2 days — check back tomorrow.",
            st["empty"]))

    doc.build(flow)


# ---------------------------------------------------------------------------
# ICS subscribable feed: one VEVENT per issue day, link in URL: and DESCRIPTION:.
# Calendar apps (Google/Apple/Outlook) auto-refresh a subscribed feed.
# ---------------------------------------------------------------------------

def _ics_escape(text):
    return (text.replace("\\", "\\\\").replace(";", "\\;")
                .replace(",", "\\,").replace("\n", "\\n"))


def _fold(line):
    # RFC 5545: fold lines longer than 75 octets.
    out, b = [], line.encode("utf-8")
    while len(b) > 73:
        cut = 73
        while (b[cut] & 0xC0) == 0x80:  # don't split a UTF-8 codepoint
            cut -= 1
        out.append(b[:cut].decode("utf-8"))
        b = b" " + b[cut:]
    out.append(b.decode("utf-8"))
    return "\r\n".join(out)


# How much article detail to embed in each calendar event.
ICS_MAX_ARTICLES = 60      # cap articles listed per event (rest -> "see PDF")
ICS_SNIPPET_CHARS = 320    # abstract snippet length per article


def _snippet(abstract, limit=ICS_SNIPPET_CHARS):
    if not abstract:
        return ""
    text = " ".join(abstract.split())  # collapse the labelled-section newlines
    return text if len(text) <= limit else text[:limit].rsplit(" ", 1)[0] + " […]"


def _event_description(ev, pdf_url, app_url):
    """Rich body: summary, links, then articles grouped by journal with snippets."""
    n = ev.get("count", 0)
    jn = ev.get("journals_with_articles", 0)
    lines = [
        f"{n} newly indexed orthopaedic article{'s' if n != 1 else ''} "
        f"across {jn} journal{'s' if jn != 1 else ''}.",
        "",
        f"📄 Open the full issue (PDF): {pdf_url}",
        f"🔗 Browse in the app: {app_url}",
    ]
    groups = [g for g in (ev.get("groups") or []) if g.get("count")]
    if not groups:
        return "\n".join(lines)

    shown = 0
    for g in groups:
        if shown >= ICS_MAX_ARTICLES:
            break
        lines += ["", f"— {g['journal']} ({g['count']}) —"]
        for a in g["articles"]:
            if shown >= ICS_MAX_ARTICLES:
                lines.append("  …more in the PDF.")
                break
            shown += 1
            lines.append(f"• {a.get('title', '').rstrip('.')}.")
            authors = a.get("authors") or []
            if authors:
                lines.append("  " + ", ".join(authors[:6]) + (" et al." if len(authors) > 6 else ""))
            refs = []
            if a.get("pubmed_url"):
                refs.append(f"PubMed {a['pubmed_url']}")
            if a.get("doi_url"):
                refs.append(f"DOI {a['doi_url']}")
            if refs:
                lines.append("  " + "  ".join(refs))
            snip = _snippet(a.get("abstract", ""))
            if snip:
                lines.append("  " + snip)
    total_articles = sum(g["count"] for g in groups)
    if total_articles > shown:
        lines += ["", f"(+{total_articles - shown} more — open the PDF for the full issue.)"]
    return "\n".join(lines)


def build_ics(events, base_url, out_path):
    """events = [{date, count, journals_with_articles, generated_at, groups?}], any order.

    Each issue is an all-day event on its date. The day's PDF is the clickable target
    (URL:), and the DESCRIPTION carries the new articles with snippets + PubMed/DOI links.
    Events that include `groups` get the full per-article body; others get summary + links.
    """
    base_url = base_url.rstrip("/")
    lines = [
        "BEGIN:VCALENDAR", "VERSION:2.0",
        "PRODID:-//Praxia//Praxia Update//EN",
        "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
        "X-WR-CALNAME:Praxia Update — Orthopaedic Digest",
        "X-WR-CALDESC:Daily orthopaedic literature digest. Each event lists the day's new articles and links its issue PDF.",
        "X-PUBLISHED-TTL:PT12H",
        "REFRESH-INTERVAL;VALUE=DURATION:PT12H",
    ]
    for ev in events:
        d = datetime.date.fromisoformat(ev["date"])
        dtstart = d.strftime("%Y%m%d")
        dtend = (d + datetime.timedelta(days=1)).strftime("%Y%m%d")
        # Normalise generated_at (ISO) -> ICS UTC stamp.
        try:
            stamp = datetime.datetime.fromisoformat(
                ev["generated_at"].replace("Z", "+00:00")
            ).strftime("%Y%m%dT%H%M%SZ")
        except Exception:  # noqa: BLE001
            stamp = d.strftime("%Y%m%dT080000Z")
        pdf_url = ev.get("pdf_url") or f"{base_url}/issues/{ev['date']}.pdf"
        app_url = ev.get("app_url") or f"{base_url}/?date={ev['date']}"
        n = ev.get("count", 0)
        summary = f"Praxia Update — {n} new article{'s' if n != 1 else ''}"
        desc = _event_description(ev, pdf_url, app_url)
        block = [
            "BEGIN:VEVENT",
            f"UID:praxia-update-{ev['date']}@praxia",
            f"DTSTAMP:{stamp}",
            f"DTSTART;VALUE=DATE:{dtstart}",
            f"DTEND;VALUE=DATE:{dtend}",
            f"SUMMARY:{_ics_escape(summary)}",
            f"DESCRIPTION:{_ics_escape(desc)}",
            f"URL:{_ics_escape(pdf_url)}",
            "TRANSP:TRANSPARENT",
            "END:VEVENT",
        ]
        lines.extend(_fold(l) for l in block)
    lines.append("END:VCALENDAR")
    with open(out_path, "w", encoding="utf-8", newline="") as f:
        f.write("\r\n".join(_fold(l) if l.startswith(("X-", "REFRESH")) else l
                            for l in lines) + "\r\n")
