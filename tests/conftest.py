import pytest

import agentltl_vibe  # noqa: F401  (configures the Mistral Vibe harness)


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    """No user-level rule file, and session state under tmp."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.delenv("VIBE_HOME", raising=False)
    monkeypatch.delenv("VIBE_PROJECT_DIR", raising=False)
    monkeypatch.setenv("AGENTLTL_STATE", str(tmp_path / "state"))
    monkeypatch.delenv("AGENTLTL_AUTO", raising=False)
