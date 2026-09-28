#!/usr/bin/env python3
"""
Build the 2026 season archive (Past Seasons page).

Team standings: taken directly from the final docs/data/team_standings.json
(the season is over, so today's numbers are final), reshaped into the
archive schema and including the new "owner" column.

Player standings: the top 100 players in MLB this season by combined 2B+HR,
plus any drafted player who didn't crack the top 100. Drafted players use
the final stats already in docs/data/player_stats.json. Undrafted players
come from the MLB Stats API HR/2B leaderboards (same method the app already
uses for the live "top undrafted" feature, extended from top-50 to top-100).

Perfect Team: a straight copy of the final docs/data/perfect_team.json.

Usage:
    python3 scripts/build_2026_archive.py
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))

from scraper import fetch_top_combined_leaders, fetch_player_stats  # noqa: E402

SEASON = 2026
ARCHIVE_DIR = ROOT / "docs" / "data" / "archive" / str(SEASON)


def assign_ranks(items: list[dict]) -> None:
    """Assign competition ranks (ties share a rank; next rank skips)."""
    items.sort(key=lambda x: (x["total"], x["doubles"]), reverse=True)
    for i, item in enumerate(items):
        item["rank"] = items[i - 1]["rank"] if i > 0 and item["total"] == items[i - 1]["total"] else i + 1


def build_teams_archive() -> None:
    with open(ROOT / "docs" / "data" / "team_standings.json") as f:
        standings = json.load(f)["teams"]

    teams = [
        {
            "rank": t["rank"],
            "team_name": t["team_name"],
            "owner": t["owner"],
            "total": t["total"],
            "doubles": t["doubles"],
            "homers": t["homers"],
        }
        for t in standings
    ]

    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    with open(ARCHIVE_DIR / "teams.json", "w") as f:
        json.dump({"season": SEASON, "teams": teams}, f, indent=2)
    print(f"Wrote {ARCHIVE_DIR / 'teams.json'} ({len(teams)} teams)")


def build_players_archive() -> None:
    with open(ROOT / "data" / "teams.json") as f:
        teams_config = json.load(f)
    with open(ROOT / "docs" / "data" / "player_stats.json") as f:
        player_stats = json.load(f)["players"]

    drafted = [p for p in player_stats if p.get("drafted") is not False]
    drafted_names_lower = {p["name"].lower() for p in drafted}

    config_players = teams_config.get("players", {})
    drafted_mlb_ids = {
        v.get("mlb_id") for v in config_players.values()
        if isinstance(v, dict) and v.get("mlb_id")
    }

    # Existing undrafted rows already carry full stats (games, mlb_team, etc.)
    # from today's run -- reuse them instead of re-fetching.
    already_fetched_undrafted = {
        p["br_id"]: p for p in player_stats if p.get("drafted") is False
    }

    print("Fetching MLB-wide HR/2B leaderboards...")
    leaders = fetch_top_combined_leaders(SEASON, limit=100)
    print(f"  Got {len(leaders)} candidate players")

    undrafted_candidates = [
        (mlb_id, info) for mlb_id, info in leaders.items()
        if mlb_id not in drafted_mlb_ids and info["name"].lower() not in drafted_names_lower
    ]
    undrafted_candidates.sort(key=lambda x: (x[1]["homers"] + x[1]["doubles"]), reverse=True)

    # Build the full candidate pool: drafted (real totals) + undrafted leaderboard entries.
    pool = []
    for p in drafted:
        pool.append({"kind": "drafted", "total": p["total"], "doubles": p["doubles"], "row": p})
    for mlb_id, info in undrafted_candidates:
        total = info["homers"] + info["doubles"]
        pool.append({"kind": "undrafted", "total": total, "doubles": info["doubles"],
                     "mlb_id": mlb_id, "info": info})

    pool.sort(key=lambda x: (x["total"], x["doubles"]), reverse=True)

    # Determine the top-100 cutoff (ties at the boundary are all included).
    cutoff_total = pool[99]["total"] if len(pool) >= 100 else (pool[-1]["total"] if pool else 0)
    top100 = [x for x in pool if x["total"] >= cutoff_total]
    stragglers = [x for x in pool if x["kind"] == "drafted" and x["total"] < cutoff_total]

    final_pool = top100 + stragglers
    print(f"  Top 100 (with ties): {len(top100)} players; "
          f"+{len(stragglers)} drafted players outside the top 100")

    # Fill in full stats for undrafted entries in the final list.
    rows = []
    fetch_count = 0
    for item in final_pool:
        if item["kind"] == "drafted":
            p = item["row"]
            rows.append({
                "name": p["name"],
                "mlb_team": p["mlb_team"],
                "group": p["group"],
                "times_drafted": p.get("times_selected", 0),
                "total": p["total"],
                "doubles": p["doubles"],
                "homers": p["homers"],
                "games": p["games_played"],
                "per_game": p["per_game"],
            })
        else:
            mlb_id, info = item["mlb_id"], item["info"]
            br_id = f"mlb_{mlb_id}"
            cached = already_fetched_undrafted.get(br_id)
            if cached:
                rows.append({
                    "name": cached["name"],
                    "mlb_team": cached["mlb_team"],
                    "group": "Wildcard",
                    "times_drafted": 0,
                    "total": cached["total"],
                    "doubles": cached["doubles"],
                    "homers": cached["homers"],
                    "games": cached["games_played"],
                    "per_game": cached["per_game"],
                })
            else:
                fetch_count += 1
                print(f"  Fetching full stats for {info['name']} (undrafted, not in cached top-50)...")
                stats = fetch_player_stats(mlb_id=mlb_id, name=info["name"], br_id=br_id,
                                            group="Wildcard", season=SEASON)
                rows.append({
                    "name": stats.name,
                    "mlb_team": stats.mlb_team,
                    "group": "Wildcard",
                    "times_drafted": 0,
                    "total": stats.total,
                    "doubles": stats.doubles,
                    "homers": stats.homers,
                    "games": stats.games_played,
                    "per_game": stats.per_game,
                })

    print(f"  Fetched {fetch_count} additional undrafted players not already cached")

    assign_ranks(rows)
    rows.sort(key=lambda r: r["rank"])

    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    with open(ARCHIVE_DIR / "players.json", "w") as f:
        json.dump({"season": SEASON, "players": rows}, f, indent=2)
    print(f"Wrote {ARCHIVE_DIR / 'players.json'} ({len(rows)} players)")


def build_perfect_team_archive() -> None:
    with open(ROOT / "docs" / "data" / "perfect_team.json") as f:
        data = json.load(f)

    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    with open(ARCHIVE_DIR / "perfect_team.json", "w") as f:
        json.dump(data, f, indent=2)
    print(f"Wrote {ARCHIVE_DIR / 'perfect_team.json'}")


def update_archive_index() -> None:
    index_path = ROOT / "docs" / "data" / "archive" / "index.json"
    with open(index_path) as f:
        index = json.load(f)
    if SEASON not in index["seasons"]:
        index["seasons"].insert(0, SEASON)
    with open(index_path, "w") as f:
        json.dump(index, f, indent=2)
    print(f"Updated {index_path}: seasons = {index['seasons']}")


def main() -> None:
    build_teams_archive()
    build_players_archive()
    build_perfect_team_archive()
    update_archive_index()
    print("\nDone.")


if __name__ == "__main__":
    main()
