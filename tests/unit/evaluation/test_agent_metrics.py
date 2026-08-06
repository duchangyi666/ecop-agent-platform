from __future__ import annotations

from backend.evaluation.agent_metrics import accuracy, classification_metrics, guard_metrics


def test_accuracy_basic() -> None:
    assert accuracy(["a", "b", "c"], ["a", "b", "c"]) == 1.0
    assert accuracy(["a", "b", "c"], ["a", "x", "c"]) == 2 / 3
    assert accuracy([], []) == 0.0


def test_classification_metrics_macro_average() -> None:
    labels = ["a", "b"]
    actual = ["a", "a", "b", "b"]
    expected = ["a", "b", "b", "b"]

    result = classification_metrics(labels, actual, expected)
    assert result["accuracy"] == 3 / 4
    # class a: tp=1, fp=1, fn=0 -> precision=0.5, recall=1.0, f1=0.667
    # class b: tp=2, fp=0, fn=1 -> precision=1.0, recall=2/3, f1=0.8
    per_class = result["per_class"]
    assert per_class["a"]["precision"] == 0.5
    assert per_class["a"]["recall"] == 1.0
    assert abs(per_class["a"]["f1"] - 2 / 3) < 1e-9
    assert per_class["b"]["precision"] == 1.0
    assert per_class["b"]["recall"] == 2 / 3
    assert per_class["b"]["f1"] == 0.8
    assert abs(result["macro_f1"] - (2 / 3 + 0.8) / 2) < 1e-9
    assert result["confusion_matrix"]["a"]["a"] == 1
    assert result["confusion_matrix"]["b"]["a"] == 1


def test_classification_metrics_empty_labels() -> None:
    result = classification_metrics([], [], [])
    assert result["accuracy"] == 0.0
    assert result["macro_f1"] == 0.0


def test_guard_metrics_perfect() -> None:
    metrics = guard_metrics([True, True, False], [True, True, False])
    assert metrics["accuracy"] == 1.0
    assert metrics["fpr"] == 0.0
    assert metrics["fnr"] == 0.0
    assert metrics["interception_rate"] == 1.0


def test_guard_metrics_with_leak_and_false_alarm() -> None:
    # expected_blocked=[T,T,F], actual_blocked=[T,F,T]
    metrics = guard_metrics([True, True, False], [True, False, True])
    # tp=1, fp=1, fn=1, tn=0
    assert metrics["accuracy"] == 1 / 3
    assert metrics["fpr"] == 1.0
    assert metrics["fnr"] == 0.5
    assert metrics["interception_rate"] == 0.5


def test_guard_metrics_empty() -> None:
    metrics = guard_metrics([], [])
    assert metrics["case_count"] == 0.0
