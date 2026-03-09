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

    splits = resp.json().get("stats", [{}])[0].get("splits", [])
    if not splits:
        print(f"  {name}: no {season} stats yet (0 2B, 0 HR, 0 G)")
        return PlayerStats(name=name, br_id=br_id, group=group)

    # Use the last split which is the season total (handles traded players)
    stat = splits[-1].get("stat", {})
    doubles = stat.get("doubles", 0) or 0
    homers  = stat.get("homeRuns", 0) or 0
    games   = stat.get("gamesPlayed", 0) or 0

    print(f"  {name} ({group}): {games}G  {doubles}2B  {homers}HR  ({doubles + homers} total)")
    return PlayerStats(name=name, br_id=br_id, group=group, doubles=doubles, homers=homers, games_played=games)


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
