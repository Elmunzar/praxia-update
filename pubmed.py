"""PubMed E-utilities client (stdlib only).

Pipeline per the verified spec:
  1. esearch  — find PMIDs newly *indexed* (datetype=edat) in a date window for one [TA].
  2. efetch   — pull structured XML (title, abstract, authors, DOI) for those PMIDs.

No API key required. Set PUBMED_API_KEY to raise the rate limit 3/s -> 10/s.
Server-side use only: browsers hit CORS / rate limits on bulk efetch.
"""

import os
import re
import time
import json
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
API_KEY = os.environ.get("PUBMED_API_KEY", "").strip()
TOOL = "praxia-update"
EMAIL = os.environ.get("PUBMED_EMAIL", "elmunzarr@gmail.com")

# Be polite to NCBI: 3 req/s without a key, 10 with one.
_MIN_INTERVAL = 0.11 if API_KEY else 0.34
_last_call = [0.0]


def _throttle():
    wait = _MIN_INTERVAL - (time.monotonic() - _last_call[0])
    if wait > 0:
        time.sleep(wait)
    _last_call[0] = time.monotonic()


def _common(params):
    params = dict(params)
    params.update({"tool": TOOL, "email": EMAIL})
    if API_KEY:
        params["api_key"] = API_KEY
    return params


def _get(endpoint, params, retries=3):
    url = BASE + endpoint + "?" + urllib.parse.urlencode(_common(params))
    return _request(url, None, retries)


def _post(endpoint, params, retries=3):
    data = urllib.parse.urlencode(_common(params)).encode()
    return _request(BASE + endpoint, data, retries)


def _request(url, data, retries):
    last = None
    for attempt in range(retries):
        _throttle()
        try:
            req = urllib.request.Request(url, data=data, headers={"User-Agent": TOOL})
            with urllib.request.urlopen(req, timeout=45) as resp:
                return resp.read().decode("utf-8", "replace")
        except Exception as e:  # noqa: BLE001 - retry on any transient network error
            last = e
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"PubMed request failed after {retries} tries: {last}")


def esearch_ids(ta, mindate, maxdate, retmax=200):
    """Return PMIDs for one journal [TA] newly indexed in [mindate, maxdate] (YYYY/MM/DD)."""
    params = {
        "db": "pubmed",
        "retmode": "json",
        "retmax": str(retmax),
        "datetype": "edat",
        "mindate": mindate,
        "maxdate": maxdate,
        "term": f'"{ta}"[TA]',
    }
    raw = _get("esearch.fcgi", params)
    return json.loads(raw)["esearchresult"].get("idlist", [])


def _text(el):
    """Flatten an element's text content, including inline markup children."""
    if el is None:
        return ""
    return "".join(el.itertext()).strip()


def efetch_articles(pmids):
    """Fetch structured records for PMIDs. POST avoids URL-length limits on large sets."""
    if not pmids:
        return []
    params = {"db": "pubmed", "retmode": "xml", "rettype": "abstract", "id": ",".join(pmids)}
    xml = _post("efetch.fcgi", params)
    root = ET.fromstring(xml)
    out = []
    for art in root.findall(".//PubmedArticle"):
        out.append(_parse_article(art))
    return out


def _parse_article(art):
    medline = art.find(".//MedlineCitation")
    article = medline.find("Article") if medline is not None else None

    pmid = _text(medline.find("PMID")) if medline is not None else ""
    title = _text(article.find("ArticleTitle")) if article is not None else ""

    # Abstract: concatenate labelled sections (BACKGROUND / METHODS / ...).
    abstract_parts = []
    if article is not None:
        for ab in article.findall(".//Abstract/AbstractText"):
            label = ab.get("Label")
            body = _text(ab)
            if label and body:
                abstract_parts.append(f"{label}: {body}")
            elif body:
                abstract_parts.append(body)
    abstract = "\n\n".join(abstract_parts)

    # Authors -> "Smith JA"
    authors = []
    if article is not None:
        for a in article.findall(".//AuthorList/Author"):
            last = _text(a.find("LastName"))
            initials = _text(a.find("Initials"))
            collective = _text(a.find("CollectiveName"))
            if last:
                authors.append(f"{last} {initials}".strip())
            elif collective:
                authors.append(collective)

    # DOI lives in ArticleIdList (idtype="doi") or ELocationID.
    doi = ""
    for aid in art.findall(".//ArticleIdList/ArticleId"):
        if aid.get("IdType") == "doi":
            doi = _text(aid)
            break
    if not doi and article is not None:
        for eloc in article.findall("ELocationID"):
            if eloc.get("EIdType") == "doi":
                doi = _text(eloc)
                break

    # Journal TA + issue metadata (volume / issue / pub date) for the masthead.
    ta = volume = issue = pub_year = pub_month = pages = ""
    pub_types = []
    if article is not None:
        ta = _text(article.find(".//Journal/ISOAbbreviation"))
        ji = article.find(".//Journal/JournalIssue")
        if ji is not None:
            volume = _text(ji.find("Volume"))
            issue = _text(ji.find("Issue"))
            pub_year = _text(ji.find("PubDate/Year"))
            pub_month = _text(ji.find("PubDate/Month"))
            if not pub_year:  # some records use MedlineDate, e.g. "2026 Jun"
                md = _text(ji.find("PubDate/MedlineDate"))
                parts = md.split()
                if parts:
                    pub_year = parts[0]
                    if len(parts) > 1:
                        pub_month = parts[1]
        # Pagination (e.g. "735-738") for the table-of-contents look.
        pages = _text(article.find(".//Pagination/MedlinePgn"))
        if not pages:
            sp = _text(article.find(".//Pagination/StartPage"))
            ep = _text(article.find(".//Pagination/EndPage"))
            pages = f"{sp}-{ep}" if sp and ep else sp
        # Keep only realistic page ranges; online-ahead-of-print records put a long
        # article id in MedlinePgn (e.g. the DOI suffix) — drop those.
        if pages and not re.match(r"^[A-Za-z]?\d{1,5}(-[A-Za-z]?\d{1,5})?$", pages):
            pages = ""
        # Publication types → a single "section" label for grouping the contents.
        pub_types = [_text(pt) for pt in article.findall(".//PublicationTypeList/PublicationType")
                     if _text(pt)]

    section = _section_for(pub_types)

    return {
        "pmid": pmid,
        "title": title,
        "authors": authors,
        "abstract": abstract,
        "doi": doi,
        "journal_ta": ta,
        "volume": volume,
        "issue": issue,
        "pub_year": pub_year,
        "pub_month": pub_month,
        "pages": pages,
        "pub_types": pub_types,
        "section": section,
        "pubmed_url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else "",
        "doi_url": f"https://doi.org/{doi}" if doi else "",
    }


# Map PubMed publication types to a clean contents-section label. First match wins;
# "Journal Article" is the generic fallback so it only shows when nothing else fits.
_SECTION_PRIORITY = [
    ("Editorial", "Editorial"),
    ("Practice Guideline", "Guideline"),
    ("Guideline", "Guideline"),
    ("Systematic Review", "Systematic Review"),
    ("Meta-Analysis", "Meta-Analysis"),
    ("Randomized Controlled Trial", "Randomized Trial"),
    ("Clinical Trial", "Clinical Trial"),
    ("Review", "Review"),
    ("Case Reports", "Case Report"),
    ("Comment", "Comment"),
    ("Letter", "Letter"),
    ("Observational Study", "Observational Study"),
]


def _section_for(pub_types):
    types = set(pub_types)
    for needle, label in _SECTION_PRIORITY:
        if needle in types:
            return label
    return "Article"
