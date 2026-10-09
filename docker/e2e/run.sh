#!/usr/bin/env bash
# Runs inside the agentltl-vibe image (see ../e2e.sh): installs the plugin from /src as a user
# would, starts the scripted model, runs one `vibe -p` session in /work with e2e/AGENTLTL.yaml,
# and leaves what happened in /out.
set -u
here=/src/docker/e2e
export VIBE_HOME=/home/dev/.vibe FAKE_KEY=x
mkdir -p "$VIBE_HOME/plugins" /out
cp "$here/config.toml" "$VIBE_HOME/"
cp -r /src "$VIBE_HOME/plugins/agentltl" && rm -rf "$VIBE_HOME/plugins/agentltl/.venv"
cd /work && printf 'hello\n' > README.md && git add README.md && git commit -qm init
cp "$here/AGENTLTL.yaml" /work/AGENTLTL.yaml
"$VIBE_HOME/plugins/agentltl/bin/agentltl" install --no-cli > /out/install.txt 2>&1
vibe --version > /out/version.txt 2>&1
python3 /src/vendor/agentltl-coding/e2e/scripted_model.py "$here/script.json" --log /out &
sleep 1
timeout 300 vibe -p "do the scripted steps" --auto-approve --trust --output json \
    > /out/vibe.json 2> /out/vibe-stderr.txt
echo "exit $?" >> /out/vibe-stderr.txt
"$VIBE_HOME/plugins/agentltl/bin/agentltl" trace > /out/trace.txt 2>&1
