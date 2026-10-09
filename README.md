# AgentLTL for Mistral Vibe

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![arXiv](https://img.shields.io/badge/arXiv-2607.02599-b31b1b.svg)](https://arxiv.org/abs/2607.02599)
[![Docs](https://img.shields.io/badge/docs-agentltl.github.io-3f51b5.svg)](https://agentltl.github.io/harnesses/mistral-vibe/)

> Rules Vibe can't forget.

`AGENTS.md` is advice: Vibe can lose it in a long session or inside a subagent. AgentLTL
checks every tool call [Mistral Vibe](https://github.com/mistralai/mistral-vibe) makes against
the rules in `AGENTLTL.yaml` **before it runs**, and refuses the ones that break them.

```
> ship 1.6.0 to prod

  ✗ bash  helm upgrade web repo/web --version 1.6.0 -n prod
    Rule 'promote-what-staging-ran' blocked this call. Nothing was executed.
    Problem: for chart='repo/web', v='1.6.0': no earlier helm_upgrade call had
             namespace='staging', chart='repo/web', version='1.6.0'.

  ✓ bash  helm upgrade web repo/web --version 1.6.0 -n staging
  ✓ bash  curl -fsS https://staging.example.com/health
  ✓ bash  helm upgrade web repo/web --version 1.6.0 -n prod
```

One rule did that:

```yaml
- id: promote-what-staging-ran
  before:
    first: {tool: helm_upgrade, with: {chart: $chart, version: $v, namespace: staging}}
    then:  {tool: helm_upgrade, with: {chart: $chart, version: $v, namespace: prod}}
  scope: project       # the staging deploy may have been yesterday, in another session
```

This is the [Claude Code plugin](https://github.com/AgentLTL/agentltl-claude-code)'s guard, on
Vibe's hooks: the same rule language, the same library and the same `AGENTLTL.yaml`, so a
project can share one rule file between Vibe, Claude Code and
[Copilot CLI](https://github.com/AgentLTL/agentltl-copilot-cli). It works with whatever model
Vibe runs, Mistral's or your own.

## Features

- **Order-aware rules:** tests before push, plan before apply, staging before prod; per session
  or across the whole project.
- **Variables across calls:** `$variables` tie calls together by their arguments.
- **Real shell parsing:** `git commit -am x && git push -f` is checked as `git_commit` then
  `git_push{force: true}`, all or nothing.
- **Plain-language rules:** ask Vibe to "add a rule: never push to main" (`/agentltl:rules`);
  it writes the rule and tests it before saving.
- **Opt-in rule library:** tested rules for git, secrets, installs and infrastructure
  (`/agentltl:setup`).
- **`finally` rules:** "run the tests before you finish": Vibe is sent back before it ends its
  turn.
- **Secret leak alerts:** when a command's output contains what looks like a credential, Vibe
  is told not to repeat it and you get a notice, so you can rotate it.
- **Rules instead of instructions:** when Vibe would write a rule into `AGENTS.md`, it writes an
  enforced rule instead; `/agentltl:import` does the same for what your instructions already
  hold.
- **Fail-safe:** never approves a call; if the guard can't answer, the call is refused.

## Installation

Requires Python 3.10+, git, and Mistral Vibe 2.26 or later.

```bash
git clone --recurse-submodules https://github.com/AgentLTL/agentltl-mistral-vibe.git ~/.vibe/plugins/agentltl
~/.vibe/plugins/agentltl/bin/agentltl install
```

`install` builds the plugin's Python environment (in `~/.vibe/plugin-data/agentltl`), adds
AgentLTL's three hooks to `~/.vibe/hooks.toml` (your own hooks there are kept), and links the
`agentltl` command into `~/.local/bin`. Vibe has no plugin installer and doesn't run hooks
from plugin folders, hence this step. The plugin does nothing until there is an
`AGENTLTL.yaml`: at a project's root for that project, or in `~/.vibe/` for every project.
Start with `/agentltl:setup` in a Vibe session to pick rules from the library.

**Updating:** `agentltl update`. **Removing:** `agentltl uninstall`, then delete the folder.

### Your own model

Vibe runs any OpenAI-compatible model. For a self-hosted one (vLLM serving Qwen, for
example, with `--enable-auto-tool-choice --tool-call-parser <parser>`), in
`~/.vibe/config.toml`:

```toml
active_model = "qwen"

[[providers]]
name = "vllm"
api_base = "http://my-server:8000/v1"
api_key_env_var = "VLLM_API_KEY"   # its value in ~/.vibe/.env; "" for none
backend = "generic"
api_style = "openai"

[[models]]
name = "Qwen/Qwen3-Coder-30B-A3B-Instruct"   # the served model name
provider = "vllm"
alias = "qwen"
max_context_length = 131072
```

AgentLTL doesn't depend on the model: the hooks see tool calls, whoever makes them.

## Usage

### Rules

```yaml
# AGENTLTL.yaml
use: [tests-before-push, no-force-push, protect-env-files, no-vibe-coauthor]

rules:
  - id: tests-before-push-here
    before: {first: {tool: make, with: {argv: check}}, then: git_push, since: [Edit, Write]}
    why: CI is slow; run the checks locally first.
    mode: warn
  - id: changelog
    finally: {call: {tool: Edit, where: {file_path: CHANGELOG.md}}, since: [Edit, Write]}
    why: Every change gets a CHANGELOG line.
```

Rules name tools as the library does, with Claude Code's names, so one file serves every
agent; Vibe's tools are mapped onto them:

| Mistral Vibe | Rules say |
|---|---|
| `bash {command}` | the commands it runs (`git_push`, `pytest`...) |
| `write_file`, `edit`, `read_file` | `Write`, `Edit`, `Read` (same arguments: `file_path`...) |
| `grep`, `web_fetch`, `web_search` | `Grep`, `WebFetch`, `WebSearch` |
| `agent_spawn` (`task` in the legacy runtime) | `Task` |

The full language (rule kinds, targets, variables, memory, modes) is in the
[rules reference](https://agentltl.github.io/rules/reference/), and the packaged rules in the
[library](https://agentltl.github.io/rules/library/). Library entries for another agent only
(`no-claude-coauthor`, `no-copilot-coauthor`, `subagents-on-sonnet`) switch nothing on in
Vibe, so a shared file stays valid. Vibe signs commits by default (`Co-Authored-By: Mistral
Vibe`); `no-vibe-coauthor` refuses those commits, and `include_commit_signature = false` in
`config.toml` stops Vibe from trying.

### Modes

| Mode | The call is | Who can let it through |
|---|---|---|
| `block` | denied, with the reason | you |
| `warn` | denied once | Vibe, by repeating the exact same call |
| `ask` | denied; Vibe asks you, then the exact same call goes through once | you |
| `retry` | denied; after the allowed retries, as `ask` | you |
| `stop` | denied, and every call is refused until you reply | you |
| `log` | allowed; Vibe is told it broke the rule | n/a |

### Skills and commands

| In Vibe | What it does |
|---|---|
| `/agentltl:setup` | pick packaged rules to switch on |
| `/agentltl:rules` | add, change or remove a rule in plain words |
| `/agentltl:import` | turn instructions (`AGENTS.md`...) into enforced rules |
| `/agentltl:status` | the rules in force and what they blocked |

| Command | What it does |
|---|---|
| `agentltl install`, `uninstall`, `update` | the hooks in `~/.vibe/hooks.toml` |
| `agentltl validate` | compile the rule files and list the rules |
| `agentltl check "git push" "pytest" "git push"` | replay steps through the rules |
| `agentltl translate "git commit -am x && git push"` | the calls a command line stands for |
| `agentltl library`, `use NAME`, `unuse NAME` | the packaged rules |
| `agentltl trace`, `reset` | what the guard recorded in this session and project |
| `agentltl memory scan` | statements in your instructions that could be rules |

## How it works

Vibe runs AgentLTL's hooks (`~/.vibe/hooks.toml`) around every tool call:

| Hook | AgentLTL |
|---|---|
| `pre_tool` | decides the call: `deny` with the reason, or silence |
| `post_tool` | records the call that ran (and whether it failed), passes on notes, scans the output for credentials; on a session's first call, lists the rules in force to Vibe |
| `post_agent` | sends Vibe back while a `finally` rule is unmet |

Vibe has no session-start or user-prompt hook and no "ask" answer; the
[full reference](docs/REFERENCE.md) says how the plugin does without them, and maps every
feature of the Claude Code plugin onto Vibe. Shell command lines are translated by
[cli-to-tools](https://github.com/AgentLTL/cli-to-tools) into the calls they run; the rules are
compiled by [agentltl-coding](https://github.com/AgentLTL/agentltl-coding) into
[AgentLTL](https://github.com/AgentLTL/AgentLTL) formulas, checked on the calls so far.

## Limitations

- **Subagents are not checked.** Vibe (2.26, default runtime) runs no hooks inside a
  subagent, so the calls a subagent makes escape the rules. The built-in rule
  `subagents-unchecked` makes spawning one a warning: Vibe is told to do the work itself, may
  insist by repeating the call, and you get a notice when a subagent starts.
  `subagents_unchecked: false` in `settings:` switches it off; `mode: block` (a project rule
  with the same id) forbids subagents.
- **`ask` goes through Vibe.** Vibe's hooks can't prompt you, so an `ask` rule refuses the
  call and Vibe asks you itself; the plugin lets the call through once Vibe has asked or you
  have written, trusting Vibe to respect a "no".
- **Notices name the tool, not the rule.** When a call is refused, Vibe shows you "Denied
  tool 'bash'"; the reason and the rule go to the model, which is asked to name the rule in
  its reply. `agentltl trace` lists every refusal with its rule.
- **Calls from `run_typescript`** (Vibe's sandbox that calls tools from code) are checked like
  any other, but a refused one only reads "skipped by Runtime policy" to the model.
- **The rules arrive with the first call's result**, not before Vibe's first message.
- **Unattended runs:** set `AGENTLTL_AUTO=1` for `vibe -p`, so `ask` rules refuse and commands
  the guard can't analyse follow `unparseable.auto`.
- **Project hooks:** AgentLTL's hooks live in your `~/.vibe/hooks.toml`; it doesn't use a
  project's `.vibe/hooks.toml`, which Vibe only runs in trusted folders.
- The rest is as in the [Claude Code plugin](https://agentltl.github.io/harnesses/claude-code/):
  a rule sees tool calls, not what a script does inside.

## Development

```bash
git clone --recurse-submodules https://github.com/AgentLTL/agentltl-mistral-vibe.git
cd agentltl-mistral-vibe
scripts/setup.sh --dev
.venv/bin/pytest -q
```

`docker/` has an image with Mistral Vibe 2.26 for trying the plugin end to end:

```bash
docker/e2e.sh                   # no model needed: a scripted model makes the calls
cp .env.example .env            # your OpenAI-compatible endpoint and key
docker/live.sh "a task"         # one `vibe -p` session on your model, with e2e/AGENTLTL.yaml
docker run --rm -it --network host --env-file .env -v "$PWD":/src:ro agentltl-vibe \
    bash -c 'mkdir -p ~/.vibe/plugins && cp -r /src ~/.vibe/plugins/agentltl && ~/.vibe/plugins/agentltl/bin/agentltl install && bash'
# then `vibe` in /work, a scratch repository
```

`tests/fixtures/payloads/` holds hook payloads captured from Vibe 2.26.0; the tests replay
them. The Vibe version `docker/e2e.sh` tests is pinned in `docker/requirements.txt`;
Dependabot proposes each new release as a pull request, and the end-to-end workflow flags the
ones that break the plugin.

## Documentation

[agentltl.github.io](https://agentltl.github.io/harnesses/mistral-vibe/), and
[docs/REFERENCE.md](docs/REFERENCE.md) here.

## License

MIT. See [LICENSE](LICENSE).
