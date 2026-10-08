"""
agentltl_vibe/hook.py – the Mistral Vibe hook: ``python -m agentltl_vibe.hook EVENT`` reads the
event JSON on stdin and prints the hook's JSON answer (``hooks.toml``, see ``install.py``).

    pre_tool    deny a call that breaks a rule (a `stop` denies every call until the user
                writes), else stay silent
    post_tool   add the call that ran to the session and project traces (status 0, or 1 when
                it failed); pass on a note the rules left on the call, warn when its output
                contains a credential, and, on a session's first call, list the rules
    post_agent  Vibe is about to finish: while a `finally` rule is unmet, send it back with
                what is missing (at most settings.finish_retries times a turn)

Without an AGENTLTL.yaml (project or ``~/.vibe``) it exits at once. It never approves a call:
silence leaves the decision to Vibe's own permissions. An internal error during pre_tool
denies the call, so a broken guard is visible instead of failing open.

Vibe's hooks have no session start, no user prompt event and no "ask" answer. So:

- the rules in force reach Vibe with the result of its first call in a session, and each
  refusal names its rule;
- a turn that ends (post_agent lets Vibe finish) means the next call follows a new message
  from the user: a `stop` is lifted, and `finally` rules may send Vibe back again;
- an `ask` rule refuses the call and tells Vibe to ask the user (``ask_user_question``); the
  exact same call then goes through once, after Vibe asked or the user wrote.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from typing import Any, Dict, Optional, Tuple

from . import MISTRAL_VIBE, tool_name  # noqa: F401  (configures the harness)

_NOTES = "vibe_notes"                 # notes from pre_tool for post_tool
_ASKS = "vibe_asks"                   # call key -> "asked" | "answered"
_TURN_ENDED = "vibe_turn_ended"       # post_agent let Vibe finish: the user writes next
_TOLD = "vibe_told"                   # the rules were listed to Vibe in this session
ASK_TOOL = "ask_user_question"

_ASK_TAIL = (
    "Nothing was executed. Vibe's hooks can't ask the user directly, so do it yourself: show "
    "the user this call and why the rule asks for approval, with the ask_user_question tool "
    "if you have it, otherwise in your reply, ending your turn there. If they approve, repeat "
    "exactly the same call and it will go through. If they decline, don't retry it or work "
    "around the rule; ask them what they want instead.")


def main(argv: Optional[list] = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        return 0
    out = run(argv[0] if argv else "", payload if isinstance(payload, dict) else {})
    if out:
        sys.stdout.write(json.dumps(out))
    return 0


def run(event: str, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """The hook's answer to one event, or None for no output."""
    event = event or payload.get("hook_event_name", "")
    try:
        from agentltl_coding import Session
        from agentltl_coding.cli import _git_root
        cwd = payload.get("cwd") or os.getcwd()
        project = os.environ.get("VIBE_PROJECT_DIR") or _git_root(cwd) or cwd
        session = Session(cwd, project, payload.get("session_id"))
        if not session.files:
            return None
        return _handle(event, payload, session)
    except Exception as exc:  # the guard must not fail open silently
        return _failure(event, exc)


def _handle(event: str, payload: Dict[str, Any], session: Any) -> Optional[Dict[str, Any]]:
    from agentltl_coding.rules import RuleFileError

    if event == "pre_tool":
        _maybe_new_turn(session)
    try:
        session.ruleset
    except RuleFileError as exc:
        return _broken_file(event, session, exc.problems)

    if event == "post_agent":
        verdict = session.finish()
        if verdict.action != "block":
            _set(session, _TURN_ENDED, True)
            return None
        return {"decision": "deny", "reason": verdict.reason,
                "system_message": f"AgentLTL sent Vibe back: {_first_line(verdict.reason)}"}

    tool, tool_input = _call(payload)
    if event == "pre_tool":
        return _pre(session, tool, tool_input)
    if event == "post_tool":
        return _post(session, payload, tool, tool_input)
    return None


def _pre(session: Any, tool: str, tool_input: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    auto = os.environ.get("AGENTLTL_AUTO") == "1"
    verdict = session.pre(tool, tool_input, auto=auto)
    if verdict.action == "ask" and not auto and _approved(session, tool, tool_input):
        return None
    if verdict.action in ("deny", "stop", "ask"):
        reason = verdict.reason
        if verdict.action == "ask":
            reason = _ask_reason(verdict.reason) if not auto else (
                verdict.reason.rsplit("\n", 1)[0]
                + "\nNobody can approve it in an unattended run: the call is refused.")
            if not auto:
                _ask(session, tool, tool_input)
        elif verdict.context:
            reason = reason + "\n" + verdict.context
        rule = f"rule '{verdict.rule}'" if verdict.rule else "a rule"
        return {"decision": "deny", "reason": reason,
                "system_message": f"AgentLTL: {rule} refused {_show(tool, tool_input)}"}
    if verdict.context:
        _keep_note(session, tool, tool_input, verdict.context)
    return None


def _post(session: Any, payload: Dict[str, Any], tool: str,
          tool_input: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    status_name = payload.get("tool_status", "success")
    notes, shown = [], []
    if status_name != "cancelled":                # a cancelled call never ran
        status = 0 if status_name == "success" and not _exit_code(payload) else 1
        output = payload.get("tool_output_text") or payload.get("tool_error")
        found = session.post(tool, tool_input, payload.get("tool_call_id") or "", output,
                             status=status)
        if tool == ASK_TOOL and status == 0:
            _answered(session)
        notes += [n for n in (_take_note(session, tool, tool_input), found and found[1]) if n]
        if found:
            shown.append(found[0])
        if tool in ("agent_spawn", "task") and status == 0:
            shown.append("AgentLTL: a subagent started; Vibe runs no hooks inside it, so its "
                         "calls are not checked")
    # A call run from inside run_typescript gets no added text to its result: keep the rules
    # for a call whose result Vibe does see.
    nested = str(payload.get("tool_call_id") or "").startswith("typescript:")
    if not nested and _first(session, _TOLD):
        text = session.start()
        if text:
            notes.insert(0, text)
            shown.insert(0, f"AgentLTL: {len(session.ruleset.rules)} rule(s) in force")
    if not notes and not shown:
        return None
    out: Dict[str, Any] = {}
    if notes:
        out["hook_specific_output"] = {"additional_context": "\n\n".join(notes)}
    if shown:
        out["system_message"] = " · ".join(shown)
    return out


# ── the payload ───────────────────────────────────────────────────────────────

def _call(payload: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    """The tool, under the name the model uses for it, and its arguments."""
    args = payload.get("tool_input")
    return tool_name(payload.get("tool_name") or ""), args if isinstance(args, dict) else {}


def _exit_code(payload: Dict[str, Any]) -> int:
    """A shell command's exit code, when the tool reports one alongside "success"."""
    out = payload.get("tool_output")
    if isinstance(out, dict):
        for key in ("returncode", "exit_code", "return_code"):
            if isinstance(out.get(key), int):
                return out[key]
    return 0


def _show(tool: str, tool_input: Dict[str, Any]) -> str:
    what = tool_input.get("command") or tool_input.get("file_path") or ""
    what = " ".join(str(what).split())
    return f"{tool} {what[:80] + ('…' if len(what) > 80 else '')}".strip()


def _first_line(text: str) -> str:
    return next((line for line in text.splitlines() if line.strip()), "")[:160]


# ── state kept across hook calls ──────────────────────────────────────────────

def _get(session: Any, key: str) -> Any:
    from agentltl_coding import store
    with store.locked(session.sid) as state:
        return state.get(key)


def _set(session: Any, key: str, value: Any) -> None:
    from agentltl_coding import store
    with store.locked(session.sid) as state:
        state[key] = value


def _first(session: Any, key: str) -> bool:
    """True the first time it is called for *key* in this session (parallel hooks included)."""
    from agentltl_coding import store
    with store.locked(session.sid) as state:
        first = not state.get(key)
        state[key] = True
    return first


def _maybe_new_turn(session: Any) -> None:
    """The last turn ended: this call follows a message from the user."""
    from agentltl_coding import store
    with store.locked(session.sid) as state:
        ended = state.pop(_TURN_ENDED, None)
        asks = state.get(_ASKS) or {}
        if ended:
            state[_ASKS] = {k: "answered" for k in asks}
    if ended:
        session.prompt()


def _key(tool: str, tool_input: Dict[str, Any]) -> str:
    raw = json.dumps([tool, tool_input], sort_keys=True, default=str)
    return hashlib.sha1(raw.encode()).hexdigest()[:16]


def _ask(session: Any, tool: str, tool_input: Dict[str, Any]) -> None:
    from agentltl_coding import store
    with store.locked(session.sid) as state:
        asks = state.setdefault(_ASKS, {})
        asks[_key(tool, tool_input)] = "asked"
        while len(asks) > 20:
            asks.pop(next(iter(asks)))


def _answered(session: Any) -> None:
    from agentltl_coding import store
    with store.locked(session.sid) as state:
        state[_ASKS] = {k: "answered" for k in state.get(_ASKS) or {}}


def _approved(session: Any, tool: str, tool_input: Dict[str, Any]) -> bool:
    """Whether this exact call was refused for an `ask` rule and the user has been asked since
    (once: the approval is used up)."""
    from agentltl_coding import store
    key = _key(tool, tool_input)
    with store.locked(session.sid) as state:
        asks = state.get(_ASKS) or {}
        if asks.get(key) != "answered":
            return False
        del asks[key]
        # The guard logged this call as an "ask" for `agentltl trace`: it went ahead, approved.
        for d in reversed(state.get("decisions") or []):
            if d.get("action") == "ask":
                d["action"] = "ok"
                break
        return True


def _ask_reason(prompt: str) -> str:
    """The guard's permission prompt, turned into instructions for Vibe."""
    lines = [line for line in prompt.splitlines() if not line.endswith("Allow this call anyway?")]
    return "\n".join(lines + [_ASK_TAIL])


def _keep_note(session: Any, tool: str, tool_input: Dict[str, Any], text: str) -> None:
    from agentltl_coding import store
    with store.locked(session.sid) as state:
        notes = state.setdefault(_NOTES, {})
        notes[_key(tool, tool_input)] = text
        while len(notes) > 50:
            notes.pop(next(iter(notes)))


def _take_note(session: Any, tool: str, tool_input: Dict[str, Any]) -> Optional[str]:
    from agentltl_coding import store
    with store.locked(session.sid) as state:
        return (state.get(_NOTES) or {}).pop(_key(tool, tool_input), None)


# ── trouble ───────────────────────────────────────────────────────────────────

def _broken_file(event: str, session: Any, problems: list) -> Optional[Dict[str, Any]]:
    """Tell Vibe and the user once per session; calls go ahead (no rules to check)."""
    from agentltl_coding.session import broken
    if event != "post_tool" or not _first(session, _TOLD):
        return None
    return {"hook_specific_output": {"additional_context": broken(problems) + "\nTell the user."},
            "system_message": "AgentLTL: AGENTLTL.yaml has errors; no rules are enforced"}


def _failure(event: str, exc: Exception) -> Optional[Dict[str, Any]]:
    text = f"AgentLTL guard error ({type(exc).__name__}: {exc})"
    if event == "pre_tool":
        return {"decision": "deny",
                "reason": text + "; this call was refused because it could not be checked "
                                 "against the rules. Tell the user.",
                "system_message": text}
    if event == "post_tool":
        return {"hook_specific_output": {"additional_context": text + ". Tell the user."},
                "system_message": text}
    return None


if __name__ == "__main__":
    sys.exit(main())
