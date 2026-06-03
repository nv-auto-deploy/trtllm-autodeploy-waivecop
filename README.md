# TRT-LLM AutoDeploy Slack notifications — GitHub Actions

Two GitHub Actions post to Slack about waived TensorRT-LLM AutoDeploy tests:

1. **New-waiver alerts** (hourly) — fires only when a *new* AutoDeploy waiver appears.
2. **Daily digest** (weekdays, 7:00 AM Pacific) — posts the full current AutoDeploy
   waiver list.

Both use the same bot token + channel.

## What's here

```
.github/workflows/trtllm-autodeploy-waivers.yml   # hourly new-waiver watcher
.github/workflows/trtllm-autodeploy-digest.yml    # daily 7am Pacific full digest
.github/scripts/watch_autodeploy_waivers.py       # change detection + alert
.github/scripts/post_autodeploy_waivers.py        # full-list digest post
.state/autodeploy_waivers.json                    # snapshot (auto-created & committed)
```

## Setup (shared by both)

1. Copy these files into your repo, preserving the paths.
2. Add credentials under **Settings → Secrets and variables → Actions**:
   - **Secret** `AUTODEPLOY_WAIVECOP` = `xoxb-...` (Bot User OAuth Token) → mapped to the
     scripts' `SLACK_BOT_TOKEN`.
   - **Variable** `AUTODEPLOY_DEV_CHANNEL` = `C0XXXXXXXXX` (channel ID) → mapped to
     `SLACK_CHANNEL_ID`.
3. Bot must be able to post to the channel: public → `chat:write.public`; private →
   `/invite` the app.
4. The watcher needs **`permissions: contents: write`** (already set) to commit its
   snapshot. The digest needs no special permissions.
5. Commit & push, then **Actions → Run workflow** on each (the watcher's first run just
   establishes the baseline; the digest posts immediately on a manual run).

## 1) New-waiver alerts (hourly)

`waives.txt` lives upstream in `NVIDIA/TensorRT-LLM` (you don't control it, and Actions
can't trigger on another repo's commits), so this **polls hourly and diffs against a saved
snapshot** at `.state/autodeploy_waivers.json`:

- Fires **only on additions** — new `auto_deploy`/`autodeploy` test entries. Un-waives
  (removals) are ignored.
- The alert names the new waiver(s) explicitly and posts the full current list (new ones
  marked `:new:`) as a threaded reply.
- **First run is a baseline:** records the current set and does not alert; alerts start on
  the next run that adds a waiver.
- Latency is up to ~1 hour (`cron: "23 * * * *"`, every day; `:23` dodges top-of-hour
  congestion). ~24 short runs/day — free on public repos, uses minutes on private. Narrow
  the cron to cut runs (e.g. `"23 13-23 * * 1-5"`).

## 2) Daily digest (weekdays, 7:00 AM Pacific)

Posts the full AutoDeploy waiver list every weekday morning. GitHub cron is UTC and
best-effort, so it registers both `14:00` (PDT) and `15:00` (PST) UTC and a DST-aware gate
runs whichever matches the current offset + cron — a delayed run posts late rather than
skipping. Edit the two `cron:` lines / `-0700`/`-0800` offsets to change the time.

## Local preview (no posting)

```bash
# Daily digest output:
DRY_RUN=1 python3 .github/scripts/post_autodeploy_waivers.py

# New-waiver alert (seed a baseline, then point at a file with an added line):
DRY_RUN=1 STATE_FILE=/tmp/seed.json WAIVES_URL="file://$PWD/before.txt" \
  python3 .github/scripts/watch_autodeploy_waivers.py
DRY_RUN=1 STATE_FILE=/tmp/seed.json WAIVES_URL="file://$PWD/after.txt" \
  python3 .github/scripts/watch_autodeploy_waivers.py
```

`DRY_RUN=1` prints instead of posting.

## Notes

- Never commit the token — it lives only in repo secrets.
- Change channel by editing the `AUTODEPLOY_DEV_CHANNEL` variable (affects both workflows).
