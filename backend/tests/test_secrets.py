"""Secrets from the user's Claude Code history must never reach the dashboard, the prompt or his voice."""

import json
from datetime import datetime
from pathlib import Path

import pytest

from bonnington.dashboard import build_dashboard
from bonnington.vault.projects import ProjectDetail, ProjectStatus, _clean_request, _parse_session
from bonnington.vault.store import Vault
from bonnington.vault.tools import Tracker

NOW = datetime(2026, 11, 15, 23, 40)


@pytest.mark.parametrize("text", [
    "use AKIAIOSFODNN7EXAMPLE for the s3 bucket",
    "connect with postgres://admin:S3cr3tPass99@db.local/app",
    "my login is admin and pw is Hunter2024!",
    "set OPENAI=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
    "export ANTHROPIC_API=sk-ant-api03-abcdefghijklmnopqrstuv",
    "the slack bot is xoxb-123456789012-abcdefghijkl",
    "maps key AIzaSyA1234567890abcdefghijklmnopqrstu",
    "header eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.abc",
    "-----BEGIN OPENSSH PRIVATE KEY----- b3BlbnNzaC1rZXktdjE",
    "db pass: qwerty",
    "the github pat is ghp_abcdefghijklmnopqrstuvwxyz0123456789",
])
def test_secret_shapes_are_hidden(text):
    assert "hidden" in _clean_request(text)


@pytest.mark.parametrize("text", [
    "why does the build fail on windows",
    "add a dark mode toggle to the settings page",
    "move src/app/page.tsx into src/routes",
    "make the tests pass",
])
def test_ordinary_requests_are_shown(text):
    assert _clean_request(text) == text


def test_session_titles_and_branches_are_scrubbed_too(tmp_path):
    p = tmp_path / "s.jsonl"
    rows = [{"type": "user", "cwd": "C:/x", "gitBranch": "fix/AKIAIOSFODNN7EXAMPLE"},
            {"type": "custom-title", "customTitle": "rotate sk-ant-api03-abcdefghijklmnopqrstuv now"}]
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    _cwd, title, branch, _prompts = _parse_session(p)
    assert "sk-ant" not in title and "hidden" in title
    assert "AKIA" not in branch


def test_ordinary_titles_and_branches_are_kept(tmp_path):
    p = tmp_path / "s.jsonl"
    rows = [{"type": "user", "cwd": "C:/x", "gitBranch": "feat/map"},
            {"type": "custom-title", "customTitle": "Campus map"}]
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    _cwd, title, branch, _prompts = _parse_session(p)
    assert (title, branch) == ("Campus map", "feat/map")


def test_the_dashboard_never_shows_what_was_typed(tmp_path):
    projects = [ProjectStatus("das_v0", Path("a"), NOW, 0, "active", "Personal", "Init", "main")]
    detail = lambda name: ProjectDetail(name, [("Init", 0)], ["here is my db url, use it"])
    tracker = Tracker(Vault(tmp_path / "v"), projects=lambda: projects, now=lambda: NOW, detail=detail)
    rows = build_dashboard(tracker)["focus"]["rows"]
    assert not any("db url" in cell for row in rows for cell in row)
