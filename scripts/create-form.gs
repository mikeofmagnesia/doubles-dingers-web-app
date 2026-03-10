/**
 * Doubles and Dingers 2025 — Google Form Creator
 *
 * Instructions:
 *  1. Go to script.google.com and create a new project
 *  2. Paste this entire file into the editor
 *  3. Click Run > createTeamEntryForm
 *  4. Grant the requested permissions when prompted
 *  5. Check the Execution Log for the form URL and sheet URL
 *  6. Copy the form URL into docs/index.html (replace GOOGLE_FORM_URL_HERE)
 *  7. Commit and push
 */

function createTeamEntryForm() {
  const SEASON = 2026;

  const form = FormApp.create(`Doubles and Dingers ${SEASON} — Team Entry`);

  form.setDescription(
    `Enter your Doubles and Dingers ${SEASON} team!\n\n` +
    'Rules:\n' +
    '  • Pick 1 player from each tier (Group A, B, and C)\n' +
    '  • Pick 4 Wildcard players — any active MLB hitter not in a group tier\n' +
    '  • No player can appear more than once on your team\n' +
    '  • One entry per person\n\n' +
    'Your score = combined doubles + home runs across all 7 players. ' +
    'Stats update daily at noon CDT.'
  );

  form.setCollectEmail(false);
  form.setLimitOneResponsePerUser(false);
  form.setShowLinkToRespondAgain(false);
  form.setConfirmationMessage(
    'Your team has been submitted! Stats will appear after the next daily update (noon CDT). ' +
    'Head to the leaderboard to track your team: https://dd.ericksonm.com'
  );

  // ── Identity ──────────────────────────────────────────────────────────────

  form.addTextItem()
    .setTitle('Your Name')
    .setHelpText('First and last name')
    .setRequired(true);

  form.addTextItem()
    .setTitle('Team Name')
    .setHelpText('Get creative — must be unique across all entries.')
    .setRequired(true);

  // ── Group Picks ───────────────────────────────────────────────────────────

  form.addSectionHeaderItem()
    .setTitle('Group Picks')
    .setHelpText('Select exactly one player from each group tier.');

  form.addMultipleChoiceItem()
    .setTitle('Group A — Pick One')
    .setRequired(true)
    .setChoiceValues([
      'Shohei Ohtani',
      'Aaron Judge',
      'Pete Alonso',
      'Cal Raleigh',
      'Freddie Freeman',
    ]);

  form.addMultipleChoiceItem()
    .setTitle('Group B — Pick One')
    .setRequired(true)
    .setChoiceValues([
      'Matt Olson',
      'Bryce Harper',
      'Fernando Tatis Jr.',
      'Vladimir Guerrero Jr.',
      'Kyle Schwarber',
    ]);

  form.addMultipleChoiceItem()
    .setTitle('Group C — Pick One')
    .setRequired(true)
    .setChoiceValues([
      'Bobby Witt Jr.',
      'José Ramírez',
      'Ronald Acuña Jr.',
      'Juan Soto',
      'Rafael Devers',
    ]);

  // ── Wildcard Picks ────────────────────────────────────────────────────────

  form.addSectionHeaderItem()
    .setTitle('Wildcard Picks (4 required)')
    .setHelpText(
      'Any active MLB hitter NOT in Groups A, B, or C qualifies as a wildcard. ' +
      'Enter each player\'s full name exactly as listed on Baseball Reference ' +
      '(e.g. "Yordan Alvarez", "Gunnar Henderson", "Manny Machado"). ' +
      'All four wildcards must be different players, and none can duplicate your group picks.'
    );

  ['Wildcard 1', 'Wildcard 2', 'Wildcard 3', 'Wildcard 4'].forEach(label => {
    form.addTextItem()
      .setTitle(label)
      .setHelpText('Full player name — e.g. Yordan Alvarez')
      .setRequired(true);
  });

  // ── Link to Google Sheet ──────────────────────────────────────────────────

  const sheet = SpreadsheetApp.create(`Doubles and Dingers ${SEASON} — Responses`);
  form.setDestination(FormApp.DestinationType.SPREADSHEET, sheet.getId());

  // ── Log output URLs ───────────────────────────────────────────────────────

  console.log('');
  console.log('=== SAVE THESE URLS ===');
  console.log('Form (share this with participants): ' + form.getPublishedUrl());
  console.log('Form (edit):                         ' + form.getEditUrl());
  console.log('Responses spreadsheet:               ' + sheet.getUrl());
  console.log('');
  console.log('Next step: paste the form URL into docs/index.html (replace GOOGLE_FORM_URL_HERE), then commit and push.');
}
