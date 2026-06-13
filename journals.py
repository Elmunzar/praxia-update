"""Subscribed-journal config: load / save / mutate config/journals.json.

config/journals.json is the single source of truth for which journals the daily
build fetches. Edit it in the app ("Add journal"), via manage_journals.py, or by hand.
Each entry: {key, name, ta} where `ta` is the exact PubMed [TA] abbreviation.
"""

import os
import re
import json

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(HERE, "config", "journals.json")


def load():
    """Return the list of journal dicts from config (order = display order)."""
    with open(CONFIG_PATH, encoding="utf-8") as f:
        data = json.load(f)
    return data.get("journals", [])


def save(journals):
    payload = {
        "_comment": ("Your subscribed journals — the daily build fetches each one. "
                     "Add by name in the app, or run: "
                     'python3 manage_journals.py --add "Journal name or URL". '
                     "'ta' must be the exact PubMed [TA] abbreviation."),
        "journals": journals,
    }
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")


def slugify(name):
    s = re.sub(r"[^a-z0-9]+", "_", (name or "").lower()).strip("_")
    return s[:32] or "journal"


def make_key(name, existing_keys):
    base = slugify(name)
    key, n = base, 2
    while key in existing_keys:
        key, n = f"{base}_{n}", n + 1
    return key


def add(journals, name, ta):
    """Append a journal (idempotent on TA). Returns (journals, added_bool, entry)."""
    for j in journals:
        if j["ta"].lower() == ta.lower():
            return journals, False, j  # already subscribed
    entry = {"key": make_key(name, {j["key"] for j in journals}),
             "name": name.strip(), "ta": ta.strip()}
    journals.append(entry)
    return journals, True, entry


def remove(journals, key_or_ta):
    kept = [j for j in journals
            if j["key"] != key_or_ta and j["ta"].lower() != key_or_ta.lower()]
    return kept, len(kept) != len(journals)
