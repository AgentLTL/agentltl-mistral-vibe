#!/usr/bin/env bash
# End to end, no model needed: Mistral Vibe in Docker, the plugin installed from this checkout,
# and a scripted model (scripted_model.py) that makes the calls in e2e/script.json. Checks that
# each rule in e2e/AGENTLTL.yaml refused what it should, and that `finally` sent Vibe back.
#
#   docker/e2e.sh            # builds the image if needed
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
docker image inspect agentltl-vibe >/dev/null 2>&1 || docker build -q -t agentltl-vibe "$root/docker"
out="$(mktemp -d)"
chmod 777 "$out"
docker run --rm -v "$root":/src:ro -v "$out":/out agentltl-vibe bash /src/docker/e2e/run.sh
python3 - "$out" <<'EOF'
import json, sys
out = sys.argv[1]
trace = open(f"{out}/trace.txt").read()
expected = ["DENY  [read-before-overwrite] Write README.md", "DENY  [no-sudo] Bash sudo ls",
            "ASK   [ask-before-rm-rf] Bash rm -rf build", "DENY  [no-vibe-coauthor]",
            "DENY  [no-force-push]", "DENY  [no-sudo] Bash sudo id"]
missing = [e for e in expected if e not in trace]
notices = [e["message"] for e in json.load(open(f"{out}/vibe.json"))
           if e.get("type") == "notice" and e["detail"].get("kind") == "hook_completed"]
if not any(n.startswith("AgentLTL sent Vibe back") for n in notices):
    missing.append("a finally send-back")
if not any("rule(s) in force" in n for n in notices):
    missing.append("the rules in force")
if missing:
    print("FAILED, missing:", *missing, f"(see {out})", sep="\n  ")
    sys.exit(1)
print(f"OK: {len(expected)} refusals, the rules listed, Vibe sent back once ({out})")
EOF
