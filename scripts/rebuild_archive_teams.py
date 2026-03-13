#!/usr/bin/env python3
"""
Add mlb_team abbreviation to 2019 and 2020 archive players.json.

Uses the team the player finished the season playing for (splits[-1] with a
valid team.id). Rebuilds both archive files in-place.

Usage:
    python3 scripts/rebuild_archive_teams.py
"""

import json
import time
import urllib.request
import urllib.parse
from pathlib import Path

ARCHIVE = Path(__file__).parent.parent / "docs" / "data" / "archive"
MLB_API = "https://statsapi.mlb.com/api/v1"

# Known MLB IDs for accented/variant names used in the CSV (carried from
# the original build scripts so we can re-fetch stats + team)
PLAYER_IDS_2019: dict[str, int] = {
    "CJ Cron":              543068,   # C.J. Cron
    "Gary Sanchez":         596142,   # Gary Sánchez
    "Javier Baez":          595879,   # Javier Báez
    "Edwin Encarnacion":    429665,   # Edwin Encarnación
    "Jose Ramirez":         608070,   # José Ramírez
    "Ronald Acuna Jr.":     660670,   # Ronald Acuña Jr.
    "Nicholas Castellanos": 592206,   # Nick Castellanos
    "Jesus Aguilar":        542583,   # Jesús Aguilar
    "Jose Abreu":           547989,   # José Abreu
}

PLAYER_IDS_2020: dict[str, int] = {
    "Eloy Jimenez":         650391,   # Eloy Jiménez
    "Eugenio Suarez":       553993,   # Eugenio Suárez
    "Javier Baez":          595879,   # Javier Báez
    "Jose Abreu":           547989,   # José Abreu
    "Jose Ramirez":         608070,   # José Ramírez
    "Luis Robert":          673357,   # Luis Robert Jr.
    "Miguel Sano":          593934,   # Miguel Sanó
    "Nicholas Castellanos": 592206,   # Nick Castellanos
    "Renato Nunez":         600524,   # Renato Núñez
    "Ronald Acuna Jr.":     660670,   # Ronald Acuña Jr.
    "Yoan Moncada":         660162,   # Yoán Moncada
}


def mlb_get(path: str, params: dict = None) -> dict:
    url = f"{MLB_API}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=15) as resp:
        return json.loads(resp.read())


def build_team_abbrev_map(season: int) -> dict[int, str]:
    """Return {team_id: abbreviation} for all MLB teams in a season."""
    data = mlb_get("/teams", {"season": season, "sportId": 1})
    return {t["id"]: t["abbreviation"] for t in data.get("teams", []) if "abbreviation" in t}


def build_roster_lookup(season: int) -> dict[str, int]:
    """Return {full_name: mlb_id} for all players in a season."""
    data = mlb_get("/sports/1/players", {"season": season, "sportId": 1})
    return {p["fullName"]: p["id"] for p in data.get("people", [])}


def find_player_id(name: str, roster: dict[str, int]) -> int | None:
    if name in roster:
        return roster[name]
    lower = {k.lower(): v for k, v in roster.items()}
    return lower.get(name.lower())


def fetch_final_team(mlb_id: int, season: int, team_map: dict[int, str]) -> str | None:
    """Return abbreviation of the team the player finished the season with."""
    try:
        data = mlb_get(
            f"/people/{mlb_id}/stats",
            {"stats": "season", "season": season, "sportId": 1},
        )
        splits = data.get("stats", [{}])[0].get("splits", [])
        if not splits:
            return None
        # Walk splits in reverse to find the last one with a valid team.id
        for split in reversed(splits):
            team_id = split.get("team", {}).get("id")
            if team_id and team_id in team_map:
                return team_map[team_id]
        return None
    except Exception as e:
        print(f"    WARNING: team fetch failed for id={mlb_id}: {e}")
        return None


def rebuild(season: int, player_ids_override: dict[str, int]) -> None:
    print(f"\n=== {season} ===")
    players_path = ARCHIVE / str(season) / "players.json"

    with open(players_path) as f:
        data = json.load(f)
    players = data["players"]

    print(f"Building team abbreviation map for {season}...")
    team_map = build_team_abbrev_map(season)

    print(f"Building player roster lookup for {season}...")
    roster = build_roster_lookup(season)

    print(f"Fetching final-team for {len(players)} players...")
    for p in players:
        name = p["name"]
        mlb_id = player_ids_override.get(name) or find_player_id(name, roster)
        if mlb_id is None:
            print(f"  NOT FOUND: {name!r}")
            p["mlb_team"] = None
            continue
        abbrev = fetch_final_team(mlb_id, season, team_map)
        print(f"  {name}: {abbrev}")
        p["mlb_team"] = abbrev
        time.sleep(0.05)

    with open(players_path, "w") as f:
        json.dump(data, f, indent=2)
    print(f"Wrote {players_path} ({players_path.stat().st_size:,} bytes)")


def main():
    rebuild(2019, PLAYER_IDS_2019)
    rebuild(2020, PLAYER_IDS_2020)
    print("\nDone.")


if __name__ == "__main__":
    main()
