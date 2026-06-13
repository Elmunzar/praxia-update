#!/usr/bin/env python3
"""Manage your subscribed journals (config/journals.json).

  python3 manage_journals.py --list
  python3 manage_journals.py --search "foot ankle international"
  python3 manage_journals.py --add "Foot & Ankle International"
  python3 manage_journals.py --add "https://www.thelancet.com"
  python3 manage_journals.py --add-ta "Foot Ankle Int" --name "Foot & Ankle International"
  python3 manage_journals.py --remove foot_ankle_international

--add resolves the name/URL via the NLM Catalog. If several journals match it lists
them and asks you to re-run with --add-ta "<exact TA>" to disambiguate.
"""

import sys
import argparse

import journals
import nlm_catalog


def cmd_list():
    js = journals.load()
    print(f"{len(js)} subscribed journal(s):\n")
    for j in js:
        print(f"  {j['key']:<22} {j['ta']:<32} {j['name']}")


def cmd_search(query):
    cands = nlm_catalog.search(query)
    if not cands:
        print(f"No currently-indexed journal matched: {query!r}")
        return
    print(f"Matches for {query!r}:\n")
    for c in cands:
        issn = (" · ISSN " + ", ".join(c["issn"])) if c["issn"] else ""
        print(f"  TA: {c['ta']:<34} {c['name']}{issn}")


def cmd_add(query, ta=None, name=None):
    js = journals.load()

    if ta:  # explicit TA path (disambiguation / scripting)
        chosen_ta, chosen_name = ta, (name or ta)
    else:
        cands = nlm_catalog.search(query)
        if not cands:
            print(f"No currently-indexed journal matched: {query!r}")
            sys.exit(1)
        if len(cands) > 1 and _ambiguous(cands):
            print(f"Several journals match {query!r} — re-run with the exact TA:\n")
            for c in cands:
                print(f'  --add-ta "{c["ta"]}" --name "{c["name"]}"')
            sys.exit(2)
        chosen_ta, chosen_name = cands[0]["ta"], (name or cands[0]["name"])

    js, added, entry = journals.add(js, chosen_name, chosen_ta)
    if not added:
        print(f"Already subscribed: {entry['name']} [{entry['ta']}]")
        return
    journals.save(js)
    print(f"Added: {entry['name']} [{entry['ta']}] (key: {entry['key']})")
    print("Run the daily build to fetch it: python3 build_issue.py")


def _ambiguous(cands):
    # Treat as ambiguous when the top two are close (no clear exact-TA winner).
    return not (len(cands) == 1 or cands[0].get("ta"))


def cmd_remove(key_or_ta):
    js = journals.load()
    js, removed = journals.remove(js, key_or_ta)
    if not removed:
        print(f"No subscribed journal matched: {key_or_ta!r}")
        sys.exit(1)
    journals.save(js)
    print(f"Removed: {key_or_ta}")


def main():
    p = argparse.ArgumentParser(description="Manage subscribed journals.")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--list", action="store_true")
    g.add_argument("--search", metavar="QUERY")
    g.add_argument("--add", metavar="NAME_OR_URL")
    g.add_argument("--remove", metavar="KEY_OR_TA")
    p.add_argument("--add-ta", metavar="TA", help="Exact PubMed [TA] (with --add for disambiguation).")
    p.add_argument("--name", metavar="NAME", help="Display name to store (with --add-ta).")
    args = p.parse_args()

    if args.list:
        cmd_list()
    elif args.search:
        cmd_search(args.search)
    elif args.remove:
        cmd_remove(args.remove)
    elif args.add or args.add_ta:
        cmd_add(args.add, ta=args.add_ta, name=args.name)


if __name__ == "__main__":
    main()
