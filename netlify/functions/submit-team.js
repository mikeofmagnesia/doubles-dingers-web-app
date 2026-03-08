/**
 * Doubles and Dingers - team submission handler.
 *
 * Receives a validated team from the entry form, then uses the GitHub
 * Contents API to append the team to data/teams.json in the repo.
 *
 * Required Netlify environment variables:
 *   GITHUB_TOKEN  - fine-grained PAT with "Contents: Read and write" on this repo
 *   GITHUB_OWNER  - GitHub username or org that owns the repo
 *   GITHUB_REPO   - repository name (e.g. "doubles-and-dingers")
 */

const GITHUB_API = "https://api.github.com";
const FILE_PATH  = "data/teams.json";

// ---------------------------------------------------------------------------
// GitHub helpers
// ---------------------------------------------------------------------------

function ghHeaders() {
  return {
    Authorization: `Bearer ${process.env.GITHUB_TOKEN}`,
    Accept: "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
    "Content-Type": "application/json",
  };
}

async function getFile() {
  const owner = process.env.GITHUB_OWNER;
  const repo  = process.env.GITHUB_REPO;
  const res = await fetch(
    `${GITHUB_API}/repos/${owner}/${repo}/contents/${FILE_PATH}`,
    { headers: ghHeaders() }
  );
  if (!res.ok) {
    throw new Error(`GitHub GET failed: ${res.status} ${await res.text()}`);
  }
  const data = await res.json();
  const content = JSON.parse(Buffer.from(data.content, "base64").toString("utf-8"));
  return { content, sha: data.sha };
}

async function putFile(content, sha, message) {
  const owner = process.env.GITHUB_OWNER;
  const repo  = process.env.GITHUB_REPO;
  const encoded = Buffer.from(JSON.stringify(content, null, 2)).toString("base64");
  const res = await fetch(
    `${GITHUB_API}/repos/${owner}/${repo}/contents/${FILE_PATH}`,
    {
      method: "PUT",
      headers: ghHeaders(),
      body: JSON.stringify({ message, content: encoded, sha }),
    }
  );
  if (!res.ok) {
    throw new Error(`GitHub PUT failed: ${res.status} ${await res.text()}`);
  }
}

// ---------------------------------------------------------------------------
// Response helpers
// ---------------------------------------------------------------------------

function ok(body) {
  return {
    statusCode: 200,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  };
}

function err(statusCode, message) {
  return {
    statusCode,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ error: message }),
  };
}

// ---------------------------------------------------------------------------
// Handler
// ---------------------------------------------------------------------------

exports.handler = async function (event) {
  if (event.httpMethod !== "POST") {
    return err(405, "Method Not Allowed");
  }

  // --- Parse body ---
  let body;
  try {
    body = JSON.parse(event.body);
  } catch {
    return err(400, "Invalid JSON body.");
  }

  const { owner_name, team_name, group_a, group_b, group_c, wildcards } = body;

  // --- Basic presence checks ---
  if (!owner_name?.trim())        return err(400, "Owner name is required.");
  if (!team_name?.trim())         return err(400, "Team name is required.");
  if (!group_a?.br_id)            return err(400, "Select a Group A player.");
  if (!group_b?.br_id)            return err(400, "Select a Group B player.");
  if (!group_c?.br_id)            return err(400, "Select a Group C player.");
  if (!Array.isArray(wildcards) || wildcards.length !== 4) {
    return err(400, `Select exactly 4 Wildcard players (received ${wildcards?.length ?? 0}).`);
  }
  if (wildcards.some(w => !w?.br_id || !w?.name)) {
    return err(400, "One or more wildcard players is missing data.");
  }

  // --- No duplicate players ---
  const allIds = [group_a.br_id, group_b.br_id, group_c.br_id, ...wildcards.map(w => w.br_id)];
  if (new Set(allIds).size !== allIds.length) {
    return err(400, "A player cannot appear more than once on your team.");
  }

  // --- Read current teams.json from GitHub ---
  let teamsData, sha;
  try {
    ({ content: teamsData, sha } = await getFile());
  } catch (e) {
    console.error("GitHub read error:", e);
    return err(502, "Could not read the team config. Please try again.");
  }

  // --- Validate group assignments against configured groups ---
  const groupA = new Set(teamsData.groups?.A ?? []);
  const groupB = new Set(teamsData.groups?.B ?? []);
  const groupC = new Set(teamsData.groups?.C ?? []);
  const allGroupIds = new Set([...groupA, ...groupB, ...groupC]);

  if (!groupA.has(group_a.br_id)) {
    return err(400, `${group_a.name} is not in Group A.`);
  }
  if (!groupB.has(group_b.br_id)) {
    return err(400, `${group_b.name} is not in Group B.`);
  }
  if (!groupC.has(group_c.br_id)) {
    return err(400, `${group_c.name} is not in Group C.`);
  }
  for (const w of wildcards) {
    if (allGroupIds.has(w.br_id)) {
      return err(400, `${w.name} is in a group tier (A/B/C) and cannot be a Wildcard pick.`);
    }
  }

  // --- Team name uniqueness ---
  const existingNames = new Set(
    (teamsData.teams ?? []).map(t => t.team_name.trim().toLowerCase())
  );
  if (existingNames.has(team_name.trim().toLowerCase())) {
    return err(400, `A team named "${team_name}" already exists. Choose a different name.`);
  }

  // --- Add any new players to the players dict so the scraper will track them ---
  if (!teamsData.players) teamsData.players = {};

  const allPlayers = [
    { ...group_a, group: "A" },
    { ...group_b, group: "B" },
    { ...group_c, group: "C" },
    ...wildcards.map(w => ({ ...w, group: "Wildcard" })),
  ];

  for (const p of allPlayers) {
    if (!teamsData.players[p.br_id]) {
      const letter = p.br_id[0];
      teamsData.players[p.br_id] = {
        name:   p.name,
        group:  p.group,
        br_url: `https://www.baseball-reference.com/players/${letter}/${p.br_id}.shtml`,
      };
    }
  }

  // --- Append the new team ---
  if (!teamsData.teams) teamsData.teams = [];
  teamsData.teams.push({
    owner:     owner_name.trim(),
    team_name: team_name.trim(),
    players:   allIds,
  });

  // --- Commit back to GitHub ---
  try {
    await putFile(
      teamsData,
      sha,
      `Add team: ${team_name.trim()} (${owner_name.trim()})`
    );
  } catch (e) {
    console.error("GitHub write error:", e);
    return err(502, "Failed to save your team. Please try again.");
  }

  return ok({ message: `Team "${team_name.trim()}" submitted! Stats will appear after the next daily update.` });
};
