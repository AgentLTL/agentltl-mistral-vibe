"""
agentltl_vibe/memory.py – where Mistral Vibe's instructions live.

Vibe reads ``AGENTS.md`` (the project's, from its root down a trusted folder chain) and the
user's ``~/.vibe/AGENTS.md``; custom agents carry ``instructions`` in ``~/.vibe/agents/*.toml``
(or the project's ``.vibe/agents/``), and custom system prompts live in ``prompts/*.md``.
:func:`vibe_sources` lists the files that apply; the scanner is agentltl_coding's
(:mod:`agentltl_coding.memory`), re-exported here.
"""

from __future__ import annotations

import os
from typing import List

from agentltl_coding.memory import *  # noqa: F401,F403  (scan, split, decline, ...)
from agentltl_coding.memory import PROJECT, USER, Source, files, nested


def _vibe_dir(base: str, scope: str) -> List[Source]:
    out = [Source(os.path.join(base, "AGENTS.md"), "agents-md", scope)]
    out += [Source(p, "instructions", scope)
            for p in files(os.path.join(base, "agents"), "*.toml")]
    out += [Source(p, "instructions", scope)
            for p in files(os.path.join(base, "prompts"), "*.md")]
    return out


def vibe_sources(root: str, user_only: bool, home: str) -> List[Source]:
    """The instruction files that apply in project *root*, then the user's. With *user_only*,
    only the user's."""
    base = os.environ.get("VIBE_HOME") or os.path.join(home, ".vibe")
    user = _vibe_dir(base, USER)
    if user_only:
        return user
    out = [Source(os.path.join(root, "AGENTS.md"), "agents-md", PROJECT)]
    out += [Source(p, "agents-md", PROJECT) for p in nested(root, "AGENTS.md")]
    out += _vibe_dir(os.path.join(root, ".vibe"), PROJECT)[1:]
    return out + user
