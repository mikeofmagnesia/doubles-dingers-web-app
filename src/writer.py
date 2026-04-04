"""
Doubles and Dingers - JSON data writer.

Writes all stat data to JSON files in docs/data/.
Called by main.py after scraping and ranking.

History files (player_history.json, team_history.json) are append-only:
existing records are preserved and today's data is appended (or replaced
if the job runs more than once in a day).
"""

import json
from datetime import date
from pathlib import Path

from models import PlayerStats, Team

DATA_DIR = Path(__file__).parent.parent / "docs" / "data"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _write_json(filename: str, data: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = DATA_DIR / filename
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
    size = path.stat().st_size
    print(f"  Wrote {filename} ({size:,} bytes)")


def _read_history(filename: str) -> list[dict]:
    """Read existing history records. Returns empty list if file not found."""
    path = DATA_DIR / filename
    if not path.exists():
        return []
    with open(path) as f:
        data = json.load(f)
    return data.get("records", [])


def _e(value):
    """Pass through value (None becomes JSON null)."""
    return value


def _player_row(p: PlayerStats) -> dict:
    return {"name": p.name, "mlb_team": p.mlb_team, "doubles": p.doubles, "homers": p.homers, "total": p.total}


# ---------------------------------------------------------------------------
# History: read (called by main.py before scraping to get prev-day data)
# ---------------------------------------------------------------------------

def read_latest_player_history() -> dict[str, dict]:
    """
    Returns {player_name: {"rank": int, "doubles": int, "homers": int}}
    from the most recently logged date that is before today.
    Returns an empty dict if no prior history exists.
    """
    records = _read_history("player_history.json")
    if not records:
        return {}

    today = date.today().isoformat()
    prior = [r for r in records if r.get("date", "") < today]
    if not prior:
        return {}

    latest_date = max(r["date"] for r in prior)
    return {
        r["player"]: {
            "rank": r.get("rank"),
            "doubles": r.get("doubles", 0),
            "homers": r.get("homers", 0),
        }
        for r in prior
        if r["date"] == latest_date
    }


def read_latest_team_history() -> dict[str, dict]:
    """
    Returns {team_name: {"rank": int, "doubles": int, "homers": int}}
    from the most recently logged date that is before today.
    Returns an empty dict if no prior history exists.
    """
    records = _read_history("team_history.json")
    if not records:
        return {}

    today = date.today().isoformat()
    prior = [r for r in records if r.get("date", "") < today]
    if not prior:
        return {}

    latest_date = max(r["date"] for r in prior)
    return {
        r["team"]: {
            "rank": r.get("rank"),
            "doubles": r.get("doubles", 0),
            "homers": r.get("homers", 0),
        }
        for r in prior
        if r["date"] == latest_date
    }


# ---------------------------------------------------------------------------
# Main views: write
# ---------------------------------------------------------------------------

def write_player_stats(players: list[PlayerStats], teams_config: dict) -> None:
    """Write View 1: Player Stats JSON."""
    # Count how many fantasy teams selected each player
    times_selected: dict[str, int] = {}
    for team in teams_config.get("teams", []):
        for pid in team.get("players", []):
            times_selected[pid] = times_selected.get(pid, 0) + 1

    rows = []
    for p in players:
        rows.append({
            "rank": p.rank,
            "name": p.name,
            "mlb_team": p.mlb_team,
            "br_id": p.br_id,
            "group": p.group,
            "drafted": p.drafted,
            "times_selected": times_selected.get(p.br_id, 0),
            "doubles": p.doubles,
            "homers": p.homers,
            "total": p.total,
            "games_played": p.games_played,
            "per_game": p.per_game,
            "prev_rank": _e(p.prev_rank),
            "prev_doubles": _e(p.doubles - p.prev_doubles) if p.prev_doubles is not None else None,
            "prev_homers": _e(p.homers - p.prev_homers) if p.prev_homers is not None else None,
            "prev_total": _e(p.prev_total),
            "rank_change": _e(p.rank_change),
            "total_change": _e(p.total_change),
        })

    _write_json("player_stats.json", {
        "updated": date.today().isoformat(),
        "players": rows,
    })


def write_team_standings(teams: list[Team]) -> None:
    """Write View 2: Team Standings JSON."""
    rows = []
    for t in teams:
        rows.append({
            "rank": t.rank,
            "owner": t.owner,
            "team_name": t.team_name,
            "doubles": t.doubles,
            "homers": t.homers,
            "total": t.total,
            "prev_rank": _e(t.prev_rank),
            "prev_doubles": _e(t.doubles - t.prev_doubles) if t.prev_doubles is not None else None,
            "prev_homers": _e(t.homers - t.prev_homers) if t.prev_homers is not None else None,
            "prev_total": _e(t.prev_total),
            "rank_change": _e(t.rank_change),
            "total_change": _e(t.total_change),
        })

    _write_json("team_standings.json", {
        "updated": date.today().isoformat(),
        "teams": rows,
    })


def write_perfect_team(players: list[PlayerStats]) -> None:
    """
    Write perfect_team.json — the best possible team picks.

    Rules:
    - For each lettered group (A, B, C): show the leader(s). If tied, show all
      but exclude that group's total from the grand total.
    - For Wildcard: show the top 4. If more than 4 players are tied at the 4th
      cutoff total, show all of them but count only 4 toward the grand total.
    """
    # Only drafted players are eligible
    drafted = [p for p in players if p.drafted]

    by_group: dict[str, list[PlayerStats]] = {}
    for p in drafted:
        by_group.setdefault(p.group, []).append(p)

    result_groups: dict[str, dict] = {}
    grand_total = 0
    has_tied_groups = False

    for group in ("A", "B", "C"):
        gp = sorted(by_group.get(group, []), key=lambda x: (x.total, x.doubles), reverse=True)
        if not gp:
            result_groups[group] = {"leaders": [], "is_tied": False}
            continue
        max_total = gp[0].total
        leaders = [p for p in gp if p.total == max_total]
        is_tied = len(leaders) > 1
        result_groups[group] = {
            "leaders": [_player_row(p) for p in leaders],
            "is_tied": is_tied,
        }
        grand_total += max_total
        if is_tied:
            has_tied_groups = True

    # Wildcard: all players not in a lettered group (drafted WC + undrafted).
    # The Perfect Team page shows the best possible WC picks regardless of draft status.
    wc_pool = [p for p in players if p.group not in ("A", "B", "C")]
    wc = sorted(wc_pool, key=lambda x: (x.total, x.doubles), reverse=True)
    if not wc:
        wildcard: dict = {"players": [], "is_tied": False, "counted_count": 0}
    elif len(wc) <= 4:
        wildcard = {
            "players": [_player_row(p) for p in wc],
            "is_tied": False,
            "counted_count": len(wc),
        }
        grand_total += sum(p.total for p in wc)
    else:
        cutoff = wc[3].total  # 4th-highest total
        definite = [p for p in wc if p.total > cutoff]
        tied_at_cutoff = [p for p in wc if p.total == cutoff]
        needed = 4 - len(definite)
        is_tied = len(tied_at_cutoff) > needed
        wildcard = {
            "players": [_player_row(p) for p in definite + tied_at_cutoff],
            "is_tied": is_tied,
            "counted_count": 4,
        }
        grand_total += sum(p.total for p in wc[:4])

    _write_json("perfect_team.json", {
        "updated": date.today().isoformat(),
        "groups": result_groups,
        "wildcard": wildcard,
        "grand_total": grand_total,
        "has_tied_groups": has_tied_groups,
    })


def write_team_rosters(teams: list[Team]) -> None:
    """Write View 3: Team Rosters JSON (sorted by team name per spec)."""
    team_rows = []
    for t in teams:
        player_rows = [
            {
                "name": p.name,
                "group": p.group,
                "doubles": p.doubles,
                "homers": p.homers,
                "total": p.total,
                "prev_doubles": _e(p.doubles - p.prev_doubles) if p.prev_doubles is not None else None,
                "prev_homers": _e(p.homers - p.prev_homers) if p.prev_homers is not None else None,
                "prev_total": _e(p.prev_total),
                "total_change": _e(p.total_change),
            }
            for p in t.players
        ]

        has_prev = any(p.prev_doubles is not None for p in t.players)
        prev_d_cumulative = sum(p.prev_doubles or 0 for p in t.players)
        prev_hr_cumulative = sum(p.prev_homers or 0 for p in t.players)
        prev_total = prev_d_cumulative + prev_hr_cumulative

        team_rows.append({
            "owner": t.owner,
            "team_name": t.team_name,
            "rank": t.rank,
            "rank_change": _e(t.rank_change),
            "players": player_rows,
            "totals": {
                "doubles": t.doubles,
                "homers": t.homers,
                "total": t.total,
                "prev_doubles": (t.doubles - prev_d_cumulative) if has_prev else None,
                "prev_homers": (t.homers - prev_hr_cumulative) if has_prev else None,
                "prev_total": prev_total if has_prev else None,
                "total_change": (t.total - prev_total) if has_prev else None,
            },
        })

    # View 3 spec: sorted by team name
    team_rows.sort(key=lambda t: t["team_name"].lower())

    _write_json("team_rosters.json", {
        "updated": date.today().isoformat(),
        "teams": team_rows,
    })


# ---------------------------------------------------------------------------
# History: append
# ---------------------------------------------------------------------------

def append_player_history(players: list[PlayerStats], today: str) -> None:
    """Append today's player stats to player_history.json (idempotent).
    Undrafted players are excluded from history."""
    records = _read_history("player_history.json")
    # Replace any records for today (makes the job safely re-runnable)
    records = [r for r in records if r.get("date") != today]

    for p in [p for p in players if p.drafted]:
        records.append({
            "date": today,
            "player": p.name,
            "group": p.group,
            "rank": p.rank,
            "doubles": p.doubles,
            "homers": p.homers,
            "total": p.total,
        })

    _write_json("player_history.json", {"records": records})
    print(f"  Appended {len(players)} player records for {today}")


def append_team_history(teams: list[Team], today: str) -> None:
    """Append today's team stats to team_history.json (idempotent)."""
    records = _read_history("team_history.json")
    records = [r for r in records if r.get("date") != today]

    for t in teams:
        records.append({
            "date": today,
            "owner": t.owner,
            "team": t.team_name,
            "rank": t.rank,
            "doubles": t.doubles,
            "homers": t.homers,
            "total": t.total,
        })

    _write_json("team_history.json", {"records": records})
    print(f"  Appended {len(teams)} team records for {today}")


# ---------------------------------------------------------------------------
# Supporting files
# ---------------------------------------------------------------------------

def write_groups(teams_config: dict) -> None:
    """
    Write groups.json with the A/B/C player assignments.
    Read by the entry form to populate group dropdowns and exclude those players
    from the wildcard autocomplete. players_list.json (all MLB players) is managed
    separately by scripts/build_players.py.
    """
    groups_raw = teams_config.get("groups", {})
    players_lookup = teams_config.get("players", {})

    groups: dict[str, list] = {}
    for group_name, br_ids in groups_raw.items():
        if group_name.startswith("_"):
            continue
        groups[group_name] = [
            {
                "br_id": br_id,
                "name": players_lookup.get(br_id, {}).get("name", br_id),
            }
            for br_id in br_ids
        ]

    _write_json("groups.json", groups)


def write_meta(season: int) -> None:
    """Write meta.json with last-updated info."""
    _write_json("meta.json", {
        "season": season,
        "updated": date.today().isoformat(),
    })


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def write_all(
    players: list[PlayerStats],
    teams: list[Team],
    teams_config: dict,
    today: str,
    season: int = 2026,
) -> None:
    """Write all JSON data files for the web app."""
    write_player_stats(players, teams_config)
    write_team_standings(teams)
    write_team_rosters(teams)
    write_perfect_team(players)
    append_player_history(players, today)
    append_team_history(teams, today)
    write_groups(teams_config)
    write_meta(season)
