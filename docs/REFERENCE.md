# AgentLTL for Mistral Vibe: full reference

The plugin is the [Claude Code plugin](https://github.com/AgentLTL/agentltl-claude-code)'s
guard on Mistral Vibe's hooks. Both are thin layers over
[agentltl-coding](https://github.com/AgentLTL/agentltl-coding), which holds the rule language,
the library, the guard and what the hooks do; each plugin only translates its agent's
payloads, tool names and files.

## Setup

```bash
git clone --recurse-submodules https://github.com/AgentLTL/agentltl-mistral-vibe.git ~/.vibe/plugins/agentltl
~/.vibe/plugins/agentltl/bin/agentltl install
```

- Vibe has no plugin install command, and it doesn't run hooks shipped inside a plugin
  folder: it runs the ones in `~/.vibe/hooks.toml` (and a trusted project's
  `.vibe/hooks.toml`). `agentltl install` adds three `[[hooks]]` entries there, between two
  marker comments, and leaves the rest of the file alone; `agentltl uninstall` removes them.
  The clone in `~/.vibe/plugins/` also gives Vibe the plugin's skills.
- The first run builds a Python environment in `~/.vibe/plugin-data/agentltl/venv-<pins>`
  (`$VIBE_HOME` if set), from the commits pinned in `vendor.lock`. It needs Python 3.10+ and
  git. An update that changes the pins builds a new one; environments unused for 14 days are
  removed.
- Rules apply where an `AGENTLTL.yaml` is: the project's (found from the working directory up
  to the git root) and the user's, `~/.vibe/AGENTLTL.yaml`. Without either, the hooks exit at
  once.
- `agentltl install` also links the command line into `~/.local/bin`.
- **Updating:** `agentltl update` (a `git pull` of the clone, then `install` again).

## Claude Code plugin features, in Mistral Vibe

| Claude Code plugin | Mistral Vibe plugin |
|---|---|
| `claude plugin install agentltl@agentltl` | `git clone` into `~/.vibe/plugins/agentltl`, then `agentltl install` |
| Hooks in the plugin's `hooks.json` | `[[hooks]]` in `~/.vibe/hooks.toml`: `pre_tool`, `post_tool`, `post_agent` |
| `SessionStart`: the rules in force | no such event: the rules come with the result of the session's first call (`additional_context`), and every refusal names its rule |
| `UserPromptSubmit`: lifts a `stop`, starts a turn | no such event: when `post_agent` lets Vibe finish, the next call follows the user's reply |
| PreToolUse `deny`, with a reason | `pre_tool` `decision: deny` with a `reason`; Vibe shows "Denied tool …" and the model gets the reason |
| PreToolUse `ask` | no such answer: the call is denied, Vibe is told to ask the user with `ask_user_question`, and the exact same call then goes through once |
| `systemMessage` | `system_message`: shown to the user in Vibe's notices (rules in force, credential warnings, `finally` send-backs) |
| PostToolUse / PostToolUseFailure | `post_tool` with `tool_status` `success` (status 0), `failure` (status 1), `cancelled` (not recorded) |
| Stop `decision: block` for `finally` rules | `post_agent` `decision: deny`: the reason comes back to Vibe as a message and it goes on, at most `finish_retries` times per turn |
| `permission_mode` (auto modes) | not in the payload; `AGENTLTL_AUTO=1` marks an unattended run (`vibe -p`): `ask` is refused, `unparseable.auto` applies |
| `CLAUDE_PROJECT_DIR` | `VIBE_PROJECT_DIR`, else the git root of the working directory |
| Subagents (`Task`) | `agent_spawn` (or `task` in the legacy runtime), recorded as `Task`; a subagent's calls are checked in its own session |
| Tools `Bash`, `Write`, `Edit`, `Read`, `Grep`, `WebFetch` | `bash`, `write_file`, `edit`, `read_file`, `grep`, `web_fetch` (hooks may get `file_system.bash` etc.); the arguments already have Claude Code's names |
| `~/.claude/AGENTLTL.yaml` | `~/.vibe/AGENTLTL.yaml` |
| Memory: `CLAUDE.md`, `.claude/rules/`, auto memory | Instructions: `AGENTS.md` (project and `~/.vibe/`), custom agents' `instructions` (`agents/*.toml`), prompts (`prompts/*.md`) |
| Built-in rule `memory-first` | the same, on Vibe's instruction files |
| Skills `/agentltl:setup`, `:rules`, `:import`, `:status` | `/agentltl-setup`, `/agentltl-rules`, `/agentltl-import`, `/agentltl-status` |
| Status line | Vibe has none: `/agentltl-status` and `agentltl trace` |
| Library `no-claude-coauthor`, `subagents-on-sonnet` | `no-vibe-coauthor` (Vibe's `Co-Authored-By: Mistral Vibe <vibe@mistral.ai>`); the Claude Code entries switch nothing on here |

## Hooks

| Event | Input used | Answer |
|---|---|---|
| `pre_tool` | `session_id`, `cwd`, `tool_name`, `tool_input` | `decision: deny`, `reason` and `system_message`; nothing when there is no objection |
| `post_tool` | `tool_status`, `tool_output_text`, `tool_error` | `hook_specific_output.additional_context`: the rules (first call of a session), a note the rules left on the call, a credential warning; `system_message` for the user |
| `post_agent` | `session_id` | `decision: deny` with what a `finally` rule still needs |

`pre_tool` is installed with `strict = true`: if the guard crashes or times out, Vibe refuses
the call. An internal error in the guard denies the call with the error. The guard never
answers `allow`: silence leaves the call to Vibe's own permissions. Vibe runs `pre_tool`
before its own permission check, so the rules hold under `--auto-approve` too.

Vibe runs the tool calls of one model turn in parallel, and their hooks too. The guard's
state is locked per call, so calls are recorded in the order their hooks run.

## Modes

| Mode | In Mistral Vibe |
|---|---|
| `block` | denied with the reason |
| `warn` | denied once; Vibe may repeat the exact same call to go ahead |
| `ask` | denied; Vibe asks you (`ask_user_question`), then the exact same call goes through once |
| `retry` | denied; after `retries` attempts, as `ask` |
| `stop` | denied, and every call is denied until you write again |
| `log` | allowed; Vibe gets the note with the call's result |

## Rules

The rule language is the same in every harness: see the
[rules reference](https://agentltl.github.io/rules/reference/) and the
[library](https://agentltl.github.io/rules/library/). In `agentltl check`, a step may name
Vibe's own tools: `'write_file {"file_path": ".env", "content": "x"}'`.

## State

Session and project traces live in the plugin's data directory (`sessions/`, `projects/`),
as in the Claude Code plugin: `agentltl trace` shows them, `agentltl reset` forgets them.

## Development

```bash
git clone --recurse-submodules https://github.com/AgentLTL/agentltl-mistral-vibe.git
scripts/setup.sh --dev && .venv/bin/pytest -q
```

`docker/Dockerfile` is an image with Mistral Vibe to try the plugin end to end on any
OpenAI-compatible model (see the README).
