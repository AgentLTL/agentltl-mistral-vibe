# Setting up AgentLTL for Mistral Vibe

These instructions are for Mistral Vibe. A user pasted a prompt asking you to set up this
plugin. Follow the steps in order. Say briefly what you are doing at each step, and stop to ask
the user only where a step says so.

The plugin checks every tool call against the rules in an `AGENTLTL.yaml` file, and refuses
calls that break them. Vibe has no plugin installer, so the plugin is a clone in
`~/.vibe/plugins/agentltl` plus an `install` step that registers its hooks. The only file that
lives in a project is `AGENTLTL.yaml`, at the project root (or in `~/.vibe/` to apply to every
project).

## 1. Check the prerequisites

Run `python3 --version`, `git --version` and `vibe --version`.

- **Python 3.10 or newer, git, and Mistral Vibe 2.26 or later:** all are needed. If one is
  missing or too old, stop and tell the user what to install. On macOS that is
  `brew install python git`; on Debian or Ubuntu, `sudo apt install python3 python3-venv git`.
- **`python3 -m venv`:** run `python3 -m venv --help > /dev/null`. On Debian and Ubuntu it can
  be missing even when Python is installed; the fix is `sudo apt install python3-venv`.

## 2. Look for an earlier setup

If `~/.vibe/plugins/agentltl` already exists, the plugin was installed before: run
`~/.vibe/plugins/agentltl/bin/agentltl update`, then skip to step 4.

## 3. Install the plugin

```bash
git clone --recurse-submodules https://github.com/AgentLTL/agentltl-mistral-vibe.git ~/.vibe/plugins/agentltl
~/.vibe/plugins/agentltl/bin/agentltl install
```

`install` builds the plugin's Python environment (in `~/.vibe/plugin-data/agentltl`, 10 to 30
seconds), adds AgentLTL's three hooks to `~/.vibe/hooks.toml` (the user's own hooks there are
kept), and links the `agentltl` command into `~/.local/bin`. Check that `~/.local/bin` is on the
PATH; if it is not, tell the user, and write `~/.vibe/plugins/agentltl/bin/agentltl` wherever
the steps below say `agentltl`.

## 4. Choose the first rules, with the user

The plugin ships a library of tested rules the user can switch on by name. Start there:
read `~/.vibe/plugins/agentltl/skills/setup/SKILL.md` and follow it. Run the commands from
the project root.

Then ask whether there is anything else Vibe should never do, or always do first, in this
project. For each answer, write a rule following
`~/.vibe/plugins/agentltl/skills/rules/SKILL.md`. In short:

- **Tool names:** rules use the names commands translate to. Check with
  `agentltl translate "git push --force"`.
- **Explain each rule:** give every rule a `why` (Vibe sees it when blocked) and a `mode`
  matching how strict the user wants it: `block`, `warn`, `ask`, `retry`, `stop` or `log`.
- **Test before saving:** check each rule against commands it should and should not stop:
  `agentltl check --add draft.yaml "deny: git push --force" "allow: git push"`.
  Fix it until every line ends in `ok` and there is no `WARNING`.

Show the user the final `agentltl validate` output.

## 5. Finish

Tell the user:

1. **Activate it:** restart Vibe. The plugin is active from then on, in every project that has
   an `AGENTLTL.yaml`.
2. **Try it:** ask Vibe to do something a rule forbids, and watch it get refused with the
   rule's reason.
3. **Browse the library again:** `/agentltl:setup`.
4. **Add or remove rules in plain words:** `/agentltl:rules never touch the lockfile`, or just
   ask Vibe.
5. **See what it is doing:** `/agentltl:status` shows the rules in force and what the guard
   recently blocked.
6. **Updating and removing:** `agentltl update`; `agentltl uninstall`, then delete the folder.

## Troubleshooting

- **`agentltl: command not found`:** `~/.local/bin` is not on the PATH. Use the full path
  `~/.vibe/plugins/agentltl/bin/agentltl`.
- **Install fails with `ensurepip` or `No module named venv`:** install `python3-venv` (step 1).
- **Submodules are empty:** the clone was made without `--recurse-submodules`. Run
  `git -C ~/.vibe/plugins/agentltl submodule update --init`, or install again; without them the
  dependencies come from GitHub at the pinned commits.
- **Every call is refused with "AgentLTL ... is not installed", or "could not run its guard":**
  the environment could not be built, or its Python stopped working (upgraded or removed,
  `Could not import runpy module`). The hook already tried to rebuild it once. Run
  `agentltl doctor`: it names the Python in use, what it fails to import, and the variables that
  can break it; then run `agentltl install` again and read its error.
- **A rule never fires:** run `agentltl validate` and fix any `WARNING`. It means a tool or
  argument name that no command produces.
