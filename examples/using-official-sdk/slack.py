#!/usr/bin/env python3
"""Read and write Slack through the official slack_sdk. Self-contained: run it directly.

The write half posts, searches, reacts, edits and deletes, then reads back what the server
recorded. Nothing reaches the corpus file: writes land in an in-memory overlay that lives and
dies with the server, which is what lets one evaluation run start where the last one did. See
docs/overlay.md.

pip install -e ".[official-sdk]"
python examples/using-official-sdk/slack.py            # or: --url http://localhost:8000
python examples/using-official-sdk/slack.py --url http://localhost:8000 --token <usr-token>
python examples/using-official-sdk/slack.py --read-only
"""

import argparse
import json
import urllib.request

from slack_sdk import WebClient

from backlot import serve_or_connect

CORPUS = [
    {
        "author_email": "ava@acme.com",
        "created": "2026-02-05T17:00:00Z",
        "source_type": "slack",
        "channel": "eng",
        "content": "Deploy freeze starts Friday 5pm.",
    },
    {
        "author_email": "bob@acme.com",
        "created": "2026-02-10T18:00:00Z",
        "source_type": "slack",
        "channel": "incidents",
        "content": "Anyone seeing 502s from the gateway?",
        "replies": [
            {
                "author_email": "ava@acme.com",
                "created": "2026-02-10T18:00:40Z",
                "content": "Looking now.",
            },
            {
                "author_email": "bob@acme.com",
                "created": "2026-02-10T18:06:00Z",
                "content": "Rolled back — clearing up.",
            },
        ],
    },
]

_p = argparse.ArgumentParser(
    description="Read Slack through the official slack_sdk against Backlot."
)
_p.add_argument(
    "--url", help="Backlot base URL to drive (default: spin up a local throwaway server)"
)
_p.add_argument(
    "--token",
    help="Backlot bearer token from GET /_meta/users "
    "(default: the admin token, which sees everything)",
)
_p.add_argument("--read-only", action="store_true", help="read the corpus and skip the write half")
args = _p.parse_args()

with serve_or_connect(CORPUS, url=args.url) as s:
    if args.token:
        print("authenticating with --token → responses are ACL-filtered to that user")
    client = WebClient(token=args.token or s.token, base_url=f"{s.base_url}/slack/api/")

    channels = client.conversations_list()["channels"]
    if not channels:
        print("no channels visible to this identity")
        raise SystemExit(0)

    channel = channels[0]
    messages = client.conversations_history(channel=channel["id"], limit=10)["messages"]
    print(f"{len(channels)} channels; #{channel['name']} has these recent messages:")
    for m in messages:
        print(f"  - {m['text'].splitlines()[0]}")

    if args.read_only:
        raise SystemExit(0)

    print(f"\nwriting to #{channel['name']}")
    ts = client.chat_postMessage(channel=channel["id"], text="Deploy freeze lifted.")["ts"]
    print(f"  posted {ts}")

    # A written message is a message: the reads find it under the same ACL as the corpus around
    # it, search included -- which is the part a mock usually gets wrong.
    matches = client.search_messages(query="freeze")["messages"]["matches"]
    print(
        f"  search for 'freeze' matches {len(matches)}, including the new one: "
        f"{ts in [m['ts'] for m in matches]}"
    )

    client.reactions_add(channel=channel["id"], timestamp=ts, name="tada")
    reacted = client.reactions_get(channel=channel["id"], timestamp=ts)["message"]
    print(f"  reactions: {[(r['name'], r['count']) for r in reacted['reactions']]}")

    client.chat_update(channel=channel["id"], ts=ts, text="Deploy freeze lifted - ship away.")
    edited = next(
        m
        for m in client.conversations_history(channel=channel["id"], limit=10)["messages"]
        if m["ts"] == ts
    )
    print(f"  edited to {edited['text']!r}, stamped by {edited['edited']['user']}")

    # What the server recorded, which is what an evaluation's grader reads.
    with urllib.request.urlopen(f"{s.base_url}/_meta/overlay") as response:
        overlay = json.load(response)
    rows = {name: len(table) for name, table in overlay.items() if table}
    print(f"  /_meta/overlay: {rows}")

    client.chat_delete(channel=channel["id"], ts=ts)
    left = client.conversations_history(channel=channel["id"], limit=10)["messages"]
    print(f"  deleted; still in history: {ts in [m['ts'] for m in left]}")
