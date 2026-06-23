#!/usr/bin/env python3
"""
Fetch TensorRT-LLM waives.txt and post the waived AutoDeploy tests to Slack as a
short headline message in the channel, with the full list (test + nvbug id) as a
threaded reply under it.

Standard library only — no pip install needed.

Environment variables:
  SLACK_BOT_TOKEN    Bot User OAuth token (xoxb-...). Required unless DRY_RUN=1.
  SLACK_CHANNEL_ID   Target channel ID, e.g. C0XXXXXXXXX. Required unless DRY_RUN=1.
  WAIVES_URL         Optional override of the source URL (also accepts a file:// URL).
  DRY_RUN            If "1", print the messages and exit without posting.
"""
import datetime
import json
import os
import re
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
TZ = "America/Los_Angeles"

AUTODEPLOY = re.compile(r"auto_?deploy|_ad_", re.IGNORECASE)  # autodeploy / auto_deploy / *_ad_*
BUG = re.compile(r"nvbugs?/(\d+)", re.IGNORECASE)


def fetch(url):
    req = urllib.request.Request(
        url, headers={"User-Agent": "trtllm-autodeploy-waiver-bot"}
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def parse(text):
    rows = []
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
        rows.append((test, m.group(1) if m else None))
    rows.sort()
    return rows


def today_str():
    if ZoneInfo is not None:
        return datetime.datetime.now(ZoneInfo(TZ)).strftime("%a, %b %d %Y")
    return datetime.date.today().strftime("%a, %b %d %Y")


def build_header(rows, today):
    """Short message posted in the channel."""
    if not rows:
        return (
            f":white_check_mark: *TRT-LLM AutoDeploy waived tests* — {today}\n"
            "No waived AutoDeploy tests currently in `waives.txt`."
        )
    return (
        f":warning: *TRT-LLM AutoDeploy waived tests* — {today}\n"
        f"*{len(rows)}* waived AutoDeploy test(s) currently in `waives.txt`. "
        "Full list in the thread :thread:"
    )


def build_detail(rows):
    """Long message posted as a threaded reply under the header."""
    lines = []
    for test, bug in rows:
        lines.append(
            f"• `{test}`  →  <https://nvbugs/{bug}|nvbug {bug}>"
            if bug
            else f"• `{test}`  →  _(no nvbug id found)_"
        )
    lines += ["", f"<{SOURCE_LINK}|Source: waives.txt>"]
    return "\n".join(lines)


def post(token, channel, text, thread_ts=None):
    body = {
        "channel": channel,
        "text": text,
        "unfurl_links": False,
        "unfurl_media": False,
    }
    if thread_ts:
        body["thread_ts"] = thread_ts
    payload = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        "https://slack.com/api/chat.postMessage",
        data=payload,
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
    rows = parse(fetch(WAIVES_URL))
    today = today_str()
    header = build_header(rows, today)
    print(f"Parsed {len(rows)} AutoDeploy waiver(s).")

    if os.environ.get("DRY_RUN") == "1":
        print("--- DRY_RUN: channel message ---")
        print(header)
        if rows:
            print("\n--- DRY_RUN: threaded reply ---")
            print(build_detail(rows))
        return

    token = os.environ.get("SLACK_BOT_TOKEN")
    channel = os.environ.get("SLACK_CHANNEL_ID")
    if not token or not channel:
        raise SystemExit(
            "Set SLACK_BOT_TOKEN and SLACK_CHANNEL_ID (or DRY_RUN=1 to preview)."
        )

    print(f"Posting header to {channel} ...")
    parent = post(token, channel, header)
    if rows:
        print(f"Posting {len(rows)}-item list as a threaded reply ...")
        post(token, channel, build_detail(rows), thread_ts=parent["ts"])
    print("Posted OK.")


if __name__ == "__main__":
    main()
