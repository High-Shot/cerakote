# Cerakote Ops site: Monday and Thursday refresh

Runs Monday and Thursday at 08:45 CT as a scheduled task, after the two data pipelines:

| Time (CT, Mon + Thu) | Task | Repo it updates |
|---|---|---|
| 06:30 | INTL health tracker run (account health, cases, stock, Q4 projection), labeled with the reporting week | High-Shot/INTL |
| 07:00 | NIC sales tracker run (week ending last Sunday; Thursday re-runs it with settled sessions + NTB) | High-Shot/NIC |
| 08:45 | **This runbook**: budget read, spend pull, site build, publish | High-Shot/cerakote |

Live: https://high-shot.github.io/cerakote/ (sales/, health/, inventory/). The old URLs (high-shot.github.io/NIC/, /INTL/, /INTL/q4/) keep updating from the pipelines.
Mac clone: `~/Documents/Claude/Projects/Cerakote Management/cerakote-site` (gh logged in as High-Shot there). Never pause to ask a question; a failed step must not stop the run.

## 1. Setup (cloud shell)
```
cd /home/claude
git clone https://github.com/High-Shot/cerakote.git
git clone --depth 1 https://github.com/High-Shot/NIC.git
git clone --depth 1 https://github.com/High-Shot/INTL.git
cd cerakote
```
Note the latest commit date of NIC and INTL (`git -C ../NIC log -1 --format=%ci`). If either is older than today, the pipeline run has not pushed yet: build anyway and say so in the summary.

## 2. Pacing window
NIC weeks run Monday to Sunday; the week is reviewed on Thursday. THROUGH = the Sunday that just ended (`date -d 'last sunday' +%F`), on both runs: Monday builds it, Thursday re-pulls the same window after attribution settles.
MONTH = the month of THROUGH. If the reporting week crosses into a new month, also redo last month through its last day (steps 3-4) so every month closes on its full spend, and pace the new month from the 1st through THROUGH.

## 3. Budgets (Google Sheet NIC_Monthly_Budgets, id `1v5zGlPoNPcl0qKaxbsNyyfMfDvIpJSNkJWZuSYmkYYI`)
`mcp__Google_Drive__read_file_content` on that id. Find the tab for MONTH: the tab name is the month's full name or its first 3-4 letters (July, August, Sept, Oct ...). Read column C ("Total ... Budget") for each Sales Channel row. The tab's header row may carry a stale month name in column C (the Sept tab says "Total August Budget"); go by the tab name, not the header.
```
python3 scripts/pacing.py budget $MONTH --tab "<tab name>" CC_US=<n> CC_CA=<n> CC_UK=<n> CC_AUS=<n> CC_DE=<n> CC_FR=<n> CC_ES=<n> CC_IT=<n> CC_NL=<n> CC_SA=<n> CL_US=<n> PP_US=<n>
```
Channel map (sheet -> key) is in `scripts/pacing.py`. Plain numbers, no currency symbols, each in the channel's own currency.
No tab for MONTH yet: skip this step and do not write a file. The Sales page then shows spend with "budgets not in the sheet yet". Say so in the summary.

## 4. Spend, 1st of MONTH through THROUGH
- Scale Insights, Cerakote Auto US, CA, UK, DE, FR, IT, ES, NL, AU: `mcp__Scale_Insights__get_campaign_performance` with `country, start_date, end_date, mode: "raw", count: 1, sort_by: "cost"`; use `agg.TotalSpend`. (AU key is CC_AUS.)
- Helium10, CL_US / PP_US / CC_SA: from the shared H10 cache, NEVER a Helium10 call. On the Mac (Desktop Commander `start_process` or osascript `do shell script`): `/opt/homebrew/bin/python3 "$HOME/Documents/Claude/Projects/Cerakote Management/h10-cache/bin/query.py" spend <1st of MONTH> <THROUGH> CL_US PP_US CC_SA`. It prints the cache run date and the summed daily `advertising_cost` per tab (CC_SA in SAR). A tab printed as `n/a` (THROUGH after the cache's last day, or cache missing) is left out and flagged; never estimate it. Cache spec: `Cerakote Management/h10-cache/README.md`.
```
python3 scripts/pacing.py spend $MONTH $THROUGH CC_US=<n>:si CC_CA=<n>:si ... CL_US=<n>:h10 PP_US=<n>:h10 CC_SA=<n>:h10
```
Never estimate a missing channel; leave it out and flag it.
Source check (2026-09-28): Scale Insights matched the sheet's Ads-export spend within 0.2% on all nine Cerakote Auto markets. Helium10 matches Amazon's Reports Beta spend to the cent, but NOT the sheet for CL_US (-15%), PP_US (+8%) and CC_SA (+14%) over Sept 1-26. The sheet's figures for those three are the suspect ones (unconfirmed).

## 4b. Ad-change markers (Scale Insights change history)
For each Cerakote Auto market (US, CA, UK, DE, FR, IT, ES, NL, AU), `mcp__Scale_Insights__get_change_history` for THROUGH-6 to THROUGH; read TotalChanges split into manual and automation. Then:
```
python3 scripts/changes.py counts $THROUGH US=<manual>:<auto> CA=<m>:<a> UK=... DE=... FR=... IT=... ES=... NL=... AU=...
```
Budget changes: filter the same call to budget changes; for each market that has any, save the tool result JSON and run `python3 scripts/changes.py budget <CC> <file>` (dedupes). Only changes made in Scale Insights show up; changes made in the Amazon console do not. The Sales trend charts draw a dashed "changes" line on weeks with a budget change, or with manual changes at 2x the median and 50+.
Skip on failure; the charts just show no marker for that week.

## 4c. Weekly budget (Cerakote Auto rolling 6-week bucket, `data/weekly/`)
WEEKSTART = the Monday of the week before THROUGH's week (`date -d 'last sunday - 13 days' +%F`), so the finished week re-pulls on Thursday and settles before its Tuesday lock. Window = WEEKSTART through yesterday.
- Scale Insights, US CA UK DE FR IT ES NL AU: `mcp__Scale_Insights__get_sales_data` with `country, start_date: WEEKSTART, end_date: yesterday, group_by: "day", summary_only: true, include_growth: false`. Save the result to a file and run `python3 scripts/weekly.py si-daily CC_<MKT> <file>` (AU = CC_AUS).
- US only: the per-ASIN daily feed misses multi-ASIN SB/SD spend (~5% of US). For each week in the window (finished week, then current week to yesterday) call `get_campaign_performance` (`country: US, mode: raw, count: 1, sort_by: cost`) and run `python3 scripts/weekly.py campaign CC_US <start> <end> <agg.TotalSpend>`. The other markets match campaign totals to the cent (checked 2026-10-08); skip them.
- SA: daily `advertising_cost` from the H10 cache (`query.py spend FROM TO CC_SA`, SAR) -> `python3 scripts/weekly.py day CC_SA <date>=<amt> ...`. Cache missing: leave it out; the page flags SA as not loaded.
- FX: WebFetch `https://api.frankfurter.dev/v1/<WEEKSTART minus 3 days>..<today>?from=USD&to=CAD%2CGBP%2CEUR%2CAUD`, save the JSON, `python3 scripts/weekly.py fx <file>`.
- `python3 scripts/weekly.py show` and put the current week's ceiling, spend and left into the summary line 2.
- New schedule from NIC (Matt Reid emails it; search Gmail "Rolling 6 Week Budget"): write it as JSON (source, issued, total, weeks [{wk, start Monday, base}]) and `python3 scripts/weekly.py schedule <file>`. It replaces the old one; carryover restarts from its first week because NIC's figures already include prior weeks. When the page says "last week of this schedule", flag it in the summary.
Skip on failure; the section keeps the last loaded spend and says "spend through <date>".

## 5. Build
```
python3 scripts/build.py --nic ../NIC --intl ../INTL
```
Then check: open each of sales/, health/, inventory/ in Playwright (`python3 -m http.server` from /home/claude, pages under /cerakote/), no console errors, no horizontal scroll at 390 px. The Sales GLOBAL view must show the pacing table with the Last 7 days column. The Month view must say "exact totals": it reads NIC `data/periods/`, written by the NIC run step 4b; without it the view falls back to prorated weeks labeled "est.". Out-of-stock chips come from the latest INTL q4 file.

## 5b. Password lock
`scripts/lock.py` encrypts every page and every file under inventory/files/ on each build when `config/lock.json` exists (build.py calls it; openssl CLI only, no pip installs). The build needs no password: it uses the public key in lock.json. Plain download files must not be pushed: build.py exits if it cannot delete them (the Mac connected-folder shell cannot delete; build in the cloud clone or run `git rm` from osascript). Status: `python3 scripts/lock.py status`. Barcus sets or changes the password on his Mac with `python3 scripts/lock.py setup`; never set it from a session.

## 6. Publish (from the Mac)
The cloud proxy blocks pushes to repos that are not authorized for the session. Publish from the Mac:
1. `git add -A && git commit -m "Refresh <date>"` in the cloud clone, then `git format-patch -1 -o /mnt/user-data/outputs/cerakote-patch/`.
2. `device_commit_files` the patch into `Cerakote Management/cerakote-site/inbox/`.
3. `mcp__remote-devices__Control_your_Mac__osascript` with a short `do shell script`:
   `export PATH=/opt/homebrew/bin:$PATH; cd ~/Documents/Claude/Projects/Cerakote\ Management/cerakote-site && git pull -q --rebase && git am inbox/*.patch && rm inbox/*.patch && git push -q origin main && git log -1 --oneline`
If the Mac is unreachable, SendUserFile the three index.html files and say "not published (Mac offline)".

## 7. Summary to Barcus (SendUserMessage, plain text, no em dashes)
Line 1: "Cerakote site refreshed <date>: sales WE <week>, health <ISO week>, inventory <projection week>". Line 2: pacing, one line: the total trending % and any channel outside 85-115%. Then any flags (stale pipeline, missing budget tab, missing channel, publish failure). Link: https://high-shot.github.io/cerakote/sales/
