#!/usr/bin/env python3
"""
Build 2020 archive JSON from ~/Desktop/2020.csv + MLB Stats API.

Usage:
    python3 scripts/build_2020_archive.py

Outputs:
    docs/data/archive/2020/players.json
    docs/data/archive/2020/teams.json
    docs/data/archive/index.json  (updated)
"""

import csv
import json
import time
import urllib.request
import urllib.parse
from pathlib import Path

CSV_PATH  = Path.home() / "Desktop" / "2020.csv"
ARCHIVE   = Path(__file__).parent.parent / "docs" / "data" / "archive"
MLB_API   = "https://statsapi.mlb.com/api/v1"
SEASON    = 2020

# ---------------------------------------------------------------------------
# Name normalization: fix typos and trailing spaces from the CSV
# ---------------------------------------------------------------------------
NAME_FIXES = {
    "Freddy Freeman":     "Freddie Freeman",
    "Kyler Schwarber":    "Kyle Schwarber",
    "Nolan Areando":      "Nolan Arenado",
    "Eloy Jimmenez":      "Eloy Jimenez",
    "Matt Olsen":         "Matt Olson",
    "JD Martinez":        "J.D. Martinez",
    "Nick Castellanos":   "Nicholas Castellanos",  # normalize to one form
}

GROUP_MAP = {
    "A": "A", "B": "B", "C": "C",
    "WC": "Wildcard", "W": "Wildcard", "Wildcard": "Wildcard",
}

# Explicit MLB ID overrides for accented names that don't match via lookup
PLAYER_IDS: dict[str, int] = {
    "Eloy Jimenez":       650391,   # Eloy Jiménez
    "Eugenio Suarez":     553993,   # Eugenio Suárez
    "Javier Baez":        595879,   # Javier Báez
    "Jose Abreu":         547989,   # José Abreu
    "Jose Ramirez":       608070,   # José Ramírez
    "Luis Robert":        673357,   # Luis Robert Jr.
    "Miguel Sano":        593934,   # Miguel Sanó
    "Nicholas Castellanos": 592206, # Nick Castellanos
    "Renato Nunez":       600524,   # Renato Núñez
    "Ronald Acuna Jr.":   660670,   # Ronald Acuña Jr.
    "Yoan Moncada":       660162,   # Yoán Moncada
}


def fix_name(raw: str) -> str:
    name = raw.strip()
    return NAME_FIXES.get(name, name)


def mlb_get(path: str, params: dict = None) -> dict:
    url = f"{MLB_API}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=15) as resp:
        return json.loads(resp.read())


def build_roster_lookup(season: int) -> dict[str, int]:
    """Return {full_name: mlb_id} for all active MLB players in a season."""
    print(f"Fetching {season} MLB roster...")
    data = mlb_get("/sports/1/players", {"season": season, "sportId": 1})
    lookup = {}
    for p in data.get("people", []):
        lookup[p["fullName"]] = p["id"]
    print(f"  {len(lookup)} players in {season} roster")
    return lookup


def find_player_id(name: str, roster: dict[str, int]) -> int | None:
    """Try exact match, then case-insensitive, then first-token match."""
    if name in roster:
        return roster[name]
    lower = {k.lower(): v for k, v in roster.items()}
    if name.lower() in lower:
        return lower[name.lower()]
    # Last-name first-name swap attempt
    parts = name.split()
    if len(parts) >= 2:
        swapped = " ".join(parts[-1:] + parts[:-1])
        if swapped.lower() in lower:
            return lower[swapped.lower()]
    return None


def fetch_player_stats(mlb_id: int, season: int) -> dict | None:
    """Fetch 2B and HR for a player. Returns {doubles, homers, games_played} or None."""
    try:
        data = mlb_get(
            f"/people/{mlb_id}/stats",
            {"stats": "season", "season": season, "sportId": 1},
        )
        splits = data.get("stats", [{}])[0].get("splits", [])
        if not splits:
            return None
        # Use split with most gamesPlayed (handles traded players)
        best = max(splits, key=lambda s: s.get("stat", {}).get("gamesPlayed", 0))
        stat = best.get("stat", {})
        return {
            "doubles":      stat.get("doubles", 0),
            "homers":       stat.get("homeRuns", 0),
            "games_played": stat.get("gamesPlayed", 0),
        }
    except Exception as e:
        print(f"    WARNING: stat fetch failed for id={mlb_id}: {e}")
        return None


def assign_ranks(items: list[dict], key: str = "total") -> list[dict]:
    items.sort(key=lambda x: (x[key], x.get("doubles", 0)), reverse=True)
    rank = 1
    for i, item in enumerate(items):
        if i > 0 and item[key] == items[i - 1][key]:
            item["rank"] = items[i - 1]["rank"]
        else:
            item["rank"] = rank
        rank = i + 2
    return items


def load_csv() -> list[dict]:
    with open(CSV_PATH, newline="", encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


def main():
    rows = load_csv()
    print(f"Loaded {len(rows)} rows from {CSV_PATH.name}")

    # Build player -> {group, teams} map
    player_teams: dict[str, dict] = {}  # name -> {group, team_names: list}
    team_rosters: dict[str, list] = {}  # team_name -> [player_names]

    for row in rows:
        raw_name   = row.get("Player", "").strip()
        team_name  = row.get("Team", "").strip()
        group_raw  = row.get("Tier", "").strip()

        name  = fix_name(raw_name)
        group = GROUP_MAP.get(group_raw, group_raw)

        if not name:
            continue

        if name not in player_teams:
            player_teams[name] = {"group": group, "teams": []}
        player_teams[name]["teams"].append(team_name)

        if team_name not in team_rosters:
            team_rosters[team_name] = []
        if name not in team_rosters[team_name]:
            team_rosters[team_name].append(name)

    unique_names = sorted(player_teams.keys())
    print(f"Unique players: {len(unique_names)}")

    # Build MLB roster lookup
    roster = build_roster_lookup(SEASON)

    # Fetch stats for each unique player
    print(f"\nFetching {SEASON} stats...")
    player_stats: dict[str, dict] = {}
    not_found: list[str] = []

    for name in unique_names:
        mlb_id = PLAYER_IDS.get(name) or find_player_id(name, roster)
        if mlb_id is None:
            print(f"  NOT FOUND: {name!r}")
            not_found.append(name)
            player_stats[name] = {"doubles": 0, "homers": 0, "games_played": 0, "mlb_id": None}
            continue

        stats = fetch_player_stats(mlb_id, SEASON)
        if stats is None:
            print(f"  NO STATS: {name!r} (id={mlb_id})")
            player_stats[name] = {"doubles": 0, "homers": 0, "games_played": 0, "mlb_id": mlb_id}
        else:
            d, hr, gp = stats["doubles"], stats["homers"], stats["games_played"]
            total = d + hr
            print(f"  {name}: 2B={d} HR={hr} Total={total} G={gp}")
            player_stats[name] = {
                "doubles":      d,
                "homers":       hr,
                "games_played": gp,
                "mlb_id":       mlb_id,
            }
        time.sleep(0.05)

    if not_found:
        print(f"\nPlayers not found in MLB roster ({len(not_found)}):")
        for n in not_found:
            print(f"  - {n!r}")

    # Build players list
    players = []
    for name, meta in player_teams.items():
        stats = player_stats.get(name, {})
        d     = stats.get("doubles", 0)
        hr    = stats.get("homers", 0)
        gp    = stats.get("games_played", 0)
        total = d + hr
        times = len(set(meta["teams"]))  # unique teams that picked this player
        per_game = round(total / gp, 3) if gp else None
        players.append({
            "rank":          0,  # assigned below
            "name":          name,
            "group":         meta["group"],
            "times_drafted": times,
            "total":         total,
            "doubles":       d,
            "homers":        hr,
            "games":         gp,
            "per_game":      per_game,
        })

    assign_ranks(players)

    # Build teams list
    teams = []
    for team_name, roster_names in team_rosters.items():
        # Get owner from CSV (first row for this team)
        owner = None
        for row in rows:
            if row.get("Team", "").strip() == team_name:
                owner = row.get("Owner", "").strip()
                break

        d_total  = sum(player_stats.get(n, {}).get("doubles", 0) for n in roster_names)
        hr_total = sum(player_stats.get(n, {}).get("homers",  0) for n in roster_names)
        total    = d_total + hr_total
        teams.append({
            "rank":      0,
            "team_name": team_name,
            "owner":     owner,
            "total":     total,
            "doubles":   d_total,
            "homers":    hr_total,
        })

    assign_ranks(teams)

    # Write output
    year_dir = ARCHIVE / str(SEASON)
    year_dir.mkdir(parents=True, exist_ok=True)

    players_out = year_dir / "players.json"
    teams_out   = year_dir / "teams.json"

    with open(players_out, "w") as fh:
        json.dump({"season": SEASON, "players": players}, fh, indent=2)
    print(f"\nWrote {players_out} ({players_out.stat().st_size:,} bytes)")

    with open(teams_out, "w") as fh:
        json.dump({"season": SEASON, "teams": teams}, fh, indent=2)
    print(f"Wrote {teams_out} ({teams_out.stat().st_size:,} bytes)")

    # Update index.json
    index_path = ARCHIVE / "index.json"
    existing = []
    if index_path.exists():
        with open(index_path) as fh:
            existing = json.load(fh).get("seasons", [])
    all_seasons = sorted(set(existing + [SEASON]), reverse=True)
    with open(index_path, "w") as fh:
        json.dump({"seasons": all_seasons}, fh, indent=2)
    print(f"Updated index.json: {all_seasons}")


if __name__ == "__main__":
    main()
