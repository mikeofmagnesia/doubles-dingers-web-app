"""
Import team entries from the Google Form response CSV into data/teams.json.

Usage:
  1. Open the linked Google Sheet (Doubles and Dingers Responses)
  2. File > Download > Comma-separated values (.csv)
  3. Save the file as  scripts/responses.csv
  4. Run:  python scripts/import-teams.py

The script matches player names to Baseball Reference IDs using
docs/data/players_list.json and appends valid new teams to data/teams.json.

After importing, run  python src/main.py  to fetch fresh stats, then
commit and push both data/teams.json and the updated docs/data/ files.
"""

import csv
import json
import sys
from difflib import get_close_matches
from pathlib import Path

ROOT         = Path(__file__).parent.parent
TEAMS_FILE   = ROOT / "data" / "teams.json"
PLAYERS_FILE = ROOT / "docs" / "data" / "players_list.json"
CSV_FILE     = Path(__file__).parent / "responses.csv"

# ── Column names as they appear in the Google Sheet export ────────────────────
# If you rename your form questions, update these to match.
COL_TIMESTAMP = "Timestamp"
COL_NAME      = "Your Name"
COL_TEAM      = "Team Name"
COL_GROUP_A   = "Group A \u2014 Pick One"
COL_GROUP_B   = "Group B \u2014 Pick One"
COL_GROUP_C   = "Group C \u2014 Pick One"
COL_WC        = ["Wildcard 1", "Wildcard 2", "Wildcard 3", "Wildcard 4"]


def build_name_lookup(players: list[dict]) -> dict[str, dict]:
    """Case-insensitive name -> player record."""
    return {p["name"].lower(): p for p in players}


def resolve_wildcard(raw_name: str, name_lookup: dict, group_ids: set) -> dict | None:
    """Fuzzy-match a typed name to a player record, excluding group players."""
    name = raw_name.strip()
    key  = name.lower()

    # Exact match first
    if key in name_lookup:
        p = name_lookup[key]
        if p["br_id"] not in group_ids:
            return p
        print(f"    WARNING: '{name}' is a group-tier player and cannot be a wildcard.")
        return None

    # Fuzzy match (cutoff 0.80 catches minor typos)
    candidates = [k for k in name_lookup if name_lookup[k]["br_id"] not in group_ids]
    matches = get_close_matches(key, candidates, n=1, cutoff=0.80)
    if matches:
        p = name_lookup[matches[0]]
        print(f"    Fuzzy matched '{name}' -> '{p['name']}'")
        return p

    print(f"    WARNING: could not resolve wildcard '{name}'")
    return None


def main() -> None:
    if not CSV_FILE.exists():
        print(f"ERROR: {CSV_FILE} not found.")
        print("Download the Google Sheet responses as CSV and save to scripts/responses.csv")
        sys.exit(1)

    # Load existing config
    with open(TEAMS_FILE) as f:
        config = json.load(f)

    with open(PLAYERS_FILE) as f:
        players_list = json.load(f)["players"]

    name_lookup = build_name_lookup(players_list)

    group_ids = set(
        config["groups"]["A"] + config["groups"]["B"] + config["groups"]["C"]
    )

    # name -> br_id for group-tier players (for resolving group picks)
    group_name_to_id: dict[str, str] = {
        v["name"].lower(): k
        for k, v in config["players"].items()
        if v.get("group") in ("A", "B", "C")
    }

    existing_names = {t["team_name"].strip().lower() for t in config["teams"]}
    added: list[dict]  = []
    skipped: list[int] = []

    with open(CSV_FILE, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row_num, row in enumerate(reader, 1):
            owner     = row.get(COL_NAME, "").strip()
            team_name = row.get(COL_TEAM, "").strip()
            a_name    = row.get(COL_GROUP_A, "").strip()
            b_name    = row.get(COL_GROUP_B, "").strip()
            c_name    = row.get(COL_GROUP_C, "").strip()
            wc_names  = [row.get(col, "").strip() for col in COL_WC]

            print(f"\nRow {row_num}: {owner!r} / {team_name!r}")

            # ── Basic presence ──────────────────────────────────────────────
            if not owner or not team_name:
                print("  SKIP: missing owner or team name")
                skipped.append(row_num)
                continue

            if team_name.lower() in existing_names:
                print(f"  SKIP: team name already exists")
                skipped.append(row_num)
                continue

            # ── Resolve group picks ─────────────────────────────────────────
            a_id = group_name_to_id.get(a_name.lower())
            b_id = group_name_to_id.get(b_name.lower())
            c_id = group_name_to_id.get(c_name.lower())

            if not a_id:
                print(f"  SKIP: unrecognised Group A pick: '{a_name}'")
                skipped.append(row_num)
                continue
            if not b_id:
                print(f"  SKIP: unrecognised Group B pick: '{b_name}'")
                skipped.append(row_num)
                continue
            if not c_id:
                print(f"  SKIP: unrecognised Group C pick: '{c_name}'")
                skipped.append(row_num)
                continue

            # ── Resolve wildcard picks ──────────────────────────────────────
            wc_players = []
            for wc_name in wc_names:
                p = resolve_wildcard(wc_name, name_lookup, group_ids)
                if p:
                    wc_players.append(p)

            if len(wc_players) != 4:
                print(f"  SKIP: could not resolve all 4 wildcards (got {len(wc_players)})")
                skipped.append(row_num)
                continue

            # ── Duplicate check ─────────────────────────────────────────────
            all_ids = [a_id, b_id, c_id] + [p["br_id"] for p in wc_players]
            if len(set(all_ids)) != len(all_ids):
                print("  SKIP: duplicate players on team")
                skipped.append(row_num)
                continue

            # ── Add any new wildcard players to the players dict ────────────
            for p in wc_players:
                if p["br_id"] not in config["players"]:
                    letter = p["br_id"][0]
                    config["players"][p["br_id"]] = {
                        "name":   p["name"],
                        "group":  "Wildcard",
                        "mlb_id": p.get("mlb_id", 0),
                        "br_url": (
                            f"https://www.baseball-reference.com/players"
                            f"/{letter}/{p['br_id']}.shtml"
                        ),
                    }
                    print(f"  Added wildcard player: {p['name']}")

            team = {
                "owner":     owner,
                "team_name": team_name,
                "players":   all_ids,
            }
            config["teams"].append(team)
            existing_names.add(team_name.lower())
            added.append(team)
            print(f"  OK: {', '.join(all_ids)}")

    # ── Write updated config ────────────────────────────────────────────────
    if not added:
        print("\nNo new teams to add.")
        return

    with open(TEAMS_FILE, "w") as f:
        json.dump(config, f, indent=2)

    print(f"\n{'='*40}")
    print(f"Added {len(added)} team(s). Skipped {len(skipped)} row(s).")
    if skipped:
        print(f"Skipped rows: {skipped}")
    print(f"\nNext steps:")
    print(f"  1. python src/main.py        (fetch fresh stats)")
    print(f"  2. git add data/teams.json docs/data/")
    print(f"  3. git commit -m 'Import teams from submissions'")
    print(f"  4. git push")


if __name__ == "__main__":
    main()
