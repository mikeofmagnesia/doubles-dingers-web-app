"""
Doubles and Dingers - local team entry server.

Serves a team entry form at http://localhost:8765 and writes
valid submissions directly to data/teams.json.

Usage:
  python scripts/serve-form.py
  python scripts/serve-form.py --port 8080   # optional custom port

Press Ctrl+C to stop.
"""

import argparse
import json
import os
import sys
from difflib import get_close_matches
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT         = Path(__file__).parent.parent
TEAMS_FILE   = ROOT / "data" / "teams.json"
PLAYERS_FILE = ROOT / "docs" / "data" / "players_list.json"
PID_FILE     = Path("/tmp/dd-server.pid")

# ---------------------------------------------------------------------------
# HTML
# ---------------------------------------------------------------------------

HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Doubles & Dingers — Team Entry</title>
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: system-ui, sans-serif; background: #0f172a; color: #e2e8f0; min-height: 100vh; padding: 2rem 1rem; }
  .card { max-width: 560px; margin: 0 auto; background: #1e293b; border-radius: 12px; padding: 2rem; }
  h1 { font-size: 1.5rem; margin-bottom: 0.25rem; color: #f8fafc; }
  .subtitle { font-size: 0.875rem; color: #94a3b8; margin-bottom: 2rem; }
  label { display: block; font-size: 0.8rem; font-weight: 600; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 0.35rem; margin-top: 1.25rem; }
  input, select { width: 100%; padding: 0.6rem 0.75rem; border-radius: 6px; border: 1px solid #334155; background: #0f172a; color: #f1f5f9; font-size: 0.95rem; }
  input:focus, select:focus { outline: 2px solid #3b82f6; border-color: transparent; }
  .wc-group { display: grid; grid-template-columns: 1fr 1fr; gap: 0.75rem; }
  .autocomplete-wrap { position: relative; }
  .dropdown { position: absolute; top: 100%; left: 0; right: 0; background: #1e293b; border: 1px solid #334155; border-radius: 6px; max-height: 200px; overflow-y: auto; z-index: 10; display: none; }
  .dropdown.open { display: block; }
  .dropdown li { list-style: none; padding: 0.5rem 0.75rem; cursor: pointer; font-size: 0.9rem; }
  .dropdown li:hover, .dropdown li.active { background: #3b82f6; color: #fff; }
  .dropdown li small { opacity: 0.65; margin-left: 0.4rem; }
  button[type=submit] { margin-top: 2rem; width: 100%; padding: 0.75rem; background: #3b82f6; color: #fff; font-size: 1rem; font-weight: 600; border: none; border-radius: 6px; cursor: pointer; }
  button[type=submit]:hover { background: #2563eb; }
  #msg { margin-top: 1.25rem; padding: 0.75rem 1rem; border-radius: 6px; font-size: 0.9rem; display: none; }
  #msg.ok  { background: #166534; color: #bbf7d0; }
  #msg.err { background: #7f1d1d; color: #fecaca; }
  .section-label { margin-top: 1.5rem; font-size: 0.7rem; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; color: #475569; border-top: 1px solid #334155; padding-top: 1rem; }
</style>
</head>
<body>
<div class="card">
  <h1>Doubles &amp; Dingers</h1>
  <p class="subtitle">Team Entry &mdash; <span id="season-label">2026</span></p>

  <form id="form" autocomplete="off">
    <label for="owner_name">Your Name</label>
    <input id="owner_name" name="owner_name" type="text" placeholder="Mike Erickson" required>

    <label for="team_name">Team Name</label>
    <input id="team_name" name="team_name" type="text" placeholder="The Sluggers" required>

    <p class="section-label">Group Picks</p>

    <label for="group_a">Group A <span id="group-a-hint" style="font-weight:400;color:#64748b"></span></label>
    <select id="group_a" name="group_a" required></select>

    <label for="group_b">Group B <span id="group-b-hint" style="font-weight:400;color:#64748b"></span></label>
    <select id="group_b" name="group_b" required></select>

    <label for="group_c">Group C <span id="group-c-hint" style="font-weight:400;color:#64748b"></span></label>
    <select id="group_c" name="group_c" required></select>

    <p class="section-label">Wildcard Picks <span style="font-weight:400;color:#64748b">(4 players not in any group)</span></p>

    <div class="wc-group">
      <div><label>Wildcard 1</label><div class="autocomplete-wrap"><input class="wc" data-idx="0" type="text" placeholder="Player name"><ul class="dropdown"></ul></div></div>
      <div><label>Wildcard 2</label><div class="autocomplete-wrap"><input class="wc" data-idx="1" type="text" placeholder="Player name"><ul class="dropdown"></ul></div></div>
      <div><label>Wildcard 3</label><div class="autocomplete-wrap"><input class="wc" data-idx="2" type="text" placeholder="Player name"><ul class="dropdown"></ul></div></div>
      <div><label>Wildcard 4</label><div class="autocomplete-wrap"><input class="wc" data-idx="3" type="text" placeholder="Player name"><ul class="dropdown"></ul></div></div>
    </div>

    <!-- hidden br_id fields populated by autocomplete -->
    <input type="hidden" id="wc0" name="wc0">
    <input type="hidden" id="wc1" name="wc1">
    <input type="hidden" id="wc2" name="wc2">
    <input type="hidden" id="wc3" name="wc3">
    <!-- hidden name fields for display in server response -->
    <input type="hidden" id="wcn0" name="wcn0">
    <input type="hidden" id="wcn1" name="wcn1">
    <input type="hidden" id="wcn2" name="wcn2">
    <input type="hidden" id="wcn3" name="wcn3">
    <!-- hidden mlb_id fields -->
    <input type="hidden" id="wcm0" name="wcm0">
    <input type="hidden" id="wcm1" name="wcm1">
    <input type="hidden" id="wcm2" name="wcm2">
    <input type="hidden" id="wcm3" name="wcm3">

    <button type="submit">Submit Team</button>
    <div id="msg"></div>
  </form>
</div>

<script>
let groupIds = new Set();
let wildcardPlayers = [];
let selectedWc = [null, null, null, null];

async function loadData() {
  const [configRes, playersRes] = await Promise.all([
    fetch('/data/config'),
    fetch('/data/players'),
  ]);
  const config  = await configRes.json();
  const players = await playersRes.json();

  document.getElementById('season-label').textContent = config.season;

  // Populate group dropdowns
  ['A','B','C'].forEach(g => {
    const sel = document.getElementById('group_' + g.toLowerCase());
    sel.innerHTML = '<option value="">— pick one —</option>';
    config.groups[g].forEach(brId => {
      const p = config.players[brId];
      if (!p) return;
      const opt = document.createElement('option');
      opt.value = brId;
      opt.textContent = p.name;
      sel.appendChild(opt);
    });
    groupIds = new Set([...groupIds, ...config.groups[g]]);
  });

  // Build wildcard player list (exclude group-tier players)
  wildcardPlayers = players.filter(p => !groupIds.has(p.br_id));
}

// Autocomplete
document.querySelectorAll('.wc').forEach(input => {
  const idx      = parseInt(input.dataset.idx);
  const dropdown = input.nextElementSibling;
  let activeIdx  = -1;

  function clearSelection() {
    selectedWc[idx] = null;
    ['wc','wcn','wcm'].forEach(prefix => {
      document.getElementById(prefix + idx).value = '';
    });
  }

  input.addEventListener('input', () => {
    clearSelection();
    const q = input.value.trim().toLowerCase();
    if (q.length < 2) { dropdown.innerHTML = ''; dropdown.classList.remove('open'); return; }
    const matches = wildcardPlayers
      .filter(p => p.name.toLowerCase().includes(q))
      .slice(0, 12);
    if (!matches.length) { dropdown.innerHTML = ''; dropdown.classList.remove('open'); return; }
    dropdown.innerHTML = matches.map((p, i) =>
      `<li data-idx="${i}" data-br="${p.br_id}" data-name="${p.name}" data-mlb="${p.mlb_id}">
        ${p.name}<small>${p.team || ''} ${p.pos || ''}</small>
       </li>`
    ).join('');
    dropdown.classList.add('open');
    activeIdx = -1;
  });

  dropdown.addEventListener('click', e => {
    const li = e.target.closest('li');
    if (!li) return;
    select(li);
  });

  function select(li) {
    input.value = li.dataset.name;
    document.getElementById('wc'  + idx).value = li.dataset.br;
    document.getElementById('wcn' + idx).value = li.dataset.name;
    document.getElementById('wcm' + idx).value = li.dataset.mlb;
    selectedWc[idx] = li.dataset.br;
    dropdown.innerHTML = '';
    dropdown.classList.remove('open');
  }

  input.addEventListener('keydown', e => {
    const items = dropdown.querySelectorAll('li');
    if (e.key === 'ArrowDown') { e.preventDefault(); activeIdx = Math.min(activeIdx+1, items.length-1); items.forEach((el,i) => el.classList.toggle('active', i===activeIdx)); }
    if (e.key === 'ArrowUp')   { e.preventDefault(); activeIdx = Math.max(activeIdx-1, 0); items.forEach((el,i) => el.classList.toggle('active', i===activeIdx)); }
    if (e.key === 'Enter' && activeIdx >= 0) { e.preventDefault(); select(items[activeIdx]); }
    if (e.key === 'Escape') { dropdown.classList.remove('open'); }
  });

  document.addEventListener('click', e => {
    if (!input.contains(e.target) && !dropdown.contains(e.target)) dropdown.classList.remove('open');
  });
});

// Submit
document.getElementById('form').addEventListener('submit', async e => {
  e.preventDefault();
  const msg = document.getElementById('msg');
  msg.style.display = 'none';

  const body = Object.fromEntries(new FormData(e.target));
  const res  = await fetch('/submit', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(body) });
  const data = await res.json();

  msg.style.display = 'block';
  if (res.ok) {
    msg.className = 'ok';
    msg.textContent = data.message;
    e.target.reset();
    selectedWc = [null,null,null,null];
    // Re-populate selects (reset clears them)
    loadData();
  } else {
    msg.className = 'err';
    msg.textContent = data.error;
  }
  msg.scrollIntoView({ behavior: 'smooth' });
});

loadData();
</script>
</body>
</html>
"""

# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

def load_teams():
    with open(TEAMS_FILE) as f:
        return json.load(f)

def load_players():
    with open(PLAYERS_FILE) as f:
        return json.load(f)["players"]

def validate_and_save(body: dict) -> tuple[int, dict]:
    owner_name = body.get("owner_name", "").strip()
    team_name  = body.get("team_name",  "").strip()
    group_a    = body.get("group_a",    "").strip()
    group_b    = body.get("group_b",    "").strip()
    group_c    = body.get("group_c",    "").strip()
    wc_ids     = [body.get(f"wc{i}",  "").strip() for i in range(4)]
    wc_names   = [body.get(f"wcn{i}", "").strip() for i in range(4)]
    wc_mlbs    = [int(body.get(f"wcm{i}", 0) or 0) for i in range(4)]

    if not owner_name:
        return 400, {"error": "Owner name is required."}
    if not team_name:
        return 400, {"error": "Team name is required."}
    if not group_a:
        return 400, {"error": "Select a Group A player."}
    if not group_b:
        return 400, {"error": "Select a Group B player."}
    if not group_c:
        return 400, {"error": "Select a Group C player."}
    if any(not wid for wid in wc_ids):
        return 400, {"error": "Select all 4 Wildcard players."}

    config = load_teams()

    groups_a = set(config["groups"]["A"])
    groups_b = set(config["groups"]["B"])
    groups_c = set(config["groups"]["C"])
    all_group_ids = groups_a | groups_b | groups_c

    if group_a not in groups_a:
        return 400, {"error": f"Invalid Group A pick."}
    if group_b not in groups_b:
        return 400, {"error": f"Invalid Group B pick."}
    if group_c not in groups_c:
        return 400, {"error": f"Invalid Group C pick."}

    for i, wid in enumerate(wc_ids):
        if wid in all_group_ids:
            return 400, {"error": f"Wildcard {i+1} ({wc_names[i]}) is a group-tier player and can't be a wildcard."}

    all_ids = [group_a, group_b, group_c] + wc_ids
    if len(set(all_ids)) != len(all_ids):
        return 400, {"error": "A player cannot appear more than once on your team."}

    existing = {t["team_name"].strip().lower() for t in config.get("teams", [])}
    if team_name.lower() in existing:
        return 400, {"error": f'A team named "{team_name}" already exists.'}

    # Add any new wildcard players to the players dict
    if "players" not in config:
        config["players"] = {}
    for i, wid in enumerate(wc_ids):
        if wid not in config["players"]:
            letter = wid[0]
            config["players"][wid] = {
                "name":   wc_names[i],
                "group":  "Wildcard",
                "mlb_id": wc_mlbs[i],
                "br_url": f"https://www.baseball-reference.com/players/{letter}/{wid}.shtml",
            }

    # Append team
    if "teams" not in config:
        config["teams"] = []
    config["teams"].append({
        "owner":     owner_name,
        "team_name": team_name,
        "players":   all_ids,
    })

    with open(TEAMS_FILE, "w") as f:
        json.dump(config, f, indent=2)

    return 200, {"message": f'Team "{team_name}" saved! Add another team or close this tab when done.'}

# ---------------------------------------------------------------------------
# Request handler
# ---------------------------------------------------------------------------

class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print(f"  {self.address_string()} {fmt % args}")

    def send_json(self, status: int, data: dict):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlparse(self.path).path

        if path == "/" or path == "/index.html":
            body = HTML.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", len(body))
            self.end_headers()
            self.wfile.write(body)

        elif path == "/data/config":
            config = load_teams()
            self.send_json(200, config)

        elif path == "/data/players":
            players = load_players()
            self.send_json(200, players)

        else:
            self.send_json(404, {"error": "Not found"})

    def do_POST(self):
        if self.path != "/submit":
            self.send_json(404, {"error": "Not found"})
            return

        length = int(self.headers.get("Content-Length", 0))
        raw    = self.rfile.read(length)
        try:
            body = json.loads(raw)
        except Exception:
            self.send_json(400, {"error": "Invalid JSON"})
            return

        status, result = validate_and_save(body)
        self.send_json(status, result)

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    # Write PID for the skill to use when stopping
    PID_FILE.write_text(str(os.getpid()))

    server = HTTPServer(("127.0.0.1", args.port), Handler)
    print(f"\n  Doubles & Dingers — Team Entry Server")
    print(f"  Open in your browser: http://localhost:{args.port}")
    print(f"  Press Ctrl+C to stop.\n")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        PID_FILE.unlink(missing_ok=True)
        print("\n  Server stopped.")

if __name__ == "__main__":
    main()
