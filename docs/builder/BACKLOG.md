# Builder Improvement Backlog

This backlog tracks the next improvements for the static army builder in this repo.

Current baseline:

- Builder catalogs are generated from canonical faction JSON.
- Builder data health is currently clean: `0` missing-stat units and `0` manual-selection units.
- Static builder supports faction browse/search, roster totals, printable cards, browser persistence, and JSON import/export.

Use this file as the working queue. The intended approach is to take one item at a time from top to bottom unless priorities change.

## Priority Order

### 1. Wargear And Upgrade Modeling

Status: `next`

Goal:

- Represent real equipment choices per unit instead of only points/config rows.

Scope:

- Extend exported/normalized data so optional wargear, replacement weapons, and upgrade groups are structured.
- Update the builder UI so roster entries can choose legal loadout options.
- Persist those choices in saved rosters and reflect them in card rendering and print output.

Why this is next:

- It is the biggest gap between the current roster shell and a real list builder.
- Future legality checks depend on a more complete unit configuration model.

Done criteria:

- At least representative infantry, character, and vehicle units support structured wargear selection.
- Saved rosters round-trip those choices through local storage and JSON import/export.
- Preview and print output show the selected loadout, not only the default card text.

### 2. Rules-Aware Legality Checks

Status: `queued`

Goal:

- Validate that a roster is not just costed, but structurally legal enough to be useful.

Scope:

- Add detachment selection.
- Add duplicate limits, points-cap validation, leader attachment checks, and transport capacity checks.
- Surface legality issues in the builder without blocking roster editing.

Dependencies:

- Depends on item 1 for unit configuration fidelity.

Done criteria:

- Builder shows legal/illegal state for representative rosters.
- Invalid conditions are visible at roster and entry level.
- Saved/imported rosters preserve legality-relevant state.

### 3. Hosted Builder And CI Automation

Status: `queued`

Goal:

- Make the builder easy to access and keep regressions from slipping in.

Scope:

- Publish the static builder from `docs/`.
- Add CI for export validation, builder regression checks, and save/load tests.
- Fail CI when builder data health or roster persistence regressions appear.

Why this matters:

- It reduces manual verification and makes the builder usable without local setup.

Done criteria:

- Builder is accessible from a hosted static URL.
- CI runs on push/PR and covers Python tests, Node roster-store tests, and builder regression checks.

### 4. Advanced Browse And Filter UX

Status: `queued`

Goal:

- Make catalog exploration practical once roster complexity increases.

Scope:

- Add filters for keyword, faction keyword, unit role, points band, leaders, transports, aircraft, and epic heroes.
- Improve search relevance and quick roster-add workflows.

Dependencies:

- Independent of legality, but more valuable once rosters contain configured units.

Done criteria:

- Users can narrow large faction catalogs quickly without relying on plain text search.
- Filter state does not break saved-roster restore behavior.

### 5. Print And Export Polish

Status: `queued`

Goal:

- Improve the printable output from “works” to “presentation quality.”

Scope:

- Better roster summary pages.
- Cleaner multi-card print layouts.
- Optional faction-themed headers or styling that still stays generic enough for all factions.

Done criteria:

- Printed output includes roster context, totals, and configured unit summaries.
- Multi-page print layouts remain readable and do not duplicate broken entries.

### 6. Shareable Rosters

Status: `queued`

Goal:

- Let users send rosters to each other without passing raw files manually.

Scope:

- Add URL sharing only after the saved-roster schema stabilizes.
- Consider compressed roster payloads in the URL or a copyable encoded share string.

Dependencies:

- Should come after items 1 and 2 so the roster schema is mature enough to avoid churn.

Done criteria:

- A shared roster opens into the builder with the same faction, entries, and configuration state.
- Invalid or stale shared data degrades visibly instead of failing silently.

### 7. Broader Faction Coverage And Refresh Workflow

Status: `queued`

Goal:

- Expand the builder beyond the current six imported factions and keep data current.

Scope:

- Capture and validate more faction manifests.
- Add a repeatable refresh workflow so new exports and builder catalogs stay in sync.

Done criteria:

- New factions can be added through the existing export/build pipeline without builder-specific custom handling.
- Validation and builder regression reports remain clean as coverage expands.

## Operating Notes

- Treat `out/json` as the source of truth.
- Keep `out/builder` and `docs/builder/data` as derived runtime outputs.
- Avoid mixing multiple major features in one pass; each item above should land as its own focused implementation phase.
- Update this backlog after each completed phase so the next item becomes the active target.
