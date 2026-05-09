import json

from ai.agent.action_log import latest_recommendations, read_actions


def _write_jsonl(path, entries):
    with open(path, "w", encoding="utf-8") as f:
        for entry in entries:
            f.write(json.dumps(entry) + "\n")


def test_read_actions_filters_by_status_and_container(tmp_path):
    path = tmp_path / "actions.jsonl"
    _write_jsonl(path, [
        {"id": "1", "container": "api", "status": "recommended"},
        {"id": "2", "container": "worker", "status": "failed"},
        {"id": "3", "container": "api", "status": "applied"},
    ])

    actions = read_actions(
        status="applied",
        container_name="api",
        path=str(path),
    )

    assert [action["id"] for action in actions] == ["3"]


def test_latest_recommendations_returns_latest_entry_per_container(tmp_path):
    path = tmp_path / "actions.jsonl"
    _write_jsonl(path, [
        {
            "id": "old",
            "container": "api",
            "status": "recommended",
            "recommended_limits": {"cpu_quota": 0.3},
        },
        {
            "id": "latest-worker",
            "container": "worker",
            "status": "applied",
            "recommended_limits": {"cpu_quota": 0.5},
        },
        {
            "id": "ignored",
            "container": "api",
            "status": "failed",
            "recommended_limits": {"cpu_quota": 0.1},
        },
        {
            "id": "latest-api",
            "container": "api",
            "status": "applied",
            "recommended_limits": {"cpu_quota": 0.8},
        },
    ])

    recommendations = latest_recommendations(path=str(path))

    assert {entry["container"]: entry["id"] for entry in recommendations} == {
        "api": "latest-api",
        "worker": "latest-worker",
    }
