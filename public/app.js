/* Praxia Update — front end (newsstand model).
   Home = your journals as cards (icon + edition + new count).
   Tap a journal → its contents (titles grouped by type, authors, pages, abstracts).
   Tap an article → its abstract. Plus journal management, search, share, calendar.
*/

const LS = {
  hidden: "praxia.hidden.v1",
  add: "praxia.pendingAdd.v1",
  remove: "praxia.pendingRemove.v1",
};
const EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/";

const $ = (id) => document.getElementById(id);
const els = {
  status: $("status"), content: $("content"), dateSelect: $("dateSelect"),
  search: $("search"), issueMeta: $("issueMeta"), pdfLink: $("pdfLink"),
  shareBtn: $("shareBtn"), downloadBtn: $("downloadBtn"),
  journalsBtn: $("journalsBtn"), journalsPanel: $("journalsPanel"),
  journalsGrid: $("journalsGrid"), allJournals: $("allJournals"), noneJournals: $("noneJournals"),
  journalSearch: $("journalSearch"), journalSearchBtn: $("journalSearchBtn"),
  journalResults: $("journalResults"),
  subsSync: $("subsSync"), copySubs: $("copySubs"), syncHelp: $("syncHelp"),
  subsHelp: $("subsHelp"), revertSubs: $("revertSubs"),
  calendarBtn: $("calendarBtn"), calendarModal: $("calendarModal"),
  calendarClose: $("calendarClose"), icsUrl: $("icsUrl"), copyIcs: $("copyIcs"),
  addCal: $("addCal"), addGcal: $("addGcal"), addOutlook: $("addOutlook"),
  emailInput: $("emailInput"), emailBtn: $("emailBtn"), emailMsg: $("emailMsg"),
};

// Set this to your Formspree form id (e.g. "xeoqkabc") to enable in-app email sign-up.
// Until then the email field shows a "not enabled yet" note. Calendar works regardless.
const FORMSPREE_ID = "";

const state = {
  baseUrl: "", index: [], issue: null, query: "",
  servedSubs: [],
  hidden: lsGet(LS.hidden, []),
  pendingAdd: lsGet(LS.add, []),
  pendingRemove: lsGet(LS.remove, []),
  view: "newsstand",   // 'newsstand' | 'journal'
  openKey: null,       // journal key when view === 'journal'
};

function lsGet(k, fallback) { try { return JSON.parse(localStorage.getItem(k)) ?? fallback; } catch { return fallback; } }
function lsSet(k, v) { localStorage.setItem(k, JSON.stringify(v)); }
const esc = (s) => (s || "").replace(/[&<>"']/g, c =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const norm = (s) => (s || "").toLowerCase().replace(/[^a-z0-9 ]/g, " ").replace(/\s+/g, " ").trim();
function prettyDate(iso) {
  return new Date(iso + "T00:00:00").toLocaleDateString(undefined,
    { weekday: "long", day: "numeric", month: "long", year: "numeric" });
}

/* ---------- journal identity (monogram + accent), mirrors the PDF/iOS ---------- */
const PALETTE = ["#13264A", "#2F6F62", "#9C6B2E", "#6E5BA6", "#A6453A",
                 "#2C6B8F", "#5B7553", "#8A5A83", "#3F6C3A", "#9A7B2E", "#445A7A"];
const STOP = new Set(["the", "of", "and", "for", "in", "a", "an"]);
function journalAccent(key) {
  let h = 0; for (const c of (key || "x")) h += c.charCodeAt(0);
  return PALETTE[h % PALETTE.length];
}
function journalInitials(name) {
  const words = (name || "").split(/[^A-Za-z]+/).filter(w => w && !STOP.has(w.toLowerCase()));
  let s = words.map(w => (w === w.toUpperCase() && w.length > 1) ? w : w[0].toUpperCase()).join("");
  return (s || (name || "?").slice(0, 2).toUpperCase()).slice(0, 4);
}
const MONTHS = { "01": "January", "02": "February", "03": "March", "04": "April", "05": "May",
  "06": "June", "07": "July", "08": "August", "09": "September", "10": "October",
  "11": "November", "12": "December", jan: "January", feb: "February", mar: "March",
  apr: "April", may: "May", jun: "June", jul: "July", aug: "August", sep: "September",
  oct: "October", nov: "November", dec: "December" };
function monthName(m) {
  if (!m) return "";
  return MONTHS[m.toLowerCase().slice(0, 3)] || MONTHS[m] || m;
}
/** Journal badge: a logo from journal-icons/<key>.png if present, else the monogram tile. */
function badgeHtml(g, accent) {
  return `<span class="jcard-badge" style="background:${accent}">${esc(journalInitials(g.journal))}` +
    `<img class="jbadge-img" alt="" loading="lazy" src="journal-icons/${esc(g.key)}.png" ` +
    `onload="this.parentNode.classList.add('has-img')" onerror="this.remove()"></span>`;
}

/** "Volume 108, Issue 6 · June 2026" derived from a group's articles. */
function editionLabel(group) {
  const arts = group.articles || [];
  const vols = [...new Set(arts.map(a => a.volume).filter(Boolean))];
  const issues = [...new Set(arts.map(a => a.issue).filter(Boolean))];
  const bits = [];
  if (vols.length === 1) {
    let seg = `Volume ${vols[0]}`;
    if (issues.length === 1) seg += `, Issue ${issues[0]}`;
    bits.push(seg);
  }
  const yms = arts.filter(a => a.pub_year).map(a => [monthName(a.pub_month), a.pub_year].filter(Boolean).join(" "));
  if (yms.length) {
    const counts = {};
    yms.forEach(y => (counts[y] = (counts[y] || 0) + 1));
    bits.push(Object.entries(counts).sort((a, b) => b[1] - a[1])[0][0]);
  }
  if (!vols.length) bits.push("online ahead of print");
  return bits.join(" · ");
}

/* ---------- effective subscription list ---------- */
function effectiveSubs() {
  const removed = new Set(state.pendingRemove);
  const servedTAs = new Set(state.servedSubs.map(j => j.ta.toLowerCase()));
  const kept = state.servedSubs.filter(j => !removed.has(j.key));
  const added = state.pendingAdd.filter(p => !servedTAs.has(p.ta.toLowerCase()));
  return [...kept, ...added];
}
function hasPending() { return state.pendingAdd.length || state.pendingRemove.length; }
function healPending() {
  const servedTAs = new Set(state.servedSubs.map(j => j.ta.toLowerCase()));
  const servedKeys = new Set(state.servedSubs.map(j => j.key));
  state.pendingAdd = state.pendingAdd.filter(p => !servedTAs.has(p.ta.toLowerCase()));
  state.pendingRemove = state.pendingRemove.filter(k => servedKeys.has(k));
  lsSet(LS.add, state.pendingAdd); lsSet(LS.remove, state.pendingRemove);
}

async function init() {
  const idx = await fetch("issues/index.json", { cache: "no-store" }).then(r => r.json()).catch(() => null);
  if (idx) { state.baseUrl = idx.base_url || location.origin; state.index = idx.issues || []; }
  const subsDoc = await fetch("subscriptions.json", { cache: "no-store" }).then(r => r.json()).catch(() => null);
  state.servedSubs = subsDoc?.journals || [];
  if (!state.baseUrl) state.baseUrl = subsDoc?.base_url || location.origin;
  healPending();

  if (!state.index.length) {
    const latest = await fetch("issues/latest.json", { cache: "no-store" }).then(r => r.json()).catch(() => null);
    if (!latest) { els.status.textContent = "No issues yet. The first daily build will appear here."; setupStaticUI(); return; }
    state.index = [{ date: latest.date, count: latest.counts.articles }];
  }

  els.dateSelect.innerHTML = state.index.map(e =>
    `<option value="${e.date}">${prettyDate(e.date)} — ${e.count} article${e.count !== 1 ? "s" : ""}</option>`).join("");
  const wanted = new URLSearchParams(location.search).get("date");
  const start = state.index.find(e => e.date === wanted)?.date || state.index[0].date;
  els.dateSelect.value = start;

  bindEvents();
  setupStaticUI();
  await loadIssue(start);
}

function setupStaticUI() { setupCalendarModal(); setupDigestEmail(); setupShareDownload(); renderJournalPicker(); updateSyncBanner(); }

async function loadIssue(date) {
  els.content.innerHTML = `<p class="status">Loading ${prettyDate(date)}…</p>`;
  state.issue = await fetch(`issues/${date}.json`, { cache: "no-store" }).then(r => r.json()).catch(() => null);
  state.view = "newsstand"; state.openKey = null; state.query = ""; els.search.value = "";
  if (!state.issue) { els.content.innerHTML = `<p class="status">Couldn't load ${prettyDate(date)}.</p>`; return; }
  els.pdfLink.href = `issues/${date}.pdf`;
  renderJournalPicker();
  render();
}

/* ---------- data helpers ---------- */
function visibleGroups() {
  const subscribed = new Set(effectiveSubs().map(j => j.key));
  const hidden = new Set(state.hidden);
  return (state.issue?.groups || []).filter(g => subscribed.has(g.key) && !hidden.has(g.key));
}
function matchesQuery(a, terms) {
  if (!terms.length) return true;
  const hay = (a.title + " " + (a.authors || []).join(" ") + " " + a.abstract).toLowerCase();
  return terms.every(t => hay.includes(t));
}

/* ---------- render dispatch ---------- */
function render() {
  if (!state.issue) return;
  if (state.view === "journal" && state.openKey) renderJournalContents();
  else renderNewsstand();
}

function setMeta(html) { els.issueMeta.innerHTML = html; }

/* ---------- newsstand ---------- */
function renderNewsstand() {
  const groups = visibleGroups();
  const live = groups.filter(g => g.count > 0).length;
  const fresh = groups.filter(g => g.is_new).length;
  setMeta(`<strong>${live} journal${live !== 1 ? "s" : ""}</strong><br>${fresh ? `${fresh} new issue${fresh !== 1 ? "s" : ""} · ` : ""}${prettyDate(state.issue.date)}`);

  const q = norm(state.query);
  const shown = q ? groups.filter(g => norm(g.journal).includes(q)) : groups;

  if (!groups.length) {
    els.content.innerHTML = `<div class="empty">No journals selected. Tap <strong>Journals</strong> to add or show some.</div>`;
    return;
  }
  const withNew = shown.filter(g => g.count > 0);
  const noNew = shown.filter(g => g.count === 0);

  const card = (g) => {
    const accent = journalAccent(g.key);
    const clickable = g.count > 0;
    return `<button class="jcard ${clickable ? "" : "is-empty"}" ${clickable ? `data-open="${g.key}"` : "disabled"}>
        ${badgeHtml(g, accent)}
        <span class="jcard-body">
          <span class="jcard-name">${esc(g.journal)}</span>
          <span class="jcard-edition">${clickable ? esc(editionLabel(g)) + (g.is_new ? " · new" : "") : "No current issue"}</span>
        </span>
        <span class="jcard-count" style="--a:${accent}">${g.count || "—"}</span>
      </button>`;
  };

  els.content.innerHTML =
    `<p class="summary-line">Your journals — ${prettyDate(state.issue.date)}</p>
     <div class="newsstand">${withNew.map(card).join("")}</div>
     ${noNew.length ? `<p class="muted nostand-sep">No current issue</p><div class="newsstand dim">${noNew.map(card).join("")}</div>` : ""}
     ${q && !shown.length ? `<div class="empty">No journals match “${esc(state.query)}”.</div>` : ""}`;

  els.content.querySelectorAll(".jcard[data-open]").forEach(b =>
    b.addEventListener("click", () => { state.openKey = b.dataset.open; state.view = "journal"; state.query = ""; els.search.value = ""; window.scrollTo(0, 0); render(); }));
}

/* ---------- one journal's contents (table of contents) ---------- */
function renderJournalContents() {
  const g = visibleGroups().find(x => x.key === state.openKey);
  if (!g) { state.view = "newsstand"; return renderNewsstand(); }
  const accent = journalAccent(g.key);
  setMeta(`<strong>${esc(g.journal)}</strong><br>${esc(editionLabel(g))}`);

  const terms = norm(state.query).split(" ").filter(Boolean);
  const arts = g.articles.filter(a => matchesQuery(a, terms));

  // Group by section, preserving first-appearance order.
  const order = [], bySec = {};
  arts.forEach(a => { const s = a.section || "Article"; if (!bySec[s]) { bySec[s] = []; order.push(s); } bySec[s].push(a); });

  const head = `<div class="toc-head">
      <button class="back" id="backBtn">‹ Journals</button>
      <div class="toc-title">${badgeHtml(g, accent)}
        <span><span class="toc-journal">${esc(g.journal)}</span><span class="toc-edition">${esc(editionLabel(g))} · ${g.count} article${g.count !== 1 ? "s" : ""}</span></span>
      </div>
    </div>`;

  const body = !arts.length
    ? `<div class="empty">${state.query ? `No articles match “${esc(state.query)}”.` : "No articles."}</div>`
    : order.map(sec => `
        <section class="toc-section">
          <h3 class="toc-section-label">${esc(sec)}</h3>
          ${bySec[sec].map(articleRow).join("")}
        </section>`).join("");

  els.content.innerHTML = head + body;
  $("backBtn").addEventListener("click", () => { state.view = "newsstand"; state.openKey = null; state.query = ""; els.search.value = ""; window.scrollTo(0, 0); render(); });
  els.content.querySelectorAll(".article h4 button").forEach(btn =>
    btn.addEventListener("click", () => { const ab = btn.closest(".article").querySelector(".abstract"); if (ab) ab.hidden = !ab.hidden; }));
}

function articleRow(a) {
  const authors = (a.authors || []).slice(0, 12).join(", ") + ((a.authors || []).length > 12 ? " et al." : "");
  const links = [];
  if (a.pubmed_url) links.push(`<a href="${a.pubmed_url}" target="_blank" rel="noopener">PubMed</a>`);
  if (a.doi_url) links.push(`<a href="${a.doi_url}" target="_blank" rel="noopener">DOI</a>`);
  return `<article class="article">
      <h4><button type="button">${esc(a.title)}</button></h4>
      ${authors ? `<p class="authors">${esc(authors)}</p>` : ""}
      <p class="meta-line">${a.pages ? `Pages ${esc(a.pages)}` : ""}${a.pages && links.length ? ` &nbsp;·&nbsp; ` : ""}${links.join(" &nbsp;·&nbsp; ")}</p>
      ${a.abstract ? `<div class="abstract" hidden>${esc(a.abstract)}</div>` : ""}
    </article>`;
}

/* ---------- journal picker (add / show-hide) ---------- */
function renderJournalPicker() {
  const subs = effectiveSubs();
  const counts = {};
  (state.issue?.groups || []).forEach(g => { counts[g.key] = g.count; });
  const hidden = new Set(state.hidden);
  els.journalsGrid.innerHTML = subs.map(j => {
    const inIssue = j.key in counts;
    const tag = inIssue ? `(${counts[j.key]})` : `<span class="pending-tag">pending</span>`;
    const on = !hidden.has(j.key);
    return `<label class="journal-row">
      <input type="checkbox" data-key="${j.key}" ${on ? "checked" : ""}>
      <span class="jrow-name">${esc(j.name)} <span class="toggle-hint">${tag}</span></span>
      <button class="jrow-remove" data-remove="${j.key}" title="Unsubscribe">×</button>
    </label>`;
  }).join("") || `<p class="muted">No journals yet — add one above.</p>`;
  els.journalsGrid.querySelectorAll('input[type="checkbox"]').forEach(cb =>
    cb.addEventListener("change", () => {
      const h = new Set(state.hidden);
      cb.checked ? h.delete(cb.dataset.key) : h.add(cb.dataset.key);
      state.hidden = [...h]; lsSet(LS.hidden, state.hidden);
      if (state.openKey && h.has(state.openKey)) { state.view = "newsstand"; state.openKey = null; }
      render();
    }));
  els.journalsGrid.querySelectorAll(".jrow-remove").forEach(b =>
    b.addEventListener("click", e => { e.preventDefault(); removeJournal(b.dataset.remove); }));
}

/* ---------- add a journal (NLM Catalog, client-side) ---------- */
function cleanQuery(text) {
  text = (text || "").trim();
  if (/^(https?:\/\/|www\.)/i.test(text)) {
    try {
      const u = new URL(text.includes("//") ? text : "//" + text, "http://x");
      let label = (u.hostname || "").replace(/^www\./, "").split(".")[0];
      if (label.startsWith("the") && label.length > 5) label = label.slice(3);
      const path = (u.pathname || "").split(/[\/._-]+/).filter(w => w.length > 2 && !/^\d+$/.test(w));
      text = [label, ...path].join(" ");
    } catch { /* */ }
  }
  return text.replace(/[^A-Za-z0-9 ]+/g, " ").replace(/\s+/g, " ").trim();
}
async function searchJournals(query) {
  const q = cleanQuery(query); if (!q) return [];
  const term = `(${q}[Title] OR ${q}[Title Abbreviation]) AND currentlyindexed[All]`;
  const es = await fetch(`${EUTILS}esearch.fcgi?db=nlmcatalog&retmode=json&retmax=16&term=${encodeURIComponent(term)}`).then(r => r.json());
  const ids = es.esearchresult?.idlist || []; if (!ids.length) return [];
  const su = await fetch(`${EUTILS}esummary.fcgi?db=nlmcatalog&retmode=json&id=${ids.join(",")}`).then(r => r.json());
  const qt = new Set(norm(q).split(" ")); const out = [];
  for (const uid of ids) {
    const rec = su.result?.[uid]; if (!rec) continue;
    const title = (rec.titlemainlist?.[0]?.title || "").replace(/[.\s]+$/, "");
    const ta = rec.medlineta || rec.isoabbreviation || ""; if (!ta) continue;
    const issn = (rec.issnlist || []).map(i => i.issn).filter(Boolean);
    const ts = new Set(norm(title).split(" "));
    const score = [...qt].filter(t => ts.has(t)).length + (norm(q) === norm(ta) ? 3 : 0) + (norm(q) === norm(title) ? 2 : 0);
    out.push({ name: title || ta, ta, issn, score });
  }
  return out.sort((a, b) => b.score - a.score).slice(0, 8);
}
async function runJournalSearch() {
  const q = els.journalSearch.value.trim(); if (!q) return;
  els.journalResults.innerHTML = `<p class="muted">Searching…</p>`;
  let results; try { results = await searchJournals(q); }
  catch { els.journalResults.innerHTML = `<p class="muted">Search failed — try again.</p>`; return; }
  if (!results.length) { els.journalResults.innerHTML = `<p class="muted">No currently-indexed journal matched “${esc(q)}”.</p>`; return; }
  const have = new Set(effectiveSubs().map(j => j.ta.toLowerCase()));
  els.journalResults.innerHTML = results.map(r => {
    const subbed = have.has(r.ta.toLowerCase());
    const issn = r.issn.length ? ` · ISSN ${esc(r.issn.join(", "))}` : "";
    return `<div class="jresult"><div><strong>${esc(r.name)}</strong><br><span class="muted">${esc(r.ta)}${issn}</span></div>
      <button class="btn ${subbed ? "" : "btn-accent"}" data-ta="${esc(r.ta)}" data-name="${esc(r.name)}" ${subbed ? "disabled" : ""}>${subbed ? "Added" : "Add"}</button></div>`;
  }).join("");
  els.journalResults.querySelectorAll("button[data-ta]").forEach(b =>
    b.addEventListener("click", () => addJournal(b.dataset.name, b.dataset.ta)));
}
function slugify(name) { return (name.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "").slice(0, 32)) || "journal"; }
function addJournal(name, ta) {
  if (effectiveSubs().some(j => j.ta.toLowerCase() === ta.toLowerCase())) return;
  const served = state.servedSubs.find(j => j.ta.toLowerCase() === ta.toLowerCase());
  if (served) { state.pendingRemove = state.pendingRemove.filter(k => k !== served.key); lsSet(LS.remove, state.pendingRemove); }
  else {
    const keys = new Set([...state.servedSubs, ...state.pendingAdd].map(j => j.key));
    let key = slugify(name), n = 2; while (keys.has(key)) key = `${slugify(name)}_${n++}`;
    state.pendingAdd.push({ key, name, ta }); lsSet(LS.add, state.pendingAdd);
  }
  renderJournalPicker(); updateSyncBanner(); runJournalSearch();
}
function removeJournal(key) {
  const pa = state.pendingAdd.find(j => j.key === key);
  if (pa) { state.pendingAdd = state.pendingAdd.filter(j => j.key !== key); lsSet(LS.add, state.pendingAdd); }
  else if (!state.pendingRemove.includes(key)) { state.pendingRemove.push(key); lsSet(LS.remove, state.pendingRemove); }
  state.hidden = state.hidden.filter(k => k !== key); lsSet(LS.hidden, state.hidden);
  if (state.openKey === key) { state.view = "newsstand"; state.openKey = null; }
  renderJournalPicker(); updateSyncBanner(); render();
}

/* ---------- sync banner ---------- */
function updateSyncBanner() {
  if (!hasPending()) { els.subsSync.hidden = true; return; }
  els.subsSync.hidden = false;
  const journals = effectiveSubs().map(({ key, name, ta }) => ({ key, name, ta }));
  const file = JSON.stringify({ journals }, null, 2);
  els.subsHelp.textContent =
    "1) Open config/journals.json in your repo.\n2) Replace its contents with the copied text.\n" +
    "3) Commit — the next daily build fetches your updated journals.\n\n— config/journals.json —\n" + file;
  els.copySubs.dataset.payload = file;
}

/* ---------- share / download the day's PDF ---------- */
async function currentPdf() {
  const date = els.dateSelect.value || state.issue?.date;
  const blob = await fetch(`issues/${date}.pdf`, { cache: "no-store" }).then(r => { if (!r.ok) throw new Error("pdf"); return r.blob(); });
  return { date, blob, file: new File([blob], `Praxia-Update-${date}.pdf`, { type: "application/pdf" }) };
}
function setupShareDownload() {
  let canShareFiles = false;
  try { canShareFiles = !!navigator.canShare && navigator.canShare({ files: [new File([new Blob()], "x.pdf", { type: "application/pdf" })] }); } catch { }
  els.shareBtn.hidden = !canShareFiles;
  els.shareBtn.addEventListener("click", async () => {
    els.shareBtn.disabled = true;
    try { const { date, file } = await currentPdf(); await navigator.share({ files: [file], title: `Praxia Update — ${prettyDate(date)}`, text: "Today's orthopaedic literature digest" }); }
    catch (e) { if (e && e.name !== "AbortError") downloadPdf(); } finally { els.shareBtn.disabled = false; }
  });
  els.downloadBtn.addEventListener("click", downloadPdf);
}
async function downloadPdf() {
  try {
    const { date, blob } = await currentPdf();
    const url = URL.createObjectURL(blob); const a = document.createElement("a");
    a.href = url; a.download = `Praxia-Update-${date}.pdf`; document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 4000);
  } catch { window.open(els.pdfLink.href, "_blank"); }
}

/* ---------- events + modals ---------- */
function bindEvents() {
  els.dateSelect.addEventListener("change", e => {
    const url = new URL(location); url.searchParams.set("date", e.target.value);
    history.replaceState(null, "", url); loadIssue(e.target.value);
  });
  els.search.addEventListener("input", e => { state.query = e.target.value.trim(); render(); });
  els.journalsBtn.addEventListener("click", () => {
    const open = els.journalsPanel.hidden; els.journalsPanel.hidden = !open;
    els.journalsBtn.setAttribute("aria-expanded", String(open));
  });
  els.allJournals.addEventListener("click", () => { state.hidden = []; lsSet(LS.hidden, []); renderJournalPicker(); render(); });
  els.noneJournals.addEventListener("click", () => { state.hidden = effectiveSubs().map(j => j.key); lsSet(LS.hidden, state.hidden); renderJournalPicker(); render(); });
  els.journalSearchBtn.addEventListener("click", runJournalSearch);
  els.journalSearch.addEventListener("keydown", e => { if (e.key === "Enter") { e.preventDefault(); runJournalSearch(); } });
  els.copySubs.addEventListener("click", async () => {
    try { await navigator.clipboard.writeText(els.copySubs.dataset.payload || ""); els.copySubs.textContent = "Copied"; }
    catch { els.subsHelp.hidden = false; }
    setTimeout(() => (els.copySubs.textContent = "Copy subscription file"), 1500);
  });
  els.syncHelp.addEventListener("click", () => { els.subsHelp.hidden = !els.subsHelp.hidden; });
  els.revertSubs.addEventListener("click", () => { state.pendingAdd = []; state.pendingRemove = []; lsSet(LS.add, []); lsSet(LS.remove, []); renderJournalPicker(); updateSyncBanner(); render(); });
}
function setupCalendarModal() {
  const base = state.baseUrl.replace(/\/$/, "");
  const icsUrl = `${base}/issues/calendar.ics`;
  const icsWebcal = icsUrl.replace(/^https?:/, "webcal:");
  els.icsUrl.value = icsUrl;
  if (els.addCal) els.addCal.href = icsWebcal;   // one-tap subscribe (Apple / default calendar)
  if (els.addGcal) els.addGcal.href = "https://calendar.google.com/calendar/r?cid=" + encodeURIComponent(icsWebcal);
  if (els.addOutlook) els.addOutlook.href =
    "https://outlook.live.com/calendar/0/addfromweb?url=" + encodeURIComponent(icsUrl) + "&name=" + encodeURIComponent("Praxia Update");
  const open = () => (els.calendarModal.hidden = false), close = () => (els.calendarModal.hidden = true);
  els.calendarBtn.addEventListener("click", open);
  els.calendarClose.addEventListener("click", close);
  els.calendarModal.addEventListener("click", e => { if (e.target === els.calendarModal) close(); });
  els.copyIcs.addEventListener("click", async () => {
    try { await navigator.clipboard.writeText(icsUrl); els.copyIcs.textContent = "Copied"; } catch { els.icsUrl.select(); }
    setTimeout(() => (els.copyIcs.textContent = "Copy"), 1500);
  });
}

function setupDigestEmail() {
  if (!els.emailBtn) return;
  if (!FORMSPREE_ID) {
    els.emailMsg.textContent = "Email sign-up isn't switched on yet.";
    els.emailInput.disabled = true; els.emailBtn.disabled = true;
    return;
  }
  els.emailBtn.addEventListener("click", async () => {
    const email = (els.emailInput.value || "").trim();
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) { els.emailMsg.textContent = "Enter a valid email address."; return; }
    els.emailBtn.disabled = true; els.emailMsg.textContent = "Signing you up…";
    try {
      const r = await fetch(`https://formspree.io/f/${FORMSPREE_ID}`, {
        method: "POST",
        headers: { "Accept": "application/json", "Content-Type": "application/json" },
        body: JSON.stringify({ email, _subject: "Praxia Update — email sign-up" }),
      });
      if (r.ok) { els.emailMsg.textContent = "You're in — the digest arrives each morning."; els.emailInput.value = ""; }
      else { els.emailMsg.textContent = "Sign-up failed — please try again."; }
    } catch { els.emailMsg.textContent = "Sign-up failed — check your connection."; }
    finally { els.emailBtn.disabled = false; }
  });
}

init();
