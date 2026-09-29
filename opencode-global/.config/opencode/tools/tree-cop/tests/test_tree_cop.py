"""Тесты tree-cop: парсинг porcelain, атрибуция mine/foreign, вердикт.

Офлайн, без сети и без реального git-репозитория: git подменяется
заглушкой (monkeypatch run_git). Пути/логика разделения — главное,
что ломается при параллельных сессиях.
"""
import importlib.util
import sys
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "tree_cop", Path(__file__).resolve().parents[1] / "tree-cop.py"
)
tc = importlib.util.module_from_spec(SPEC)
sys.modules["tree_cop"] = tc
SPEC.loader.exec_module(tc)


def _fake_git(status_text="", skip_text="", mode_text="", revlist="0\t0"):
    def fake(*args):
        a = args[0] if args else ""
        if a == "status":
            return 0, status_text
        if a == "ls-files":
            return 0, skip_text
        if a == "diff":
            return 0, mode_text
        if a == "rev-list":
            return 0, revlist
        if a == "branch":
            return 0, "task/demo"
        if a == "fetch":
            return 0, ""
        return 0, ""
    return fake


# --- парсинг porcelain ------------------------------------------------------

def test_parses_unstaged_modification():
    """' M path' — пробел во втором столбце, путь с точкой впереди."""
    tracked, untracked = tc.parse_status() if False else (None, None)  # noqa: F841
    fake = _fake_git(status_text=" M .opencode/agent/librarian.md")
    tc.run_git = fake
    tracked, untracked = tc.parse_status()
    assert tracked == [".opencode/agent/librarian.md"]
    assert untracked == []


def test_parses_staged_modification():
    """'M  path' — символ во втором столбце, путь с третьего."""
    tc.run_git = _fake_git(status_text="M  tools/x.py")
    tracked, untracked = tc.parse_status()
    assert tracked == ["tools/x.py"]
    assert untracked == []


def test_parses_untracked_dirs_expanded():
    tc.run_git = _fake_git(status_text="?? tools/mem-index/index.py")
    tracked, untracked = tc.parse_status()
    assert untracked == ["tools/mem-index/index.py"]
    assert tracked == []


def test_rename_uses_new_path():
    tc.run_git = _fake_git(status_text="R  old.md -> new.md")
    tracked, _ = tc.parse_status()
    assert tracked == ["new.md"]


# --- атрибуция mine/foreign -------------------------------------------------

def test_classify_splits_mine_and_foreign():
    tracked = ["tools/mine.py", "tools/foreign.py"]
    untracked = ["tools/mine-doc.md", "02-Methods/other.md"]
    mine, foreign = tc.classify(tracked, untracked, ["tools/mine.py", "tools/mine-doc.md"])
    assert mine == ["tools/mine-doc.md", "tools/mine.py"]
    assert foreign == ["02-Methods/other.md", "tools/foreign.py"]


def test_classify_prefix_match_for_directories():
    tracked, untracked = [], ["tools/tree-cop/tree-cop.py", "tools/tree-cop/README.md"]
    mine, foreign = tc.classify(tracked, untracked, ["tools/tree-cop"])
    assert mine == ["tools/tree-cop/README.md", "tools/tree-cop/tree-cop.py"]
    assert foreign == []


def test_classify_normalizes_trailing_slash():
    mine, _ = tc.classify([], ["a/b/c.py"], ["a/b/"])
    assert mine == ["a/b/c.py"]


# --- невидимая грязь ---------------------------------------------------------

def test_skip_worktree_files_detected():
    tc.run_git = _fake_git(skip_text="S tools/hot.md\nH tools/other.md\n")
    assert tc.skip_worktree_files() == ["tools/hot.md"]


def test_mode_changes_detected():
    tc.run_git = _fake_git(mode_text=" mode change 100644 => 100755 tools/x.sh")
    assert tc.mode_changes() == ["tools/x.sh"]


# --- вердикт -----------------------------------------------------------------

def test_verdict_stop_on_foreign(capsys):
    tc.run_git = _fake_git(status_text="?? someone-elses.md")
    code = tc.cmd_status(type("A", (), {"mine": []})())
    payload = tc.json.loads(capsys.readouterr().out)
    assert code == 1
    assert payload["verdict"] == "STOP"
    assert "someone-elses.md" in payload["reasons"][0]


def test_verdict_go_when_only_mine(capsys):
    tc.run_git = _fake_git(status_text="?? tools/mine.py")
    code = tc.cmd_status(type("A", (), {"mine": ["tools/mine.py"]})())
    payload = tc.json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["verdict"] == "GO"
    assert payload["mine"] == ["tools/mine.py"]


def test_verdict_stop_when_origin_main_ahead(capsys):
    # rev-list --left-right: слева behind, справа ahead.
    tc.run_git = _fake_git(revlist="2\t0")
    code = tc.cmd_status(type("A", (), {"mine": []})())
    payload = tc.json.loads(capsys.readouterr().out)
    assert code == 1
    assert payload["origin_main"]["behind"] == 2
    assert payload["origin_main"]["ahead"] == 0
    assert any("origin/main" in r for r in payload["reasons"])


def test_own_ahead_is_not_behind(capsys):
    """Свой аванс — не отставание: GO, иначе коп вечно блокирует выкладку."""
    tc.run_git = _fake_git(revlist="0\t2")
    code = tc.cmd_status(type("A", (), {"mine": []})())
    payload = tc.json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["verdict"] == "GO"
    assert payload["origin_main"] == {"ahead": 2, "behind": 0}
    assert payload["reasons"] == []


def test_stash_foreign_paths_only(monkeypatch):
    calls = []

    def fake_run_git(*args):
        calls.append(args)
        if args[0] == "status":
            return 0, " M tools/mine.py\n?? foreign.md"
        return 0, ""
    monkeypatch.setattr(tc, "run_git", fake_run_git)
    code = tc.cmd_stash_foreign(type(
        "A", (), {"mine": ["tools/mine.py"], "message": "cop"})())
    assert code == 0
    stash = [c for c in calls if c[0] == "stash"]
    assert stash, "stash не вызван"
    assert "foreign.md" in stash[0]
    assert "tools/mine.py" not in stash[0], "своё не должно попадать в stash"


def test_stash_foreign_noop_when_clean(capsys):
    tc.run_git = _fake_git(status_text="")
    code = tc.cmd_stash_foreign(type(
        "A", (), {"mine": [], "message": "cop"})())
    payload = tc.json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["stashed"] == []
