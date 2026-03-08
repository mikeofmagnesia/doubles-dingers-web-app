import time
import requests
from bs4 import BeautifulSoup

from models import PlayerStats

# Baseball Reference robots.txt specifies a 3-second crawl delay.
# We use 3.5s to be respectful and avoid any edge cases.
CRAWL_DELAY = 3.5

HEADERS = {
    "User-Agent": (
        "DoublesAndDingers/1.0 (personal fantasy stats tracker; "
        "non-commercial use; respects crawl-delay)"
    )
}


def scrape_player(br_id: str, name: str, br_url: str, group: str = "Wildcard") -> PlayerStats:
    """Scrape a single player's 2026 stats from Baseball Reference."""
    try:
        response = requests.get(br_url, headers=HEADERS, timeout=30)
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"  ERROR fetching {name}: {e}")
        return PlayerStats(name=name, br_id=br_id, group=group)

    soup = BeautifulSoup(response.text, "html.parser")

    table = soup.find("table", {"id": "batting_standard"})
    if not table:
        print(f"  WARNING: No batting table found for {name}")
        return PlayerStats(name=name, br_id=br_id, group=group)

    tbody = table.find("tbody")
    if not tbody:
        return PlayerStats(name=name, br_id=br_id, group=group)

    rows_2026 = []
    for row in tbody.find_all("tr"):
        year_cell = row.find(["th", "td"], {"data-stat": "year_ID"})
        if year_cell and year_cell.get_text(strip=True) == "2026":
            rows_2026.append(row)

    if not rows_2026:
        print(f"  {name}: no 2026 stats yet (0 2B, 0 HR, 0 G)")
        return PlayerStats(name=name, br_id=br_id, group=group)

    # For players traded mid-season there will be a "TOT" row; prefer it.
    target_row = rows_2026[0]
    if len(rows_2026) > 1:
        for row in rows_2026:
            team_cell = row.find("td", {"data-stat": "team_ID"})
            if team_cell and team_cell.get_text(strip=True) == "TOT":
                target_row = row
                break

    def get_stat(row, stat_name: str) -> int:
        cell = row.find("td", {"data-stat": stat_name})
        if cell:
            text = cell.get_text(strip=True)
            return int(text) if text.isdigit() else 0
        return 0

    doubles = get_stat(target_row, "2B")
    homers = get_stat(target_row, "HR")
    games = get_stat(target_row, "G")

    print(f"  {name} ({group}): {games}G  {doubles}2B  {homers}HR  ({doubles + homers} total)")
    return PlayerStats(name=name, br_id=br_id, group=group, doubles=doubles, homers=homers, games_played=games)


def scrape_all_players(players_config: dict) -> dict[str, PlayerStats]:
    """
    Scrape stats for every player in the config, respecting Baseball Reference's
    3-second crawl delay between requests.
    """
    results: dict[str, PlayerStats] = {}
    total = len(players_config)

    for i, (br_id, info) in enumerate(players_config.items(), 1):
        print(f"[{i}/{total}] Scraping {info['name']} ...")
        stats = scrape_player(
            br_id,
            info["name"],
            info["br_url"],
            info.get("group", "Wildcard"),
        )
        results[br_id] = stats

        if i < total:
            time.sleep(CRAWL_DELAY)

    return results
