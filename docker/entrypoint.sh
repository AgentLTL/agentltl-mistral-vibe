#!/usr/bin/env bash
# Point Vibe at the OpenAI-compatible model in the environment (VLLM_*, see .env.example),
# then run the command.
set -euo pipefail
home="${VIBE_HOME:-$HOME/.vibe}"
mkdir -p "$home"
if [[ -n "${VLLM_BASE_URL:-}" && ! -f "$home/config.toml" ]]; then
    base="${VLLM_BASE_URL%/}"
    [[ "$base" == */v1 ]] || base="$base/v1"
    cat > "$home/config.toml" <<TOML
active_model = "local"

[[providers]]
name = "vllm"
api_base = "${base}"
api_key_env_var = "VLLM_API_KEY"
backend = "generic"
api_style = "openai"
reasoning_field_name = "${VLLM_REASONING_FIELD:-reasoning}"

[[models]]
name = "${VLLM_MODEL:-qwen3.8-27b}"
provider = "vllm"
alias = "local"
thinking = "off"
max_context_length = ${VLLM_MAX_CONTEXT:-65536}

[utility_models]
title = "local"
TOML
fi
export VLLM_API_KEY="${VLLM_API_KEY:-none}"
exec "$@"
