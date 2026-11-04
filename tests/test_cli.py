import json
from pathlib import Path

import pytest

from agent_contract.cli import main

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"
BASELINE = str(EXAMPLES / "traces-baseline.jsonl")
CANDIDATE = str(EXAMPLES / "traces-candidate.jsonl")


def test_mine_then_run_fails_on_red(tmp_path, capsys):
    out = tmp_path / "contract.json"
    assert main(["mine", "--traces", BASELINE, "-o", str(out), "-q"]) == 0
    assert out.exists()
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["version"] == 1
    assert data["source"]["traces"]["traces"] == 40
    assert data["assertions"]

    code = main(["run", "--contract", str(out), "--target", CANDIDATE, "--no-color"])
    printed = capsys.readouterr().out
    assert code == 1
    assert "FAIL" in printed
    assert "RED" in printed
    assert "drift.facts_preserved" in printed


def test_run_fail_on_never(tmp_path):
    out = tmp_path / "c.json"
    main(["mine", "--traces", BASELINE, "-o", str(out), "-q"])
    assert main(["run", "--contract", str(out), "--target", CANDIDATE,
                 "--fail-on", "never", "-q"]) == 0


def test_run_json_output_is_parseable(tmp_path, capsys):
    out = tmp_path / "c.json"
    main(["mine", "--traces", BASELINE, "-o", str(out), "-q"])
    code = main(["run", "--contract", str(out), "--target", CANDIDATE, "--format", "json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 1
    assert payload["counts"]["red"] >= 1
    assert payload["worst"] == "red"
    assert isinstance(payload["findings"], list)


def test_run_markdown_output(tmp_path, capsys):
    out = tmp_path / "c.json"
    main(["mine", "--traces", BASELINE, "-o", str(out), "-q"])
    main(["run", "--contract", str(out), "--target", CANDIDATE, "--format", "markdown"])
    text = capsys.readouterr().out
    assert text.startswith("## agent-contract report")
    assert "| red | amber | green |" in text
    assert "❌ FAIL" in text


def test_run_writes_report_file(tmp_path):
    out = tmp_path / "c.json"
    report = tmp_path / "report.md"
    main(["mine", "--traces", BASELINE, "-o", str(out), "-q"])
    main(["run", "--contract", str(out), "--target", CANDIDATE, "--format", "markdown",
          "--output", str(report)])
    assert report.exists()
    assert "agent-contract report" in report.read_text(encoding="utf-8")


def test_mine_to_stdout(tmp_path, capsys):
    code = main(["mine", "--traces", BASELINE, "-o", "-", "--format", "json"])
    out = capsys.readouterr().out
    assert code == 0
    payload = json.loads(out[out.index("{"):])
    assert payload["assertions"]


def test_mine_yaml_roundtrip(tmp_path):
    pytest.importorskip("yaml")
    out = tmp_path / "contract.yaml"
    assert main(["mine", "--traces", BASELINE, "-o", str(out), "-q"]) == 0
    assert "assertions:" in out.read_text(encoding="utf-8")
    assert main(["run", "--contract", str(out), "--target", CANDIDATE,
                 "--fail-on", "never", "-q"]) == 0


def test_missing_trace_path_exits_2(capsys):
    code = main(["mine", "--traces", "nope/none.jsonl", "-o", "-"])
    assert code == 2
    assert "no such file" in capsys.readouterr().err


def test_missing_contract_exits_2(capsys):
    code = main(["run", "--contract", "nope.json", "--target", BASELINE])
    assert code == 2
    assert "cannot read contract" in capsys.readouterr().err


def test_empty_trace_file_exits_2(tmp_path, capsys):
    empty = tmp_path / "empty.jsonl"
    empty.write_text("", encoding="utf-8")
    code = main(["mine", "--traces", str(empty), "-o", "-"])
    assert code == 2
    assert "no traces" in capsys.readouterr().err


def test_mine_no_drift_and_no_action(tmp_path, capsys):
    code = main(["mine", "--traces", BASELINE, "-o", "-", "--no-drift", "--no-action",
                 "--format", "json"])
    out = capsys.readouterr().out
    payload = json.loads(out[out.index("{"):])
    kinds = {a["kind"] for a in payload["assertions"]}
    assert code == 0
    assert all(k.startswith("shape.") or k.startswith("action.max_calls") for k in kinds)
    assert not any(k.startswith("drift.") for k in kinds)


def test_version_flag(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert "agent-contract" in capsys.readouterr().out


def test_no_command_exits():
    with pytest.raises(SystemExit):
        main([])