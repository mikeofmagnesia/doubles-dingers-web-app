#!/usr/bin/env python3
"""
Convert Doubles & Dingers historical CSVs to archive JSON format.

Usage:
    python3 scripts/import-archive.py

Expects CSVs in ~/Downloads/ named:
    "Copy of Doubles & Dingers YEAR - Players.csv"
    "Copy of Doubles & Dingers YEAR - Standings.csv"

Outputs:
    docs/data/archive/YEAR/players.json
    docs/data/archive/YEAR/teams.json
    docs/data/archive/index.json  (updated)
"""

import csv
import json
import os
from pathlib import Path

DOWNLOADS = Path.home() / "Downloads"
ARCHIVE   = Path(__file__).parent.parent / "docs" / "data" / "archive"

YEARS = [2021, 2022, 2023, 2024]

# Normalize group labels to A / B / C / Wildcard
GROUP_MAP = {
    "1": "A", "2": "B", "3": "C",
    "A": "A", "B": "B", "C": "C",
    "W": "Wildcard", "WC": "Wildcard", "Wildcard": "Wildcard",
}


def load_csv(path):
    with open(path, newline="", encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


def parse_num(val, cast=int):
    """Return cast(val) or None if blank/missing."""
    if val is None or str(val).strip() == "":
        return None
    try:
        return cast(str(val).strip())
    except (ValueError, TypeError):
        return None


def assign_ranks(items, key="total"):
    """Assign integer ranks with ties (same rank for equal totals)."""
    items.sort(key=lambda x: x[key], reverse=True)
    rank = 1
    for i, item in enumerate(items):
        if i > 0 and item[key] == items[i - 1][key]:
            item["rank"] = items[i - 1]["rank"]
        else:
            item["rank"] = rank
        rank = i + 2
    return items


def process_players(year):
    path = DOWNLOADS / f"Copy of Doubles & Dingers {year} - Players.csv"
    rows = load_csv(path)

    players = []
    for r in rows:
        group_raw = r.get("Group", "").strip()
        group     = GROUP_MAP.get(group_raw, group_raw)

        # Column names vary slightly across years
        homers  = parse_num(r.get("HRs") or r.get("HR") or r.get("Homers"))
        doubles = parse_num(r.get("2Bs") or r.get("2B") or r.get("Doubles"))
        total   = parse_num(r.get("Total"))
        games   = parse_num(r.get("Games") or r.get("G") or r.get("Games Played"))

        per_game_raw = r.get("HRs & 2Bs per Game") or r.get("Per Game") or r.get("(2B+HR)/GP")
        per_game = parse_num(per_game_raw, float)

        # Recompute per_game from games if both present and per_game missing
        if per_game is None and games and total:
            per_game = round(total / games, 3)

        players.append({
            "rank":          parse_num(r.get("Place") or r.get("Rank") or r.get("#")),
            "name":          r.get("Player", "").strip(),
            "mlb_team":      r.get("Team", "").strip(),
            "group":         group,
            "times_drafted": parse_num(r.get("Times Drafted") or r.get("Drafted")),
            "total":         total,
            "doubles":       doubles,
            "homers":        homers,
            "games":         games,
            "per_game":      per_game,
        })

    # Re-rank by total (source data may have ties handled differently)
    assign_ranks(players)
    return players


def process_teams(year):
    path = DOWNLOADS / f"Copy of Doubles & Dingers {year} - Standings.csv"
    rows = load_csv(path)

    teams = []
    for r in rows:
        homers  = parse_num(r.get("HRs") or r.get("HR"))
        doubles = parse_num(r.get("2Bs") or r.get("2B"))
        total   = parse_num(r.get("Total"))

        teams.append({
            "rank":      parse_num(r.get("Place") or r.get("Rank") or r.get("#")),
            "team_name": r.get("Team", "").strip(),
            "total":     total,
            "doubles":   doubles,
            "homers":    homers,
        })

    assign_ranks(teams)
    return teams


def main():
    ARCHIVE.mkdir(parents=True, exist_ok=True)
    processed = []

    for year in YEARS:
        players_path = DOWNLOADS / f"Copy of Doubles & Dingers {year} - Players.csv"
        teams_path   = DOWNLOADS / f"Copy of Doubles & Dingers {year} - Standings.csv"

        if not players_path.exists():
            print(f"  SKIP {year}: missing {players_path.name}")
            continue
        if not teams_path.exists():
            print(f"  SKIP {year}: missing {teams_path.name}")
            continue

        year_dir = ARCHIVE / str(year)
        year_dir.mkdir(exist_ok=True)

        players = process_players(year)
        teams   = process_teams(year)

        players_out = year_dir / "players.json"
        teams_out   = year_dir / "teams.json"

        with open(players_out, "w") as fh:
            json.dump({"season": year, "players": players}, fh, indent=2)

        with open(teams_out, "w") as fh:
            json.dump({"season": year, "teams": teams}, fh, indent=2)

        print(f"  {year}: {len(players)} players, {len(teams)} teams → {year_dir}")
        processed.append(year)

    # Update index.json with all processed + existing seasons
    index_path = ARCHIVE / "index.json"
    existing = []
    if index_path.exists():
        with open(index_path) as fh:
            existing = json.load(fh).get("seasons", [])

    all_seasons = sorted(set(existing + processed), reverse=True)
    with open(index_path, "w") as fh:
        json.dump({"seasons": all_seasons}, fh, indent=2)

    print(f"\nindex.json updated: {all_seasons}")


if __name__ == "__main__":
    main()
