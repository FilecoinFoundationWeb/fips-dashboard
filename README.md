# Filecoin Governance Hub

🔗 **Live:** [Overview](https://thatguyllc.github.io/fips-dashboard/) · [FIPs](https://thatguyllc.github.io/fips-dashboard/fips-dashboard-static.html) · [Core Devs](https://thatguyllc.github.io/fips-dashboard/core-devs.html) · [Upgrades](https://thatguyllc.github.io/fips-dashboard/network-upgrades.html) · [Timeline](https://thatguyllc.github.io/fips-dashboard/fips-timeline-tracker.html)

One place to keep up with Filecoin governance. It pulls the public records in [filecoin-project/FIPs](https://github.com/filecoin-project/FIPs) and [filecoin-project/core-devs](https://github.com/filecoin-project/core-devs) into a readable site: proposals and their status, Core Devs meetings with recordings and notes, network upgrades, and open discussions. It's read-only. It never changes a status, assigns a number or decides an outcome; that stays with the process in [FIP-0001](https://github.com/filecoin-project/FIPs/blob/master/FIPS/fip-0001.md).

## What it shows

**Overview** (`index.html`)
- The latest Core Devs meeting: topics, FIPs mentioned, recording (playable in the page for YouTube), notes and agenda.
- **Open now**: Last Calls in progress, the next meeting's agenda issue and any scheduled upgrade.
- **Recent activity**: a 90-day feed of FIP status changes, meetings, upgrade activations and new FIP discussions.
- Most recently active FIP discussions, and links for getting involved.

**Core Devs** (`core-devs.html`)
- Latest meeting in detail, and **FIPs on the agenda**: every FIP mentioned in the last 6 meetings' notes, how often, when it was last discussed and whether it has shipped. Mentions are shown as discussion, not decisions.
- A searchable archive of every meeting (filter by FIP number, meeting number or topic) with recording, notes or slides, and agenda links.

**Upgrades** (`network-upgrades.html`)
- Every network upgrade from `upgrades.json`: mainnet and calibration dates, epoch, actors version, included FIPs and the upgrade write-up.
- **Accepted, not yet in an upgrade**: Accepted FIPs not listed in any upgrade, with when Core Devs last discussed them.

**FIPs** (`fips-dashboard-static.html`)
- **Last Call**: FIPs currently in Last Call, when they entered, when the review period ends (`review-period-end` from the FIP file, or the FIP-0001 default of 14 days, marked *est.*) and where to comment. Past Last Calls with their outcome and duration.
- **In flight**: Draft, Last Call, Accepted and Deferred FIPs that changed status in the last year, with the date, time since and when Core Devs last discussed them. Longer-running ones are only counted in a footnote (they still appear under All FIPs by status).
- **Consistency check**: FIPs where the README table and the FIP's own `status:` line disagree, or that appear in only one of them. Flagged for editors; the dashboard doesn't say which is right.
- **Open pull requests**: matched to FIPs by the files they change, with review state (approved, changes requested, awaiting review, draft) and days since last activity.
- **All FIPs by status**, with open-PR counts.

**Timeline** (`fips-timeline-tracker.html`)
- Every status change in the README, dated by commit and linked to it, back to December 2020.
- A count of transitions (e.g. Draft → Last Call) over the last 24 months.

**Internal report** (not published)
- `python3 internal_report.py` writes `internal/fips-internal-report.html`: every in-flight FIP with its full time in status and authors, the complete Last Call history, the consistency check and PRs idle 30+ days. `internal/` is gitignored and the workflow never commits it, so it stays off GitHub Pages. Share the file directly.

## How it works

The scripts clone `filecoin-project/FIPs` (about 25 MB) and `filecoin-project/core-devs` and read them locally: the FIPs README table and its full git history, each FIP file's front matter, the core-devs meetings table, meeting notes and `upgrades.json`. Only open PRs, FIP discussions and open agenda issues come from the GitHub API; if those calls fail, the pages still build and say what's missing. Everything is Python standard library; no `pip install` needed.

| File | Purpose |
|---|---|
| `fip_utils.py` | Parsing (README table across its historical layouts, FIP front matter), git history, status timeline, Last Call windows, PR matching and review state |
| `core_devs.py` | Core Devs meetings (README table + notes), recordings, FIP mentions, network upgrades, open agenda issues |
| `generate_hub.py` | Builds `index.html`, `core-devs.html` and `network-upgrades.html` |
| `theme.py` | Shared page shell: navigation, Filecoin colors, Archivo font, light/dark mode, the corgi |
| `generate_fips_dashboard.py` | Builds `fips-dashboard-static.html` |
| `fips_timeline_tracker.py` | Builds `fips-timeline-tracker.html` |
| `fetch_fip_prs.py` | Prints open PRs and review state to the terminal |
| `internal_report.py` | Builds the unpublished internal report in `internal/` |

## Usage

```bash
python3 generate_fips_dashboard.py
python3 fips_timeline_tracker.py
python3 generate_hub.py
python3 -m http.server 8000   # then open http://localhost:8000/
```

Optional environment variables:
- `GITHUB_TOKEN`: raises the GitHub API rate limit for PR and review lookups.
- `FIPS_REPO_DIR`, `CORE_DEVS_REPO_DIR`: paths to existing clones to reuse between runs.

If the PR lookup fails (rate limit, network), the dashboard still builds and shows a notice in the PR section instead of claiming there are no PRs.

## Auto-update

`.github/workflows/update-dashboard.yml` rebuilds all five pages every 6 hours, on manual dispatch, and on pushes to `master` that change the scripts. See [PUBLISHING_GUIDE.md](PUBLISHING_GUIDE.md) for hosting options.

## Notes

- Status dates are when the README table showed the change, which can lag the decision itself by a few days.
- Core Devs topics come from each meeting's Agenda section (or its headings for older notes). Meetings whose notes are slides only show links, not topics.
- The README table only goes back to December 2020; FIPs whose status hasn't changed since then show that date as a floor.
- Colors use the public Filecoin palette (Filecoin Blue `#0090FF`, Filecoin Dark `#091B2A`) and Filecoin Foundation's Archivo typeface. Tokens are at the top of `theme.py` if the official brand guide differs.
- The corgi chases a FIP tennis ball, and it's clickable.

## License

This dashboard is provided as-is for tracking Filecoin Improvement Proposals. Unofficial community tool.
