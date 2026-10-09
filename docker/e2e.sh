#!/usr/bin/env bash
# End to end, no model needed: Mistral Vibe (the version in requirements.txt) in Docker, the
# plugin installed from this checkout, and agentltl-coding's scripted model making the calls in
# e2e/script.json. Checks that the rules in e2e/AGENTLTL.yaml refused what e2e/expected.txt
# says, that the rules were listed to Vibe, and that `finally` sent Vibe back.
#
#   docker/e2e.sh          # E2E_OUT=dir keeps the output there (default: a temporary folder)
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
docker build -q -t agentltl-vibe "$root/docker" > /dev/null
if [[ -n "${E2E_OUT:-}" ]]; then
    mkdir -p "$E2E_OUT" && out="$(cd "$E2E_OUT" && pwd)"
else
    out="$(mktemp -d)"
fi
chmod 777 "$out"
docker run --rm -v "$root":/src:ro -v "$out":/out agentltl-vibe bash /src/docker/e2e/run.sh
echo "Vibe $(cat "$out/version.txt" 2>/dev/null), output in $out"
python3 "$root/vendor/agentltl-coding/e2e/check.py" "$out/trace.txt" "$root/docker/e2e/expected.txt"
python3 - "$out" <<'EOF'
import json, sys
notices = [e["message"] for e in json.load(open(f"{sys.argv[1]}/vibe.json"))
           if e.get("type") == "notice" and e["detail"].get("kind") == "hook_completed"]
missing = [what for what, ok in (
    ("the notice listing the rules in force", any("rule(s) in force" in n for n in notices)),
    ("a `finally` send-back", any(n.startswith("AgentLTL sent Vibe back") for n in notices)))
    if not ok]
if missing:
    print("FAILED: no", *missing, sep="\n  ")
    sys.exit(1)
print("OK: the rules were listed and Vibe was sent back.")
EOF
