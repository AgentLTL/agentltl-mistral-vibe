"""`agentltl install` edits ~/.vibe/hooks.toml: only its own block, idempotently."""

import os
import tomllib

from agentltl_vibe import install

USER_HOOKS = '''# my hooks
[[hooks]]
name = "lint"
type = "post_tool"
command = "ruff check"
match = "edit"
'''


def _hooks(path):
    with open(path, "rb") as fh:
        return tomllib.load(fh)["hooks"]


def test_install_keeps_the_users_hooks_and_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.setenv("VIBE_HOME", str(tmp_path / "vibe"))
    (tmp_path / "vibe").mkdir()
    path = tmp_path / "vibe" / "hooks.toml"
    path.write_text(USER_HOOKS)
    root = str(tmp_path / "it's here")

    assert install.install(root)[0]
    first = path.read_text()
    assert install.install(root) == (True, f"AgentLTL's hooks are already in {path}.")
    assert path.read_text() == first and install.installed(root)

    hooks = _hooks(path)
    assert [h["name"] for h in hooks] == ["lint", "agentltl-pre-tool", "agentltl-post-tool",
                                          "agentltl-post-agent"]
    pre = hooks[1]
    assert pre["type"] == "pre_tool" and pre["strict"] is True and pre["match"] == "*"
    posix_root = root.replace(os.sep, "/")
    assert pre["command"] == "'" + posix_root.replace("'", "'\\''") + "/hooks/run' pre_tool"
    assert "match" not in hooks[3] and "strict" not in hooks[3]

    assert install.install(str(tmp_path / "moved"))[1].startswith("Updated")
    assert len(_hooks(path)) == 4

    assert install.uninstall()[0]
    assert path.read_text() == USER_HOOKS
    assert install.uninstall() == (True, f"No AgentLTL hooks in {path}.")


def test_install_creates_the_file(tmp_path, monkeypatch):
    monkeypatch.setenv("VIBE_HOME", str(tmp_path / "vibe"))
    assert install.install("/opt/agentltl")[0]
    assert len(_hooks(tmp_path / "vibe" / "hooks.toml")) == 3
    install.uninstall()
    assert (tmp_path / "vibe" / "hooks.toml").read_text() == ""


def test_install_refuses_a_name_clash(tmp_path, monkeypatch):
    monkeypatch.setenv("VIBE_HOME", str(tmp_path))
    (tmp_path / "hooks.toml").write_text('[[hooks]]\nname = "agentltl-pre-tool"\n'
                                         'type = "pre_tool"\ncommand = "x"\n')
    ok, message = install.install("/opt/agentltl")
    assert not ok and "agentltl-pre-tool" in message
