# Ohio Election Atlas

An interactive Ohio election atlas for exploring county, congressional, state house, and state senate results across multiple cycles.

The project is built to answer a few practical questions quickly:

- Where is each party actually strong, and how strong is that strength?
- Which places are stable anchors versus recurring battlegrounds?
- How do statewide races look when they are re-aggregated into current or alternate district lines?
- Where do downballot and top-of-ticket patterns split apart?

## What You'll Find

The atlas is designed for people who want more than a red-blue snapshot.

- County-level election history for statewide and federal races.
- District-level re-aggregations for congressional, state house, and state senate maps.
- Alternate line years, including 2022, 2024, and 2026 congressional lines.
- Contest-by-contest comparisons that make it easier to spot ticket-splitting, regional drift, and structural partisan advantages.
- Hover and detail views that surface vote totals, margin, winner, and trend context.

In practice, most visitors will probably use it to look for:

- The suburban rings around Columbus, Cincinnati, Cleveland, Dayton, Akron, and Toledo.
- Appalachian and river counties that behave differently from the metros.
- Lake Erie shoreline counties that can swing harder than the rest of northern Ohio.
- Places where statewide Democrats remain competitive even when district lines are structurally Republican.
- Legislative districts that look safer or shakier than their statewide reputation suggests.

## Margin Categories

The atlas uses named margin bands rather than only raw percentages. These are based on the absolute Democratic-Republican margin.

| Category | Margin |
| --- | --- |
| `Tossup` | under `0.50%` |
| `Tilt` | `0.50%` to `0.99%` |
| `Lean` | `1.00%` to `5.49%` |
| `Likely` | `5.50%` to `9.99%` |
| `Safe` | `10.00%` to `19.99%` |
| `Stronghold` | `20.00%` to `29.99%` |
| `Dominant` | `30.00%` to `39.99%` |
| `Annihilation` | `40.00%` and up |

The party label is attached to the category name. For example:

- `Safe Republican` means the Republican candidate leads by `10.00%` to `19.99%`.
- `Lean Democratic` means the Democratic candidate leads by `1.00%` to `5.49%`.
- `Tossup (Republican Win)` means Republicans won, but by less than `0.50%`.

## How To Read The Map

The colors are meant to do two things at once:

- Hue shows which party is ahead.
- Intensity shows how large that lead is.

That means a pale district is not just "close" in a general sense. It is close within a specific competitiveness bucket. Darker shades indicate bigger cushions; lighter shades indicate more fragile control.

This matters because Ohio has a lot of places that are not tossups, but are still politically meaningful:

- `Tilt` and `Lean` areas are the first places to flip when the environment changes.
- `Likely` and `Safe` areas often decide whether a good year becomes a wave.
- `Stronghold`, `Dominant`, and `Annihilation` zones show where each party is banking raw margin.

## What The Atlas Is Good For

- Comparing the same contest across different map types.
- Understanding whether a district is naturally competitive or only appears that way because of line-drawing.
- Finding the counties and districts that consistently overperform or underperform a party's statewide baseline.
- Identifying where Ohio's political geography has hardened and where it still moves.
- Seeing how presidential, senate, gubernatorial, and judicial races diverge from one another.

## Notes

- District results are aggregated from precinct-level inputs wherever available.
- Precinct overlays now have their own prebuilt precinct-contest JSON payloads under `data/precinct_contests`, so county-view precinct coloring can load actual precinct election results directly.
- The 2022 state house and state senate carryover files are now rebuilt against the 2022 Census legislative geometries, rather than the older 2020 legislative shapes.
- Older statewide contests on congressional, state house, and state senate views now use historical `vtd10` geometry-based carryover crosswalks where available, which sharply reduces dropped precincts in 2010-2020 district reaggregations.
- Some views compare older elections against newer line vintages so users can inspect how the same electorate would map onto different districts.
- The atlas intentionally emphasizes margin structure and geography, not just who won.
