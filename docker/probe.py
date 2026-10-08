#!/usr/bin/env python3
"""A hook that writes each payload it gets to /probe/<n>-<event>.json and answers nothing."""
import json, os, sys, time
payload = json.load(sys.stdin)
name = f"{time.time_ns()}-{payload.get('hook_event_name', 'unknown')}.json"
with open(os.path.join(os.environ.get("PROBE_DIR", "/probe"), name), "w") as fh:
    json.dump({"payload": payload, "env": {k: v for k, v in os.environ.items()
               if "VIBE" in k or "PLUGIN" in k or k in ("PWD", "HOME")}}, fh, indent=1)
