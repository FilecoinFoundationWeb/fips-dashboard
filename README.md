# Filecoin Improvement Proposals (FIPs) Dashboard

🔗 **Live:** [Dashboard](https://thatguyllc.github.io/fips-dashboard/fips-dashboard-static.html) · [Timeline](https://thatguyllc.github.io/fips-dashboard/fips-timeline-tracker.html) · [thatguyllc.github.io/fips-dashboard](https://thatguyllc.github.io/fips-dashboard/)

A read-only dashboard for the [Filecoin Improvement Proposals](https://github.com/filecoin-project/FIPs) process. It surfaces where every FIP stands and what is waiting on someone, so authors and FIP editors can spot things faster. It never changes a status, assigns a number or decides an outcome; that stays with the process in [FIP-0001](https://github.com/filecoin-project/FIPs/blob/master/FIPS/fip-0001.md).

## What it shows

**Dashboard** (`fips-dashboard-static.html`)
- **Last Call**: FIPs currently in Last Call, when they entered, when the review period ends (`review-period-end` from the FIP file, or the FIP-0001 default of 14 days, marked *est.*) and where to comment. Past Last Calls with their outcome and duration.
- **In flight**: every Draft, Last Call, Accepted and Deferred FIP with the date it entered that status and how long it has been there, longest-waiting first.
- **Consistency check**: FIPs where the README table and the FIP's own `status:` line disagree, or that appear in only one of them. Flagged for editors; the dashboard doesn't say which is right.
- **Open pull requests**: matched to FIPs by the files they change, with review state (approved, changes requested, awaiting review, draft) and days since last activity.
- **All FIPs by status**, with open-PR counts.

**Timeline** (`fips-timeline-tracker.html`)
- Every status change in the README, dated by commit and linked to it, back to December 2020.
- A count of transitions (e.g. Draft → Last Call) over the last 24 months.

## How it works

The scripts clone `filecoin-project/FIPs` (about 25 MB) and read the README table, its full git history and each FIP file's front matter locally. Only pull-request data comes from the GitHub API. Everything is Python standard library; no `pip install` needed.

| File | Purpose |
|---|---|
| `fip_utils.py` | Parsing (README table across its historical layouts, FIP front matter), git history, status timeline, Last Call windows, PR matching and review state |
| `theme.py` | Shared page shell: Filecoin colors, Archivo font, light/dark mode, the corgi |
| `generate_fips_dashboard.py` | Builds `fips-dashboard-static.html` |
| `fips_timeline_tracker.py` | Builds `fips-timeline-tracker.html` |
| `fetch_fip_prs.py` | Prints open PRs and review state to the terminal |

## Usage

```bash
python3 generate_fips_dashboard.py
python3 fips_timeline_tracker.py
python3 -m http.server 8000   # then open http://localhost:8000/
```

Optional environment variables:
- `GITHUB_TOKEN`: raises the GitHub API rate limit for PR and review lookups.
- `FIPS_REPO_DIR`: path to an existing FIPs clone to reuse between runs.

If the PR lookup fails (rate limit, network), the dashboard still builds and shows a notice in the PR section instead of claiming there are no PRs.

## Auto-update

`.github/workflows/update-dashboard.yml` rebuilds both pages every 6 hours, on manual dispatch, and on pushes to `master` that change the scripts. See [PUBLISHING_GUIDE.md](PUBLISHING_GUIDE.md) for hosting options.

## Notes

- Status dates are when the README table showed the change, which can lag the decision itself by a few days.
- The README table only goes back to December 2020; FIPs whose status hasn't changed since then show that date as a floor.
- Colors use the public Filecoin palette (Filecoin Blue `#0090FF`, Filecoin Dark `#091B2A`) and Filecoin Foundation's Archivo typeface. Tokens are at the top of `theme.py` if the official brand guide differs.
- The corgi is clickable.

## License

This dashboard is provided as-is for tracking Filecoin Improvement Proposals. Unofficial community tool.
