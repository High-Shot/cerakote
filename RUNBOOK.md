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
- Helium10, CL_US / PP_US / CC_SA: `mcp__Helium10__get_account_profit_and_loss_summary_series`, `granularity: "day"`, sum abs(`advertising_cost`) over the window. Seller ids: CL_US A1KUYEQ8RRQVVI (US), PP_US A21D21T8B6U09C (US), CC_SA A3BMUMIXNXIR6G (SA, `currency: "SAR"`).
```
python3 scripts/pacing.py spend $MONTH $THROUGH CC_US=<n>:si CC_CA=<n>:si ... CL_US=<n>:h10 PP_US=<n>:h10 CC_SA=<n>:h10
```
Never estimate a missing channel; leave it out and flag it.
Source check (2026-09-28): Scale Insights matched the sheet's Ads-export spend within 0.2% on all nine Cerakote Auto markets. Helium10 matches Amazon's Reports Beta spend to the cent, but NOT the sheet for CL_US (-15%), PP_US (+8%) and CC_SA (+14%) over Sept 1-26. The sheet's figures for those three are the suspect ones (unconfirmed).

## 5. Build
```
python3 scripts/build.py --nic ../NIC --intl ../INTL
```
Then check: open each of sales/, health/, inventory/ in Playwright (`python3 -m http.server` from /home/claude, pages under /cerakote/), no console errors, no horizontal scroll at 390 px. The Sales GLOBAL view must show the pacing table.

## 6. Publish (from the Mac)
The cloud proxy blocks pushes to repos that are not authorized for the session. Publish from the Mac:
1. `git add -A && git commit -m "Refresh <date>"` in the cloud clone, then `git format-patch -1 -o /mnt/user-data/outputs/cerakote-patch/`.
2. `device_commit_files` the patch into `Cerakote Management/cerakote-site/inbox/`.
3. `mcp__remote-devices__Control_your_Mac__osascript` with a short `do shell script`:
   `export PATH=/opt/homebrew/bin:$PATH; cd ~/Documents/Claude/Projects/Cerakote\ Management/cerakote-site && git pull -q --rebase && git am inbox/*.patch && rm inbox/*.patch && git push -q origin main && git log -1 --oneline`
If the Mac is unreachable, SendUserFile the three index.html files and say "not published (Mac offline)".

## 7. Summary to Barcus (SendUserMessage, plain text, no em dashes)
Line 1: "Cerakote site refreshed <date>: sales WE <week>, health <ISO week>, inventory <projection week>". Line 2: pacing, one line: the total trending % and any channel outside 85-115%. Then any flags (stale pipeline, missing budget tab, missing channel, publish failure). Link: https://high-shot.github.io/cerakote/sales/
