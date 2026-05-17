import json

from ai.agent.finetune_log import read_finetune_runs, record_finetune_run


def test_record_finetune_run_appends_timestamped_entry(tmp_path):
    path = tmp_path / "finetune_runs.jsonl"

    entry = record_finetune_run(
        {"status": "skipped", "reason": "insufficient samples"},
        path=str(path),
    )

    assert entry["status"] == "skipped"
    assert "timestamp" in entry

    written = json.loads(path.read_text(encoding="utf-8").strip())
    assert written == entry


def test_read_finetune_runs_returns_newest_first_and_skips_bad_lines(tmp_path):
    path = tmp_path / "finetune_runs.jsonl"
    path.write_text(
        "\n".join([
            json.dumps({"status": "old"}),
            "not-json",
            json.dumps({"status": "new"}),
        ]),
        encoding="utf-8",
    )

    runs = read_finetune_runs(limit=1, path=str(path))

    assert runs == [{"status": "new"}]
