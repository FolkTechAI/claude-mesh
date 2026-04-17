# tests/unit/test_mode.py
from claude_mesh.mode import Mode, detect_mode


def test_detect_team_mode_from_team_name():
    payload = {"hook_event_name": "TeammateIdle", "teammate_name": "alpha", "team_name": "spike"}
    assert detect_mode(payload) == Mode.TEAM


def test_detect_standalone_without_team_name():
    payload = {"hook_event_name": "TaskCreated", "task_id": "1"}
    assert detect_mode(payload) == Mode.STANDALONE


def test_detect_team_from_team_name_alone():
    payload = {"hook_event_name": "TaskCreated", "team_name": "spike", "task_id": "1"}
    assert detect_mode(payload) == Mode.TEAM
