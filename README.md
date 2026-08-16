# Custom IPTV-org US EPG for TiviMate

This project builds a **custom XMLTV EPG whose channel IDs are rewritten to match the `tvg-id` values in IPTV-org's U.S. playlist**.

It combines:

- IPTV-org U.S. playlist: `https://iptv-org.github.io/iptv/countries/us.m3u`
- EPGShare US2
- EPGShare US Locals

The script only accepts conservative matches, then rewrites each matched XMLTV `<channel id>` and each `<programme channel>` to the corresponding IPTV-org `tvg-id`.

## What gets generated

- `public/guide.xml.gz` — the TiviMate EPG
- `public/match_report.csv` — every automatic match and its method
- `public/unmatched_channels.csv` — channels that were deliberately left unmatched
- `public/status.txt` — quick coverage count

## Fastest setup

1. Create a **public GitHub repository**.
2. Upload all files from this package, preserving the `.github/workflows/` folder.
3. Commit them to the `main` branch.
4. Open **Actions → Build Custom US EPG → Run workflow**.
5. Wait for the run to finish. The workflow will commit the generated `public/` files back to the repo.
6. In TiviMate, add this EPG source:

   `https://raw.githubusercontent.com/YOUR_GITHUB_USERNAME/YOUR_REPOSITORY/main/public/guide.xml.gz`

7. Assign that EPG source to the IPTV-org U.S. playlist and update EPG.

The workflow refreshes the guide once a day.

## Why this should beat a generic EPG source

TiviMate's automatic EPG mapping depends heavily on channel identifiers. A generic provider can have perfectly good listings but use different XMLTV IDs. This builder deliberately changes the output IDs to IPTV-org's `tvg-id` values after finding a safe source match.

## Important

This is intentionally conservative. It is better to leave a channel unmatched than to attach the wrong programming schedule.

After the first GitHub Actions run, open `public/status.txt` and `public/match_report.csv` to see exactly how much coverage was achieved. If coverage is still too low, the matcher can be expanded with additional guide sources or a reviewed alias table without changing the URL used by TiviMate.
