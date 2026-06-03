#!/usr/bin/env python3
"""
Watch NVIDIA/TensorRT-LLM waives.txt and alert Slack when a NEW AutoDeploy waiver
appears.

Fires ONLY on additions (test entries present now but not in the last-seen snapshot).
Removals / un-waives do NOT trigger an alert (but the snapshot is still updated, so a
later re-waive of the same test is detected as new again).

The alert names the new waiver(s) explicitly and posts the full current AutoDeploy
list as a threaded reply (with the new entries marked).

State (the last-seen set of AutoDeploy waivers) is persisted to STATE_FILE so each run
can diff against the previous one. Standard library only.

Env:
  SLACK_BOT_TOKEN   xoxb- token (required to post; unless DRY_RUN=1)
  SLACK_CHANNEL_ID  channel id (required to post; unless DRY_RUN=1)
  STATE_FILE        path to JSON snapshot (default .state/autodeploy_waivers.json)
  WAIVES_URL        optional source override (accepts a file:// URL for testing)
  DRY_RUN           "1" => print instead of posting to Slack (snapshot still updates)
"""
import datetime
import json
import os
import re
import sys
import urllib.request

try:
    from zoneinfo import ZoneInfo  # Python 3.9+
except ImportError:  # pragma: no cover
    ZoneInfo = None

WAIVES_URL = os.environ.get(
    "WAIVES_URL",
    "https://raw.githubusercontent.com/NVIDIA/TensorRT-LLM/main/tests/integration/test_lists/waives.txt",
)
SOURCE_LINK = "https://sourcegraph.com/r/github.com/NVIDIA/TensorRT-LLM/-/blob/tests/integration/test_lists/waives.txt"
STATE_FILE = os.environ.get("STATE_FILE", ".state/autodeploy_waivers.json")
TZ = "America/Los_Angeles"

AUTODEPLOY = re.compile(r"auto_?deploy", re.IGNORECASE)  # "autodeploy" or "auto_deploy"
BUG = re.compile(r"nvbugs?/(\d+)", re.IGNORECASE)


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "trtllm-autodeploy-waiver-bot"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def parse(text):
    """Return {test_name: nvbug_id_or_None} for AutoDeploy waivers."""
    out = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if not AUTODEPLOY.search(line):
            continue
        test = (
            line.split(" SKIP")[0].strip()
            if " SKIP" in line
            else re.split(r"\s+\(", line, 1)[0].strip()
        )
        m = BUG.search(line)
        out[test] = m.group(1) if m else None
    return out


def today():
    if ZoneInfo is not None:
        return datetime.datetime.now(ZoneInfo(TZ)).strftime("%a, %b %d %Y")
    return datetime.date.today().strftime("%a, %b %d %Y")


def load_state(path):
    try:
        with open(path) as f:
            return json.load(f).get("waivers", {})
    except FileNotFoundError:
        return None
    except Exception as e:  # corrupt/unreadable -> rebuild baseline
        print(f"WARN: could not read state ({e}); treating as baseline.", file=sys.stderr)
        return None


def write_state(path, waivers):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    payload = {
        "updated": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "waivers": waivers,
    }
    with open(path, "w") as f:
        json.dump(payload, f, indent=2, sort_keys=True)
        f.write("\n")


def line(test, bug, mark=""):
    if bug:
        return f"• `{test}`  →  <https://nvbugs/{bug}|nvbug {bug}>{mark}"
    return f"• `{test}`  →  _(no nvbug id found)_{mark}"


def build_alert(new_tests, current):
    d = today()
    n, m = len(new_tests), len(current)
    plural = "s" if n != 1 else ""
    header = [
        f":rotating_light: *New TRT-LLM AutoDeploy waiver{plural}* — {d}",
        f"*{n}* new waiver{plural} added (now *{m}* total AutoDeploy waiver(s)). New:",
        "",
    ]
    header += [line(t, current[t]) for t in new_tests]
    header += ["", "Full current list in the thread :thread:"]

    new_set = set(new_tests)
    body = [
        line(t, current[t], mark=" :new:" if t in new_set else "")
        for t in sorted(current)
    ]
    body += ["", f"<{SOURCE_LINK}|Source: waives.txt>"]
    return "\n".join(header), "\n".join(body)


def post(token, channel, text, thread_ts=None):
    body = {"channel": channel, "text": text, "unfurl_links": False, "unfurl_media": False}
    if thread_ts:
        body["thread_ts"] = thread_ts
    req = urllib.request.Request(
        "https://slack.com/api/chat.postMessage",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        resp = json.loads(r.read().decode("utf-8"))
    if not resp.get("ok"):
        raise SystemExit(f"Slack API error: {resp.get('error')} | full response: {resp}")
    return resp


def main():
    dry = os.environ.get("DRY_RUN") == "1"
    current = parse(fetch(WAIVES_URL))
    previous = load_state(STATE_FILE)

    # First run ever: seed the snapshot, do NOT alert (avoids a false "everything is new").
    if previous is None:
        write_state(STATE_FILE, current)
        print(f"Baseline established with {len(current)} AutoDeploy waiver(s); no alert on first run.")
        return

    new_tests = sorted(set(current) - set(previous))
    removed = sorted(set(previous) - set(current))
    changed = current != previous
    print(
        f"current={len(current)} previous={len(previous)} "
        f"new={len(new_tests)} removed={len(removed)} changed={changed}"
    )

    if new_tests:
        header, body = build_alert(new_tests, current)
        if dry:
            print("--- DRY_RUN: channel message ---")
            print(header)
            print("\n--- DRY_RUN: threaded reply ---")
            print(body)
        else:
            token = os.environ.get("SLACK_BOT_TOKEN")
            channel = os.environ.get("SLACK_CHANNEL_ID")
            if not token or not channel:
                raise SystemExit("Set SLACK_BOT_TOKEN and SLACK_CHANNEL_ID (or DRY_RUN=1).")
            parent = post(token, channel, header)
            post(token, channel, body, thread_ts=parent["ts"])
            print(f"Alerted: {len(new_tests)} new AutoDeploy waiver(s).")
    else:
        msg = "No new AutoDeploy waivers — not alerting"
        msg += f" ({len(removed)} removed, ignored)." if removed else "."
        print(msg)

    # Keep the snapshot current (additions, removals, bug-id changes) so we don't
    # re-alert. State is updated only after a successful post above.
    if changed:
        write_state(STATE_FILE, current)
        print("Snapshot updated.")
    else:
        print("Snapshot unchanged.")


if __name__ == "__main__":
    main()
