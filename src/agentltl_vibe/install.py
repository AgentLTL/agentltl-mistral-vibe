"""
agentltl_vibe/install.py – put AgentLTL's hooks into Mistral Vibe's ``hooks.toml``.

Vibe runs the hooks listed in ``$VIBE_HOME/hooks.toml`` (and a trusted project's
``.vibe/hooks.toml``); hooks shipped inside a plugin folder are not run. So installing writes
three ``[[hooks]]`` entries, between two marker comments, at the end of the user's file, and
uninstalling removes them. The rest of the file is left as it is.
"""

from __future__ import annotations

import os
import re
from typing import Tuple

from . import vibe_home

BEGIN = "# >>> agentltl (managed by `agentltl install`; `agentltl uninstall` removes it)"
END = "# <<< agentltl"
_BLOCK = re.compile(re.escape(BEGIN) + r".*?" + re.escape(END) + r"\n?", re.S)
NAMES = ("agentltl-pre-tool", "agentltl-post-tool", "agentltl-post-agent")


def hooks_file() -> str:
    return os.path.join(vibe_home(), "hooks.toml")


def block(plugin_root: str) -> str:
    run = os.path.join(plugin_root, "hooks", "run")
    cmd = lambda event: _toml_str(f"{_sh(run)} {event}")  # noqa: E731
    return "\n".join([
        BEGIN,
        "[[hooks]]",
        'name = "agentltl-pre-tool"',
        'type = "pre_tool"',
        f"command = {cmd('pre_tool')}",
        'match = "*"',
        "timeout = 120.0          # the first call of a new plugin version builds its environment",
        "strict = true            # if the guard can't answer, the call is refused",
        'description = "AgentLTL: refuse calls that break AGENTLTL.yaml"',
        "",
        "[[hooks]]",
        'name = "agentltl-post-tool"',
        'type = "post_tool"',
        f"command = {cmd('post_tool')}",
        'match = "*"',
        "timeout = 60.0",
        'description = "AgentLTL: record the calls that ran"',
        "",
        "[[hooks]]",
        'name = "agentltl-post-agent"',
        'type = "post_agent"',
        f"command = {cmd('post_agent')}",
        "timeout = 60.0",
        'description = "AgentLTL: send Vibe back while a `finally` rule is unmet"',
        END,
        "",
    ])


def install(plugin_root: str) -> Tuple[bool, str]:
    path = hooks_file()
    text = _read(path)
    rest = _BLOCK.sub("", text)
    clash = [n for n in NAMES if re.search(rf'^\s*name\s*=\s*"{n}"', rest, re.M)]
    if clash:
        return False, (f"{path} already has hooks named {', '.join(clash)} outside AgentLTL's "
                       "block; remove them and run `agentltl install` again.")
    rest = rest.rstrip("\n")
    new = (rest + "\n\n" if rest.strip() else "") + block(plugin_root)
    if new == text:
        return True, f"AgentLTL's hooks are already in {path}."
    _write(path, new)
    verb = "Updated" if _BLOCK.search(text) else "Added"
    return True, f"{verb} AgentLTL's hooks in {path}. They apply from the next Vibe session."


def uninstall() -> Tuple[bool, str]:
    path = hooks_file()
    text = _read(path)
    if not _BLOCK.search(text):
        return True, f"No AgentLTL hooks in {path}."
    rest = _BLOCK.sub("", text).rstrip("\n")
    _write(path, rest + "\n" if rest.strip() else "")
    return True, f"Removed AgentLTL's hooks from {path}."


def installed(plugin_root: str) -> bool:
    return block(plugin_root) in _read(hooks_file())


def _read(path: str) -> str:
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except FileNotFoundError:
        return ""


def _write(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".agentltl-tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(text)
    os.replace(tmp, path)


def _sh(word: str) -> str:
    """*word* quoted for the shell Vibe runs a hook command with."""
    return "'" + word.replace("'", "'\\''") + "'"


def _toml_str(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


__all__ = ["BEGIN", "END", "block", "hooks_file", "install", "installed", "uninstall"]
