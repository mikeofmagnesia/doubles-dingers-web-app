"""
Doubles and Dingers - daily stat updater.

Reads team/player configuration from data/teams.json, scrapes 2026 stats
from Baseball Reference, and writes JSON files to docs/data/ for the web app.

No environment variables required for normal operation.
Run: python src/main.py
"""

import json
import sys
from datetime import date
from pathlib import Path

from scraper import scrape_all_players
from writer import (
    read_latest_player_history,
    read_latest_team_history,
    write_all,
)
from models import Team, PlayerStats


def load_config(path: Path) -> dict:
    with open(path) as f:
        return json.load(f)


def build_teams(config: dict, player_stats: dict[str, PlayerStats]) -> list[Team]:
    teams = []
    for team_data in config["teams"]:
        players = [
            player_stats[pid]
            for pid in team_data["players"]
            if pid in player_stats
        ]
        missing = [pid for pid in team_data["players"] if pid not in player_stats]
        if missing:
            print(f"  WARNING: unknown player IDs on {team_data['owner']}'s team: {missing}")

        teams.append(Team(
            owner=team_data["owner"],
            team_name=team_data["team_name"],
            player_ids=team_data["players"],
            players=players,
        ))
    return teams


def assign_ranks_and_history(
    players: list[PlayerStats],
    teams: list[Team],
    prev_players: dict[str, dict],
    prev_teams: dict[str, dict],
) -> tuple[list[PlayerStats], list[Team]]:
    """
    Sort players and teams by 2B+HR (desc), assign ranks, and attach
    previous-day data from history. Returns the sorted lists.
    """
    sorted_players = sorted(players, key=lambda p: (p.total, p.doubles), reverse=True)
    for i, player in enumerate(sorted_players, 1):
        player.rank = i
        prev = prev_players.get(player.name)
        if prev:
            player.prev_rank = prev.get("rank")
            player.prev_doubles = prev.get("doubles")
            player.prev_homers = prev.get("homers")

    sorted_teams = sorted(teams, key=lambda t: (t.total, t.doubles), reverse=True)
    for i, team in enumerate(sorted_teams, 1):
        team.rank = i
        prev = prev_teams.get(team.team_name)
        if prev:
            team.prev_rank = prev.get("rank")
            team.prev_doubles = prev.get("doubles")
            team.prev_homers = prev.get("homers")

    return sorted_players, sorted_teams


def main() -> None:
    config_path = Path(__file__).parent.parent / "data" / "teams.json"

    if not config_path.exists():
        print(f"ERROR: Config file not found at {config_path}")
        sys.exit(1)

    config = load_config(config_path)
    season = config.get("season", 2026)
    player_count = len(config.get("players", {}))
    team_count = len(config.get("teams", []))
    print(f"Loaded config: {player_count} players across {team_count} teams (season {season})\n")

    # --- Step 1: Read previous day's history from JSON files ---
    print("--- Reading previous history ---")
    prev_players = read_latest_player_history()
    prev_teams = read_latest_team_history()
    print(f"  Found history for {len(prev_players)} players, {len(prev_teams)} teams")

    # --- Step 2: Scrape today's stats ---
    print("\n--- Scraping Baseball Reference ---")
    player_stats = scrape_all_players(config["players"])

    # --- Step 3: Build teams, sort, assign ranks, attach prev data ---
    print("\n--- Building teams and assigning ranks ---")
    teams = build_teams(config, player_stats)
    all_players = list(player_stats.values())
    sorted_players, sorted_teams = assign_ranks_and_history(
        all_players, teams, prev_players, prev_teams
    )

    # --- Step 4: Write all JSON data files ---
    today = date.today().isoformat()
    print(f"\n--- Writing JSON data files for {today} ---")
    write_all(
        players=sorted_players,
        teams=sorted_teams,
        teams_config=config,
        today=today,
        season=season,
    )

    print("\nDone.")


if __name__ == "__main__":
    main()
