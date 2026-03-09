"""
Doubles and Dingers - build comprehensive MLB player list.

Scrapes Baseball Reference's player index (26 letter pages) to collect all
currently active MLB players with their BBref IDs. Overlays group assignments
(A/B/C) from data/teams.json. Fetches team and position from the MLB Stats API
(single request, no scraping). Writes to docs/data/players_list.json.

Run this once before the season starts (and again if active rosters change):
    python scripts/build_players.py

Baseball Reference marks active players in bold on their player index pages.
The crawl delay is respected between each letter page (~91 seconds total).
"""

import json
import time
import unicodedata
from pathlib import Path

import requests
from bs4 import BeautifulSoup

BASE_DIR   = Path(__file__).parent.parent
DATA_DIR   = BASE_DIR / "docs" / "data"
TEAMS_JSON = BASE_DIR / "data" / "teams.json"

CRAWL_DELAY = 3.5
MLB_SEASON  = 2026

HEADERS = {
    "User-Agent": (
        "DoublesAndDingers/1.0 (personal fantasy stats tracker; "
        "non-commercial use; respects crawl-delay)"
    )
}


def normalize(name: str) -> str:
    """Lowercase, strip accents, collapse whitespace for fuzzy matching."""
    nfkd = unicodedata.normalize("NFKD", name)
    ascii_name = nfkd.encode("ascii", "ignore").decode("ascii")
    return " ".join(ascii_name.lower().split())


def fetch_team_map() -> dict[int, str]:
    """Return {team_id: abbreviation} for all MLB teams."""
    url = f"https://statsapi.mlb.com/api/v1/teams?sportId=1&season={MLB_SEASON}"
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    return {t["id"]: t.get("abbreviation", "") for t in resp.json().get("teams", [])}


def fetch_mlb_roster() -> dict[str, dict]:
    """
    Fetch all active MLB players from the MLB Stats API.
    Returns {normalized_name: {team, position}} lookup.
    """
    team_map = fetch_team_map()
    url = f"https://statsapi.mlb.com/api/v1/sports/1/players?season={MLB_SEASON}"
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    lookup: dict[str, dict] = {}
    for p in data.get("people", []):
        name    = p.get("fullName", "")
        mlb_id  = p.get("id", 0)
        team_id = p.get("currentTeam", {}).get("id", 0)
        team    = team_map.get(team_id, "")
        pos     = p.get("primaryPosition", {}).get("abbreviation", "")
        if name:
            lookup[normalize(name)] = {"mlb_id": mlb_id, "team": team, "pos": pos}
    return lookup


def load_group_assignments() -> dict[str, str]:
    """Return {br_id: group_name} from data/teams.json groups config."""
    if not TEAMS_JSON.exists():
        print(f"WARNING: {TEAMS_JSON} not found. No group assignments will be applied.")
        return {}

    with open(TEAMS_JSON) as f:
        config = json.load(f)

    assignments: dict[str, str] = {}
    for group_name, br_ids in config.get("groups", {}).items():
        if group_name.startswith("_"):
            continue
        for br_id in br_ids:
            assignments[br_id] = group_name
    return assignments


def scrape_letter(letter: str) -> list[dict]:
    """
    Scrape one letter-index page from Baseball Reference.
    Active players are shown in bold; inactive players are not.
    Returns list of {br_id, name} dicts.
    """
    url = f"https://www.baseball-reference.com/players/{letter}/"
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"

    soup = BeautifulSoup(resp.text, "html.parser")
    players = []

    # Active players are wrapped in <b><a href="/players/X/id.shtml">Name</a></b>
    for b_tag in soup.find_all("b"):
        a = b_tag.find("a", href=True)
        if not a:
            continue
        href = a.get("href", "")
        if not href.startswith("/players/"):
            continue
        # href format: /players/j/judgear01.shtml
        br_id = href.rstrip("/").split("/")[-1].replace(".shtml", "")
        name  = a.get_text(strip=True)
        if br_id and name:
            players.append({"br_id": br_id, "name": name})

    return players


def main() -> None:
    print("Fetching team/position data from MLB Stats API...")
    try:
        mlb_lookup = fetch_mlb_roster()
        print(f"Loaded {len(mlb_lookup)} players from MLB Stats API.\n")
    except Exception as e:
        print(f"WARNING: Could not fetch MLB roster ({e}). Team/position will be empty.\n")
        mlb_lookup = {}

    print("Building comprehensive MLB player list from Baseball Reference...")
    print(
        f"Scraping 26 letter pages with {CRAWL_DELAY}s delay "
        f"(~{int(26 * CRAWL_DELAY)}s total).\n"
    )

    group_assignments = load_group_assignments()
    print(f"Loaded {len(group_assignments)} group assignments (A/B/C) from teams.json.\n")

    all_players: list[dict] = []
    letters = "abcdefghijklmnopqrstuvwxyz"

    for i, letter in enumerate(letters, 1):
        print(f"[{i:2}/26] /players/{letter}/ ...", end=" ", flush=True)
        try:
            players = scrape_letter(letter)
            all_players.extend(players)
            print(f"{len(players)} active players")
        except requests.RequestException as e:
            print(f"ERROR: {e}")
        except Exception as e:
            print(f"PARSE ERROR: {e}")

        if i < len(letters):
            time.sleep(CRAWL_DELAY)

    # Apply group assignments and MLB team/position
    no_match = 0
    for p in all_players:
        p["group"] = group_assignments.get(p["br_id"], "Wildcard")
        mlb = mlb_lookup.get(normalize(p["name"]), {})
        p["mlb_id"] = mlb.get("mlb_id", 0)
        p["team"]   = mlb.get("team", "")
        p["pos"]    = mlb.get("pos", "")
        if not mlb:
            no_match += 1

    # Deduplicate (shouldn't be needed but guard against it)
    seen: set[str] = set()
    unique: list[dict] = []
    for p in all_players:
        if p["br_id"] not in seen:
            seen.add(p["br_id"])
            unique.append(p)

    # Sort alphabetically by last name
    unique.sort(key=lambda p: p["name"].split()[-1] + p["name"])

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    out_path = DATA_DIR / "players_list.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"players": unique}, f, indent=2, ensure_ascii=False)

    group_counts = {}
    for p in unique:
        g = p["group"]
        group_counts[g] = group_counts.get(g, 0) + 1

    print(f"\nWrote {len(unique)} players to {out_path}")
    for g, count in sorted(group_counts.items()):
        print(f"  {g}: {count}")
    print(f"  ({no_match} players had no MLB Stats API match for team/position)")
    print("\nDone. Commit docs/data/players_list.json to the repo.")


if __name__ == "__main__":
    main()
