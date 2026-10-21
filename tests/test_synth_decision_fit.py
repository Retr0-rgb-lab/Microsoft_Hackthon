"""The v1 weight fit reads synthetic decision_point events and nothing else."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from inside_the_game.features.from_tracking import decision_point_rows, load_synth_match
from inside_the_game.labels import ACTION_LABELS
from inside_the_game.system1.fit import fit_softmax


ROOT = Path(__file__).resolve().parents[1]
WEIGHTS = ROOT / "src" / "inside_the_game" / "system1" / "weights.json"
SAMPLE_COUNTS = {"pass": 73, "shoot": 2, "dribble": 41, "hold": 8}


@pytest.fixture(scope="module")
def train_main():
    sys.path.insert(0, str(ROOT / "scripts"))
    import train_softmax

    return train_softmax.main


def test_training_rows_are_only_decision_points() -> None:
    match = load_synth_match()
    assert match.metadata["synthetic"] is True
    assert match.metadata["fictional_entities"] is True
    assert match.match_id == "SYN-SINGLE-0001"
    rows = decision_point_rows(match)
    decisions = [event for event in match.events if event["type"] == "decision_point"]
    assert len(rows) == len(decisions) == 124
    labels = [label for _features, label in rows]
    assert set(labels) == set(ACTION_LABELS)
    assert {label: labels.count(label) for label in ACTION_LABELS} == SAMPLE_COUNTS
    other = [event["type"] for event in match.events if event["type"] != "decision_point"]
    assert "pass" in other and "shot" in other


def test_fit_script_opens_only_the_synthetic_sample(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, train_main) -> None:
    opened: list[str] = []
    real_read_text = Path.read_text

    def spy_read_text(self: Path, *args, **kwargs):
        opened.append(str(self))
        return real_read_text(self, *args, **kwargs)

    def refuse_statsbomb(*_args, **_kwargs):
        raise AssertionError("the v1 fit tried to load a StatsBomb match")

    monkeypatch.setattr(Path, "read_text", spy_read_text)
    monkeypatch.setattr(
        "inside_the_game.ingest.statsbomb.load_statsbomb_labeled",
        refuse_statsbomb,
    )
    destination = tmp_path / "weights.json"
    train_main(["--output", str(destination), "--steps", "40"])

    assert destination.is_file()
    assert any(path.endswith("sample_25hz_10min/events.jsonl") for path in opened)
    assert any(path.endswith("sample_25hz_10min/tracking.jsonl") for path in opened)
    assert not any("statsbomb" in path.lower() for path in opened)
    document = json.loads(destination.read_text(encoding="utf-8"))
    blob = json.dumps(document).lower()
    assert "statsbomb" not in blob
    assert "69284" not in blob
    assert document["fit_on"] == "synthdata:SYN-SINGLE-0001:decision_point"
    assert document["event_types"] == ["decision_point"]
    assert document["training"]["counts"] == SAMPLE_COUNTS
    assert set(document["labels"]) == set(ACTION_LABELS)


def test_checked_in_weights_match_the_synthetic_refit() -> None:
    document = json.loads(WEIGHTS.read_text(encoding="utf-8"))
    assert document["fit_on"] == "synthdata:SYN-SINGLE-0001:decision_point"
    assert "statsbomb" not in json.dumps(document).lower()
    fitted = fit_softmax(decision_point_rows(load_synth_match()))
    fresh = fitted.as_dict()
    assert fresh["bias"] == document["bias"]
    assert fresh["weights"] == document["weights"]
    assert fresh["training"]["counts"] == document["training"]["counts"] == SAMPLE_COUNTS


def test_non_synthetic_match_is_refused(tmp_path: Path) -> None:
    sample = load_synth_match().root
    target = tmp_path / "match"
    target.mkdir()
    for name in ("metadata.json", "events.jsonl", "tracking.jsonl"):
        (target / name).write_text((sample / name).read_text(encoding="utf-8"), encoding="utf-8")
    metadata = json.loads((target / "metadata.json").read_text(encoding="utf-8"))
    metadata["synthetic"] = False
    (target / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
    with pytest.raises(ValueError, match="synthetic"):
        load_synth_match(target)
