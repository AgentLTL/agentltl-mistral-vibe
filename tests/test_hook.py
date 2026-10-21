"""The hook end to end: Mistral Vibe hook payloads in, hook JSON out."""

import json
import os
import shutil
import subprocess
import sys

import pytest
from agentltl_coding import store

from agentltl_vibe import hook

RULES = """
rules:
  - id: tests-before-push
    before: {first: pytest, then: git_push, since: [Edit, Write]}
    why: CI is slow.
  - id: no-secrets
    never: [Read, Edit, cat]
    where: {"*": "**/.env"}
    mode: stop
"""


@pytest.fixture
def project(tmp_path):
    root = tmp_path / "proj"
    (root / ".git").mkdir(parents=True)
    (root / "AGENTLTL.yaml").write_text(RULES)
    return root



def _json_path(path):
    """*path* as it is written inside a JSON string (backslashes escaped)."""
    return json.dumps(str(path))[1:-1]


def event(project, name, tool=None, args=None, **extra):
    payload = {"hook_event_name": name, "session_id": "s1", "transcript_path": "/t",
               "cwd": str(project), "parent_session_id": None, **extra}
    if tool:
        payload.update(tool_name=tool, tool_input=args or {})
        payload.setdefault("tool_call_id", "c1")
    return hook.run(name, payload)


def pre(project, tool, args, **kw):
    return event(project, "pre_tool", tool, args, **kw)


def post(project, tool, args, text="", status="success", **kw):
    return event(project, "post_tool", tool, args, tool_status=status, tool_output=None,
                 tool_output_text=text, tool_error=None if status == "success" else text,
                 duration_ms=0, **kw)


def finish(project, **kw):
    return event(project, "post_agent", **kw)


def bash(command):
    return "file_system.bash", {"command": command, "timeout": None}


def told(project):
    """The first post_tool of a session lists the rules; get it out of the way."""
    post(project, *bash("true"))


def test_scenario(project):
    deny = pre(project, *bash("git push"))
    assert deny["decision"] == "deny" and "tests-before-push" in deny["reason"]
    assert deny["system_message"] == "AgentLTL: rule 'tests-before-push' refused bash git push"

    post(project, *bash("pytest -q"), "3 passed")
    assert pre(project, *bash("git push")) is None              # silent: no objection

    # an edit that was proposed but never ran does not count; one that ran does
    edit = ("file_system.search_replace",
            {"file_path": str(project / "a.py"), "old_string": "a", "new_string": "b",
             "replace_all": False})
    assert pre(project, *edit) is None
    assert pre(project, *bash("git push")) is None
    post(project, *edit)
    assert pre(project, *bash("git push"))["decision"] == "deny"


def test_short_and_qualified_names_are_the_same_tool(project):
    (project / "a.txt").write_text("x")
    (project / "AGENTLTL.yaml").write_text("use: [read-before-overwrite]")
    write = {"file_path": str(project / "a.txt"), "content": "y"}
    assert pre(project, "file_system.write_file", write)["decision"] == "deny"
    post(project, "read_file", {"file_path": str(project / "a.txt")})
    assert pre(project, "write_file", write) is None


def test_the_first_call_of_a_session_brings_the_rules(project):
    out = post(project, *bash("ls"), "a")
    text = out["hook_specific_output"]["additional_context"]
    assert "tests-before-push" in text and "memory-first" in text and "/agentltl:rules" in text
    assert "subagents-unchecked" in text
    assert out["system_message"].startswith("AgentLTL: 4 rule(s) in force")
    assert post(project, *bash("ls"), "a") is None                       # once
    assert post(project, *bash("ls"), "a", session_id="s2") is not None  # per session


def test_stop_denies_everything_until_the_user_writes(project):
    told(project)
    out = pre(project, "read_file", {"file_path": str(project / ".env")})
    assert out["decision"] == "deny" and "stops the session" in out["reason"]
    held = pre(project, *bash("ls"))
    assert held["decision"] == "deny" and "stopped this session" in held["reason"]
    assert finish(project) is None                         # Vibe ends its turn...
    assert pre(project, *bash("ls")) is None               # ...so the user wrote


def test_ask_rules_refuse_until_vibe_has_asked_the_user(project):
    (project / "AGENTLTL.yaml").write_text("rules: [{id: no-rm, never: rm, mode: ask}]")
    rm = bash("rm -rf build")
    out = pre(project, *rm)
    assert out["decision"] == "deny" and "no-rm" in out["reason"]
    assert "ask_user_question" in out["reason"] and "Allow this call anyway?" not in out["reason"]
    assert pre(project, *rm)["decision"] == "deny"         # repeating alone is not enough
    post(project, "ask_user_question", {"questions": [{"question": "rm -rf build?"}]}, "Yes")
    assert pre(project, *rm) is None                       # asked: goes through, once
    assert [d["action"] for d in store.read("s1")["decisions"]] == ["ask", "ask", "ok"]
    assert pre(project, *rm)["decision"] == "deny"
    assert pre(project, *bash("rm -rf dist"))["decision"] == "deny"   # only that call


def test_ask_rules_go_through_after_a_new_turn(project):
    (project / "AGENTLTL.yaml").write_text("rules: [{id: no-rm, never: rm, mode: ask}]")
    assert pre(project, *bash("rm x"))["decision"] == "deny"
    finish(project)
    assert pre(project, *bash("rm x")) is None


def test_ask_rules_unattended_are_refused(project, monkeypatch):
    monkeypatch.setenv("AGENTLTL_AUTO", "1")
    (project / "AGENTLTL.yaml").write_text("rules: [{id: no-rm, never: rm, mode: ask}]")
    out = pre(project, *bash("rm x"))
    assert out["decision"] == "deny" and "unattended" in out["reason"]
    post(project, "ask_user_question", {}, "Yes")
    assert pre(project, *bash("rm x"))["decision"] == "deny"


def test_a_note_on_an_allowed_call_comes_with_its_result(project):
    (project / "AGENTLTL.yaml").write_text("rules: [{id: no-sudo, never: sudo, mode: log, why: w}]")
    told(project)
    assert pre(project, *bash("sudo ls")) is None
    out = post(project, *bash("sudo ls"), "x")
    assert "no-sudo" in out["hook_specific_output"]["additional_context"]
    assert post(project, *bash("sudo ls"), "x") is None          # given once


def test_credentials_in_output(project):
    told(project)
    out = post(project, *bash("cat config"), "key=" + "AKIA" + "ABCDEFGHIJKLMNOP")
    assert "AWS access key ID" in out["hook_specific_output"]["additional_context"]
    assert "AWS access key ID" in out["system_message"]


def test_failed_and_cancelled_calls(project):
    post(project, *bash("pytest"), "exit 1", status="failure")
    post(project, *bash("ruff check"), "x", status="cancelled")      # never ran
    event(project, "post_tool", *bash("make"), tool_status="success",
          tool_output={"stdout": "", "returncode": 2}, tool_output_text="")
    post(project, *bash("ls"), "a")
    calls = store.read("s1")["completed_tool_calls"]
    assert [(c["tool_name"], c["status"]) for c in calls] == [("pytest", 1), ("make", 1),
                                                              ("ls", 0)]


def test_a_finally_rule_sends_vibe_back_once_per_turn(project):
    (project / "AGENTLTL.yaml").write_text("settings: {finish_retries: 1}\n"
                                           "rules: [{id: tested, finally: pytest}]")
    first = finish(project)
    assert first["decision"] == "deny" and "tested" in first["reason"]
    assert first["system_message"].startswith("AgentLTL sent Vibe back:")
    assert finish(project) is None                  # retries used up: the turn ends
    pre(project, *bash("ls"))                       # the user wrote again
    assert finish(project)["decision"] == "deny"


def test_broken_file_is_told_once_and_calls_go_ahead(project):
    (project / "AGENTLTL.yaml").write_text("rules: [{id: x, nevr: rm}]")
    assert pre(project, *bash("rm x")) is None
    out = post(project, *bash("rm x"))
    assert "NO AGENTLTL rules are being enforced" in out["hook_specific_output"]["additional_context"]
    assert post(project, *bash("ls")) is None


def test_no_rule_file_is_silent(tmp_path):
    (tmp_path / ".git").mkdir()
    assert hook.run("pre_tool", {"cwd": str(tmp_path), "tool_name": "bash",
                                 "tool_input": {"command": "rm -rf /"}}) is None


def test_internal_error_denies_instead_of_failing_open(project, monkeypatch):
    from agentltl_coding import Session
    monkeypatch.setattr(Session, "pre", lambda *a, **k: 1 / 0)
    out = pre(project, *bash("ls"))
    assert out["decision"] == "deny" and "could not be checked" in out["reason"]


def test_subagents_are_their_own_sessions(project):
    post(project, *bash("pytest"), session_id="child", parent_session_id="s1")
    assert pre(project, *bash("git push"), session_id="child", parent_session_id="s1") is None
    assert pre(project, *bash("git push"))["decision"] == "deny"


def test_project_memory_spans_sessions(project):
    (project / "AGENTLTL.yaml").write_text(
        "rules: [{id: tests-ever, before: [pytest, git_push], scope: project}]")
    post(project, *bash("pytest"), session_id="a")
    assert pre(project, *bash("git push"), session_id="b") is None
    assert store.read("b").get("project_dir") == str(project)


def test_the_project_is_vibes_project_dir(project, monkeypatch):
    sub = project / "src"
    sub.mkdir()
    monkeypatch.setenv("VIBE_PROJECT_DIR", str(project))
    assert pre(project, *bash("git push"), cwd=str(sub))["decision"] == "deny"
    assert store.read("s1")["project_dir"] == str(project)


def test_launcher(project):
    """hooks/run with the test Python: payload on stdin, JSON on stdout."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env = dict(os.environ, AGENTLTL_VIBE_PYTHON=sys.executable,
               PYTHONPATH=os.pathsep.join(sys.path))
    payload = json.dumps({"session_id": "s1", "cwd": str(project), "tool_name": "file_system.bash",
                          "tool_call_id": "c", "tool_input": {"command": "git push"}})
    out = subprocess.run([shutil.which("bash"), os.path.join(root, "hooks", "run"), "pre_tool"], input=payload,
                         capture_output=True, text=True, env=env, cwd=str(project), check=True)
    assert json.loads(out.stdout)["decision"] == "deny"


# ── what Mistral Vibe 2.26.0 actually sends (tests/fixtures/payloads) ─────────

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "payloads", "vibe-2.26.0.json")


def _replay(root, session):
    out = []
    for e in session:
        payload = json.loads(json.dumps(e["payload"]).replace("/work", _json_path(root)))
        answer = hook.run(e["event"], payload)
        if e["event"] == "pre_tool":
            out.append((payload["tool_name"].rsplit(".", 1)[-1], answer and answer["decision"]))
    return out


def test_captured_sessions_replay(tmp_path):
    root = tmp_path / "work"
    (root / ".git").mkdir(parents=True)
    (root / "AGENTLTL.yaml").write_text(
        "use: [no-vibe-coauthor, read-before-overwrite]\n"
        "rules:\n  - {id: tests, before: [pytest, git_commit]}\n")
    with open(FIXTURE) as fh:
        first, second, third = json.load(fh)["sessions"]

    assert _replay(root, first) == [("bash", None), ("search_replace", None), ("bash", None),
                                    ("bash", None), ("bash", None), ("bash", "deny")]
    calls = store.read(first[0]["payload"]["session_id"])["completed_tool_calls"]
    assert [(c["tool_name"], c.get("status")) for c in calls] == [
        ("ls", 0), ("Edit", 1), ("false", 1), ("echo", 0), ("echo", 0),
        ("git_add", None), ("git_commit", 1)]      # the commit failed (no commits yet)

    assert _replay(root, second) == [("write_file", None), ("read_file", None),
                                     ("bash", None), ("bash", None), ("bash", None)]
    assert _replay(root, third) == [("spawn", "deny"), ("wait", None)]


def test_a_subagent_is_a_warning_and_the_user_is_told(project):
    told(project)
    spawn = ("subagent.spawn", {"agentName": "kid", "message": "look around"})
    out = pre(project, *spawn)
    assert out["decision"] == "deny" and "subagents-unchecked" in out["reason"]
    assert pre(project, *spawn) is None                          # Vibe insists: allowed
    assert "not checked" in post(project, *spawn)["system_message"]
    (project / "AGENTLTL.yaml").write_text("settings: {subagents_unchecked: false}\n" + RULES)
    assert pre(project, "subagent.spawn", {"agentName": "k2", "message": "x"}) is None


def test_calls_from_run_typescript_dont_use_up_the_rule_list(project):
    nested = post(project, *bash("echo a"), tool_call_id="typescript:11:call_x:0:tool:0")
    assert nested is None
    assert "tests-before-push" in post(project, *bash("ls"))["hook_specific_output"][
        "additional_context"]


def test_tool_names():
    from agentltl_vibe import tool_name
    assert [tool_name(n) for n in ("file_system.bash", "file_system.search_replace", "bash",
                                   "subagent.spawn", "subagent.sendMessage", "web_fetch.web_fetch",
                                   "vibe.todo", "github.create_issue", "my_mcp_tool")] == [
        "bash", "edit", "bash", "agent_spawn", "sendMessage", "web_fetch", "todo",
        "github_create_issue", "my_mcp_tool"]


def test_launcher_ignores_the_callers_python_path(tmp_path):
    """A PYTHONPATH from the user's shell (another project's virtualenv) must not reach the
    plugin's Python: its packages would shadow the plugin's own."""
    import pytest
    if sys.platform == "win32":
        pytest.skip("the stub interpreter is a shell script")
    src = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    root = tmp_path / "plugin"
    shutil.copytree(os.path.join(src, "hooks"), root / "hooks")
    shutil.copytree(os.path.join(src, "scripts"), root / "scripts")
    shutil.copy(os.path.join(src, "vendor.lock"), root / "vendor.lock")
    (root / ".venv" / "bin").mkdir(parents=True)
    shutil.copy(root / "vendor.lock", root / ".venv" / "vendor.lock")
    stub = root / ".venv" / "bin" / "python"
    stub.write_text('#!/bin/sh\necho "[$PYTHONPATH][$PYTHONHOME]" > "$MARK"\n')
    stub.chmod(0o755)
    mark = tmp_path / "mark"
    env = {k: v for k, v in os.environ.items() if k != "AGENTLTL_VIBE_PYTHON"}
    env.update(HOME=str(tmp_path / "home"), MARK=str(mark),
               PYTHONPATH="/elsewhere/site-packages", PYTHONHOME="/elsewhere")
    subprocess.run([shutil.which("bash"), str(root / "hooks" / "run"), "pre_tool"], input="{}",
                   capture_output=True, text=True, env=env, cwd=str(tmp_path))
    assert mark.read_text().strip() == f"[{root}/src][]"
