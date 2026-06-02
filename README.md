# TRT-LLM AutoDeploy waivers — GitHub Actions runner

Posts a short headline to the channel and the full list of waived TensorRT-LLM AutoDeploy
tests (with nvbug IDs) as a **threaded reply**, **weekdays at 7:00 AM Pacific**, using
`chat.postMessage` with a bot token.

## What's here

```
.github/workflows/trtllm-autodeploy-waivers.yml   # the scheduled workflow
.github/scripts/post_autodeploy_waivers.py                # stdlib-only fetch + parse + post
```

## Prerequisites

- A Slack app with a **bot token** (create it from `../webapp-manifest`). Bot scopes:
  `chat:write` (+ `chat:write.public` to post to public channels without an invite).
- A **GitHub repo** to host these two files. It does **not** have to be the TensorRT-LLM
  repo — `waives.txt` is fetched over HTTPS, so any repo you own works.

## Setup

1. Copy the files into your repo, preserving the paths above.
2. Add credentials under **Settings → Secrets and variables → Actions**:
   - **Secret** `AUTODEPLOY_WAIVECOP` = `xoxb-...` (Bot User OAuth Token). The workflow
     maps this secret to the script's `SLACK_BOT_TOKEN` env var, so the script needs no change.
   - **Variable** `AUTODEPLOY_DEV_CHANNEL` = `C0XXXXXXXXX` (target channel ID — e.g. your
     `#auto-deploy-dev` once it exists; copy it from the channel URL). The workflow maps it to the `SLACK_CHANNEL_ID` env var the script reads.
3. Make sure the bot can post to that channel:
   - **Public** channel → `chat:write.public` covers it, no invite needed.
   - **Private** channel → `/invite @trtllm-autodeploy-waivers` after installing the app.
4. Commit & push.
5. **Test immediately:** Actions tab → "TRT-LLM AutoDeploy waivers" → **Run workflow**.
   Manual (`workflow_dispatch`) runs bypass the time gate and post right away.

## Schedule / timezone

GitHub cron is **UTC-only**, so the workflow triggers at `14:00` and `15:00` UTC on
weekdays, and a gate step proceeds only when it is exactly `07:00` in
`America/Los_Angeles`. That keeps it at 7 AM Pacific across DST with no drift. To change
the time, edit the two `cron:` lines and the `TZ` in the gate (and `TZ` in the script).

## Local preview (no posting)

```bash
# Live data, just print the message:
DRY_RUN=1 python3 .github/scripts/post_autodeploy_waivers.py

# Against a local copy of the file:
WAIVES_URL="file://$PWD/waives.txt" DRY_RUN=1 python3 .github/scripts/post_autodeploy_waivers.py
```

## Notes

- Never commit the token — it lives only in repo secrets.
- To post to a different channel, just change the `AUTODEPLOY_DEV_CHANNEL` variable.
- The message body is identical to `../reference_parser.py`.
