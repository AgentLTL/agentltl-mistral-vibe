"""
agentltl_vibe/cli.py – the ``agentltl`` command of the Mistral Vibe plugin.

Everything agentltl_coding's command does (validate, check, translate, tools, trace, reset,
library, use/unuse, disable/enable, and memory scan/decline/forget over Vibe's instructions),
plus what is Mistral Vibe's own:

    agentltl install [--no-cli]          add AgentLTL's hooks to ~/.vibe/hooks.toml, and put
                                         `agentltl` on your PATH (a link in ~/.local/bin)
    agentltl uninstall                   remove the hooks (the rule files stay)
    agentltl update                      pull the latest plugin version, then install again
    agentltl install-cli [--dir DIR]     only the link

``check`` steps may name Vibe's own tools: ``'write_file {"file_path": ".env", "content": "x"}'``.
"""

from __future__ import annotations

import argparse
import os
import shlex
import subprocess
import sys
from typing import Any, Callable, Dict, List, Optional

from agentltl_coding.cli import main as _main

from . import MISTRAL_VIBE  # noqa: F401  (configures the harness)

PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main(argv: Optional[List[str]] = None) -> int:
    return _main(argv, extend=_extend)


def _extend(sub: Any, commands: Dict[str, Callable[[argparse.Namespace], int]]) -> None:
    p = sub.add_parser("install", help="add AgentLTL's hooks to Vibe (~/.vibe/hooks.toml)")
    p.add_argument("--no-cli", action="store_true", help="don't link `agentltl` into ~/.local/bin")
    sub.add_parser("uninstall", help="remove AgentLTL's hooks from Vibe")
    sub.add_parser("update", help="pull the latest plugin version and install it")
    p = sub.add_parser("install-cli", help="put `agentltl` on your PATH")
    p.add_argument("--dir", default=os.path.join("~", ".local", "bin"),
                   help="where to put the link (default: ~/.local/bin)")
    commands["install"] = _install
    commands["uninstall"] = _uninstall
    commands["update"] = _update
    commands["install-cli"] = _install_cli


def _install(args: argparse.Namespace) -> int:
    from . import install
    ok, message = install.install(PLUGIN_ROOT)
    print(message, file=sys.stdout if ok else sys.stderr)
    if ok and not getattr(args, "no_cli", False):
        _install_cli(argparse.Namespace(dir=os.path.join("~", ".local", "bin")), quiet_clash=True)
    return 0 if ok else 1


def _uninstall(args: argparse.Namespace) -> int:
    from . import install
    ok, message = install.uninstall()
    print(message, file=sys.stdout if ok else sys.stderr)
    return 0 if ok else 1


def _update(args: argparse.Namespace) -> int:
    if not os.path.isdir(os.path.join(PLUGIN_ROOT, ".git")):
        print(f"{PLUGIN_ROOT} is not a git checkout; update it the way you installed it.",
              file=sys.stderr)
        return 1
    for cmd in (["git", "pull", "--ff-only"],
                ["git", "submodule", "update", "--init", "--recursive"]):
        if subprocess.run(cmd, cwd=PLUGIN_ROOT).returncode != 0:
            return 1
    # The new version's code runs in a new process: its own install, its own environment.
    return subprocess.run([os.path.join(PLUGIN_ROOT, "bin", "agentltl"), "install"]).returncode

LINK_MARK = "# agentltl: runs "


def _link(target: str, link: str) -> None:
    """Symlink `link` to `target`. Where symlinks are not allowed (Windows without developer
    mode or administrator rights), write a small script that runs it instead."""
    try:
        os.symlink(target, link)
        return
    except FileExistsError:
        raise                       # another install-cli got there first: do not write through it
    except (OSError, NotImplementedError):
        pass
    posix = target.replace("\\", "/")
    # "x": never open what exists, a symlink another process just made included.
    with open(link, "x", encoding="utf-8", newline="\n") as fh:
        fh.write(f'#!/usr/bin/env bash\n{LINK_MARK}{posix}\nexec {shlex.quote(posix)} "$@"\n')
    os.chmod(link, 0o755)


def _links_to(link: str, target: str) -> bool:
    if os.path.realpath(link) == os.path.realpath(target):
        return True
    try:
        with open(link, encoding="utf-8", errors="replace") as fh:
            return f"{LINK_MARK}{target.replace(chr(92), '/')}\n" in fh.read(4096)
    except OSError:
        return False


def _install_cli(args: argparse.Namespace, quiet_clash: bool = False) -> int:
    folder = os.path.expanduser(args.dir)
    target = os.path.join(PLUGIN_ROOT, "bin", "agentltl")
    link = os.path.join(folder, "agentltl")
    if os.path.lexists(link):
        if _links_to(link, target):
            return 0
        print(f"{link} exists and is not this plugin's; not linked. Run {target} directly.",
              file=sys.stderr)
        return 0 if quiet_clash else 1
    os.makedirs(folder, exist_ok=True)
    _link(target, link)
    on_path = folder in os.environ.get("PATH", "").split(os.pathsep)
    print(f"{link} -> {target}" + ("" if on_path else f"\n{folder} is not on your PATH yet."))
    return 0


__all__ = ["main"]

if __name__ == "__main__":
    sys.exit(main())
