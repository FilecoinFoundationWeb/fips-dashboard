#!/usr/bin/env python3
"""Print a summary of open FIPs PRs, their subject FIPs and review state.

The fetching and matching logic lives in fip_utils so the dashboard and this
script always agree.
"""

import fip_utils as u


def main():
    print('Fetching open PRs from GitHub...')
    processed = u.process_prs(u.fetch_open_prs())
    grouped = u.prs_by_fip(processed)
    print(f'{len(processed)} FIP-related PR(s) across {len([k for k in grouped if k != "General"])} FIP(s)\n')
    for key in sorted(grouped, key=lambda k: (k == 'General', k)):
        label = key if key == 'General' else f'FIP-{key}'
        print(label)
        for pr in grouped[key]:
            print(f"  #{pr['number']:<5} {pr['review']:<18} idle {pr['idle_days']:>4}d  {pr['title'][:70]}")
    return {'prs': processed, 'prs_by_fip': {k: len(v) for k, v in grouped.items()}, 'total_prs': len(processed)}


if __name__ == '__main__':
    main()
