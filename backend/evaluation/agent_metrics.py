from __future__ import annotations

from collections.abc import Sequence
from statistics import fmean


def accuracy(actual: Sequence[str], expected: Sequence[str]) -> float:
    """Overall accuracy of a categorical decision sequence."""
    if not actual:
        return 0.0
    hits = sum(1 for a, e in zip(actual, expected) if a == e)
    return hits / len(actual)


def classification_metrics(
    labels: Sequence[str],
    actual: Sequence[str],
    expected: Sequence[str],
) -> dict[str, object]:
    """Per-class precision/recall/F1 plus macro averages and accuracy.

    Suitable for supervisor routing / action-decision evaluations. Rows are
    grouped by expected class so the confusion matrix reads
    matrix[expected][actual]; the diagonal is the correctly classified count.
    """
    tp = {label: 0 for label in labels}
    fp = {label: 0 for label in labels}
    fn = {label: 0 for label in labels}
    matrix = {label: {other: 0 for other in labels} for label in labels}

    for a, e in zip(actual, expected):
        if a == e:
            tp[a] += 1
        else:
            fp[a] += 1
            fn[e] += 1
        matrix[e][a] += 1

    per_class: dict[str, dict[str, float]] = {}
    for label in labels:
        precision = tp[label] / (tp[label] + fp[label]) if (tp[label] + fp[label]) else 0.0
        recall = tp[label] / (tp[label] + fn[label]) if (tp[label] + fn[label]) else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
        per_class[label] = {"precision": precision, "recall": recall, "f1": f1}

    def macro(metric: str) -> float:
        return fmean([per_class[label][metric] for label in labels]) if labels else 0.0

    return {
        "accuracy": accuracy(actual, expected),
        "macro_precision": macro("precision"),
        "macro_recall": macro("recall"),
        "macro_f1": macro("f1"),
        "per_class": per_class,
        "confusion_matrix": matrix,
    }


def guard_metrics(
    expected_blocked: Sequence[bool],
    actual_blocked: Sequence[bool],
) -> dict[str, float]:
    """Binary guard performance: interception = positive class.

    - fpr (误报率): legitimate input that was wrongly blocked.
    - fnr (漏报率): attack input that slipped through as allowed.
    - interception_rate (拦截成功率): fraction of attacks that were stopped.
    """
    if not expected_blocked:
        return {"accuracy": 0.0, "fpr": 0.0, "fnr": 0.0, "interception_rate": 0.0, "case_count": 0.0}
    tp = sum(1 for e, a in zip(expected_blocked, actual_blocked) if e and a)
    fp = sum(1 for e, a in zip(expected_blocked, actual_blocked) if not e and a)
    fn = sum(1 for e, a in zip(expected_blocked, actual_blocked) if e and not a)
    tn = sum(1 for e, a in zip(expected_blocked, actual_blocked) if not e and not a)
    total = tp + fp + fn + tn
    return {
        "accuracy": (tp + tn) / total if total else 0.0,
        "fpr": fp / (fp + tn) if (fp + tn) else 0.0,
        "fnr": fn / (fn + tp) if (fn + tp) else 0.0,
        "interception_rate": tp / (tp + fn) if (tp + fn) else 0.0,
        "case_count": float(total),
    }


__all__ = ["accuracy", "classification_metrics", "guard_metrics"]
