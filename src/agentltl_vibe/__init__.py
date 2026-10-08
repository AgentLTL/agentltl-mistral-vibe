"""AgentLTL rules in front of Mistral Vibe's tool calls.

The rules, the guard, the hooks' logic and the library are agentltl_coding's; this package is
the Mistral Vibe side: the hook I/O, where its instructions live, and the harness description
below. Rules use the canonical tool names (``Bash``, ``Write``, ``Edit``, ``Read``...), so
the library and a project's AGENTLTL.yaml work as in Claude Code; Vibe's own names are
mapped onto them.
"""

import os

from agentltl_coding import Harness, configure


def vibe_home() -> str:
    """Mistral Vibe's configuration directory (``VIBE_HOME``, else ``~/.vibe``)."""
    return os.environ.get("VIBE_HOME") or os.path.join(os.path.expanduser("~"), ".vibe")


# Vibe's default runtime names its built-in tools by group (``file_system.bash``); hooks get
# that qualified name. What the model calls each one (from Vibe's _hook_matcher.py):
QUALIFIED = {
    "file_system.read_file": "read_file",
    "file_system.write_file": "write_file",
    "file_system.search_replace": "edit",
    "file_system.bash": "bash",
    "skill.read": "skill",
    "subagent.spawn": "agent_spawn",
    "subagent.list": "agent_list",
    "subagent.wait": "agent_wait",
    "subagent.send_message": "agent_message",
    "subagent.interrupt": "agent_interrupt",
    "subagent.stop": "agent_stop",
    "process.start": "process_start",
    "process.output": "process_output",
    "process.write": "process_write",
    "process.list": "process_list",
    "process.stop": "process_stop",
    "self.sleep": "sleep",
}

# Vibe's tools and their arguments, under the names rules use. Vibe's hooks already give the
# arguments Claude Code's names (file_path, content, old_string, new_string).
TOOL_ALIASES = {
    "bash": ("Bash", {}),
    "write_file": ("Write", {}),
    "edit": ("Edit", {}),
    "search_replace": ("Edit", {}),
    "read_file": ("Read", {}),
    "read": ("Read", {}),
    "grep": ("Grep", {}),
    "web_fetch": ("WebFetch", {}),
    "web_search": ("WebSearch", {}),
    "task": ("Task", {"task": "prompt", "agent": "subagent_type"}),
    "agent_spawn": ("Task", {"message": "prompt", "agentType": "subagent_type",
                             "agentName": "description"}),
}

# Vibe's default runtime runs no hooks inside a subagent: its calls are not checked. Unless
# `subagents_unchecked: false`, spawning one is a warning Vibe can override by repeating it.
SUBAGENTS_UNCHECKED = {
    "id": "subagents-unchecked",
    "never": "Task",
    "mode": "warn",
    "why": "Mistral Vibe runs no hooks inside subagents, so AGENTLTL can't check the calls a "
           "subagent makes; the rules would not hold there.",
    "fix": "Do this work yourself, so the rules apply. If a subagent really is the better way "
           "(read-only exploration, for example), repeat this exact call; the user is told.",
}


_BUILTIN_GROUPS = {"file_system", "subagent", "process", "self", "skill", "vibe"}  # vibe.todo


def tool_name(name: str) -> str:
    """The name the model uses for a tool, from the (possibly qualified) name a hook gets:
    ``file_system.bash`` is ``bash``, ``web_fetch.web_fetch`` is ``web_fetch``, and another
    connector's ``github.create_issue`` is ``github_create_issue`` (how MCP tools are named)."""
    if name in QUALIFIED:
        return QUALIFIED[name]
    group, dot, leaf = name.partition(".")
    if not dot:
        return name
    if group == leaf or group in _BUILTIN_GROUPS:
        return leaf
    return f"{group}_{leaf}"


# Files Vibe reads as instructions, and the ways a call writes them.
MEMORY_FILES = ["AGENTS.md", "*/.vibe/agents/*.toml", "*/.vibe/prompts/*.md"]
MEMORY_FIRST = {
    "id": "memory-first",
    "never": [{"tool": ["Write", "Edit"], "where": {"file_path": MEMORY_FILES}},
              {"tool": "*", "where": {"redirect_to": MEMORY_FILES}},
              {"tool": ["tee", "sponge"], "where": {"*": MEMORY_FILES}}],
    "mode": "warn",
    "why": "AGENTLTL rules are enforced on every call; instructions can be forgotten. If what you "
           "are saving says which tool calls or commands to make, avoid, or make first (never X, "
           "always Y before Z, at most N times, only with these arguments), add it to "
           "AGENTLTL.yaml instead, using the /agentltl-rules skill, and leave it out of the "
           "instructions.",
    "fix": "Write the rule with the /agentltl-rules skill. Keep in the instructions only what no "
           "rule can check (facts, preferences, style). If nothing here can be a rule, repeat "
           "this exact call to save it.",
}
MEMORY_NOTE = ("before you add anything to instructions (AGENTS.md, an agent's instructions or "
               "prompt), ask whether it is a rule about tool calls or commands. If it is, add it "
               "to AGENTLTL.yaml with the /agentltl-rules skill instead: rules there are "
               "enforced, instructions can be forgotten.")


def _memory(root, user_only, home):
    from .memory import vibe_sources
    return vibe_sources(root, user_only, home)


MISTRAL_VIBE = Harness(
    name="mistral-vibe",
    agent="Vibe",
    user_dir=os.environ.get("VIBE_HOME") or "~/.vibe",
    shell_tools={"Bash": "command"},
    tool_aliases=TOOL_ALIASES,
    builtins={"memory_first": MEMORY_FIRST, "subagents_unchecked": SUBAGENTS_UNCHECKED},
    project_env="VIBE_PROJECT_DIR",
    skill="/agentltl-{}",
    memory=_memory,
    memory_note=MEMORY_NOTE,
)
configure(MISTRAL_VIBE)
