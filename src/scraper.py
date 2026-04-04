import requests

from models import PlayerStats

MLB_API = "https://statsapi.mlb.com/api/v1"


def fetch_player_stats(mlb_id: int, name: str, br_id: str, group: str, season: int) -> PlayerStats:
    """Fetch a single player's hitting stats from the MLB Stats API."""
    if not mlb_id:
        print(f"  {name}: no MLB ID, skipping")
        return PlayerStats(name=name, br_id=br_id, group=group)

    url = f"{MLB_API}/people/{mlb_id}/stats"
    params = {"stats": "season", "group": "hitting", "season": season}
    try:
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"  ERROR fetching {name}: {e}")
        return PlayerStats(name=name, br_id=br_id, group=group)

    stats_list = resp.json().get("stats", [])
    splits = stats_list[0].get("splits", []) if stats_list else []
    if not splits:
        print(f"  {name}: no {season} stats yet (0 2B, 0 HR, 0 G)")
        return PlayerStats(name=name, br_id=br_id, group=group)

    # Use the last split which is the season total (handles traded players)
    last_split = splits[-1]
    stat = last_split.get("stat", {})
    doubles = stat.get("doubles", 0) or 0
    homers  = stat.get("homeRuns", 0) or 0
    games   = stat.get("gamesPlayed", 0) or 0
    mlb_team = last_split.get("team", {}).get("abbreviation", "")

    print(f"  {name} ({group}): {games}G  {doubles}2B  {homers}HR  ({doubles + homers} total)")
    return PlayerStats(name=name, br_id=br_id, group=group, mlb_team=mlb_team, doubles=doubles, homers=homers, games_played=games)


def fetch_top_combined_leaders(season: int, limit: int = 100) -> dict[int, dict]:
    """
    Fetch HR and 2B leaders from the MLB Stats API.
    Returns {mlb_id: {"name": str, "homers": int, "doubles": int}}.
    Makes two separate calls (one per category) to ensure compatibility.
    """
    combined: dict[int, dict] = {}

    for category in ("homeRuns", "doubles"):
        url = f"{MLB_API}/stats/leaders"
        params = {
            "leaderCategories": category,
            "season": season,
            "limit": limit,
            "sportId": 1,
        }
        try:
            resp = requests.get(url, params=params, timeout=15)
            resp.raise_for_status()
        except requests.RequestException as e:
            print(f"  ERROR fetching {category} leaders: {e}")
            continue

        for league_leader in resp.json().get("leagueLeaders", []):
            for entry in league_leader.get("leaders", []):
                person = entry.get("person", {})
                mlb_id = person.get("id")
                if not mlb_id:
                    continue
                if mlb_id not in combined:
                    combined[mlb_id] = {
                        "name": person.get("fullName", ""),
                        "homers": 0,
                        "doubles": 0,
                    }
                value = int(entry.get("value", 0) or 0)
                if category == "homeRuns":
                    combined[mlb_id]["homers"] = value
                else:
                    combined[mlb_id]["doubles"] = value

    return combined


def fetch_undrafted_top_players(
    config_players: dict,
    season: int,
    top_n: int = 50,
) -> list[PlayerStats]:
    """
    Fetch and return PlayerStats for the top N players by 2B+HR
    who are NOT already in the drafted player config.
    """
    config_mlb_ids = {
        v.get("mlb_id")
        for v in config_players.values()
        if isinstance(v, dict) and v.get("mlb_id")
    }

    print("Fetching MLB leaders to find undrafted top players...")
    leaders = fetch_top_combined_leaders(season, limit=100)
    print(f"  Got {len(leaders)} players from leaders endpoint")

    # Sort by combined total, find top-N that aren't drafted
    sorted_leaders = sorted(
        leaders.items(),
        key=lambda x: x[1]["homers"] + x[1]["doubles"],
        reverse=True,
    )
    undrafted = [
        (mlb_id, info)
        for mlb_id, info in sorted_leaders
        if mlb_id not in config_mlb_ids
    ][:top_n]

    print(f"  {len(undrafted)} undrafted players qualify for top-{top_n} display")

    result = []
    for i, (mlb_id, info) in enumerate(undrafted, 1):
        print(f"  [{i}/{len(undrafted)}] {info['name']} (undrafted)...")
        stats = fetch_player_stats(
            mlb_id=mlb_id,
            name=info["name"],
            br_id=f"mlb_{mlb_id}",
            group="Undrafted",
            season=season,
        )
        stats.drafted = False
        result.append(stats)

    return result


def scrape_all_players(players_config: dict, season: int = 2026) -> dict[str, PlayerStats]:
    """Fetch stats for every player in the config from the MLB Stats API."""
    results: dict[str, PlayerStats] = {}
    players = [(k, v) for k, v in players_config.items() if not k.startswith("_") and isinstance(v, dict)]
    total = len(players)

    for i, (br_id, info) in enumerate(players, 1):
        print(f"[{i}/{total}] {info['name']} ...")
        stats = fetch_player_stats(
            mlb_id=info.get("mlb_id", 0),
            name=info["name"],
            br_id=br_id,
            group=info.get("group", "Wildcard"),
            season=season,
        )
        results[br_id] = stats

    return results
