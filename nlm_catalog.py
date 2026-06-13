"""Resolve a free-text journal name (or URL) to PubMed journal candidates.

Uses the NLM Catalog E-utilities, restricted to currently-indexed journals, and
ranks candidates by token overlap with the query. Returns a list of:
    {name, ta, nlm_id, issn[]}  best match first.

The exact same logic runs client-side in the app (eutils allows CORS); this module
backs the manage_journals.py CLI and any server-side resolution.
"""

import re
import json
import urllib.parse
import urllib.request

BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"


def _get(endpoint, params):
    url = BASE + endpoint + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "praxia-update"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def _norm(s):
    return set(re.sub(r"[^a-z0-9 ]", " ", (s or "").lower()).split())


def _clean_query(text):
    """Accept a raw name, a PubMed/DOI URL, or a journal homepage URL.

    For URLs we strip the scheme/host and use the readable remainder as search text;
    a bare journal name passes through unchanged. The result is then reduced to
    PubMed-safe tokens (letters/digits/spaces) so characters like '&' or ':' that
    break the E-utilities query syntax are dropped.
    """
    text = (text or "").strip()
    if text.startswith(("http://", "https://", "www.")):
        parsed = urllib.parse.urlparse(text if "//" in text else "//" + text)
        host = parsed.netloc.replace("www.", "")
        label = host.split(".")[0]
        if label.startswith("the") and len(label) > 5:  # "thelancet" -> "lancet"
            label = label[3:]
        words = [label] + re.split(r"[./_-]+", parsed.path)
        text = " ".join(w for w in words if len(w) > 2 and not w.isdigit())
    # Reduce to PubMed-safe tokens: '&', ',', ':' etc. break the term syntax.
    text = re.sub(r"[^A-Za-z0-9 ]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def search(query, limit=8):
    q = _clean_query(query)
    if not q:
        return []
    term = f"({q}[Title] OR {q}[Title Abbreviation]) AND currentlyindexed[All]"
    try:
        res = _get("esearch.fcgi", {"db": "nlmcatalog", "retmode": "json",
                                    "retmax": str(limit * 2), "term": term})
        ids = res["esearchresult"].get("idlist", [])
    except Exception:  # noqa: BLE001
        ids = []
    if not ids:
        return []

    summ = _get("esummary.fcgi", {"db": "nlmcatalog", "retmode": "json", "id": ",".join(ids)})
    qtokens = _norm(q)
    out = []
    for uid in ids:
        rec = summ["result"].get(uid)
        if not rec:
            continue
        title = (rec.get("titlemainlist") or [{}])[0].get("title", "").rstrip(". ")
        ta = rec.get("medlineta", "") or rec.get("isoabbreviation", "")
        if not ta:
            continue
        issns = [i.get("issn", "") for i in (rec.get("issnlist") or []) if i.get("issn")]
        overlap = len(qtokens & _norm(title))
        score = overlap + (3 if _norm(q) == _norm(ta) else 0) + (2 if _norm(q) == _norm(title) else 0)
        out.append({"name": title or ta, "ta": ta, "nlm_id": uid, "issn": issns, "_score": score})

    out.sort(key=lambda r: r["_score"], reverse=True)
    for r in out:
        r.pop("_score", None)
    return out[:limit]
