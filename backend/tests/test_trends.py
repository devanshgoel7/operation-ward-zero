from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.models.monitoring import Reading
from app.services.trends import evaluate_trends
from conftest import frame

END = datetime(2026, 1, 1, tzinfo=UTC)


def history(offsets=range(5, 121, 5), oxygen_change=-3, hr_change=20):
    return [Reading.model_validate(frame(i+1) | {
        "observed_at": END-timedelta(seconds=120-offset),
        "spo2_pct": 99+(oxygen_change if offset > 60 else 0),
        "heart_rate_bpm": 70+(hr_change if offset > 60 else 0),
    }) for i, offset in enumerate(offsets)]


def test_both_exact_thresholds_and_traceable_windows():
    readings = history()
    # Both outer boundaries are deliberate: start excluded, midpoint earlier, end included.
    excluded = readings[0].model_copy(update={"reading_id": uuid4(), "observed_at": END-timedelta(seconds=120), "spo2_pct": 1})
    future = readings[0].model_copy(update={"reading_id": uuid4(), "observed_at": END+timedelta(microseconds=1)})
    summaries, findings = evaluate_trends([excluded, future, *reversed(readings)], END)
    assert [f.rule_id for f in findings] == ["spo2_pct.trend.watch", "heart_rate_bpm.trend.watch"]
    assert [s.change for s in summaries] == [-3, 20]
    assert all((s.earlier_count, s.recent_count, s.max_gap_seconds) == (12, 12, 5) for s in summaries)
    assert all({e.reading_id for e in s.evidence} == {r.reading_id for r in readings} for s in summaries)


def test_medians_resist_one_outlier_and_subthreshold_changes():
    readings = history(oxygen_change=-2.9, hr_change=19.9)
    readings[-1] = readings[-1].model_copy(update={"spo2_pct": 1, "heart_rate_bpm": 200})
    summaries, findings = evaluate_trends(readings, END)
    assert not findings
    assert summaries[0].change == pytest.approx(-2.9)
    assert summaries[1].change == pytest.approx(19.9)


@pytest.mark.parametrize("offsets,status", [
    ([10,20,30,35,40,45,50,60,70,80,90,95,100,105,110,120], "calculated"),
    ([10,20,30,40,45,50,60,70,80,90,95,100,105,110,120], "insufficient_samples"),
    ([5,10,15,20,25,30,35,40,60,65,70,75,80,85,90,95,100,105,110,115,120], "gap"),
    (list(range(11, 121, 5)), "gap"),
    (list(range(5, 110, 5)), "gap"),
    ([], "insufficient_samples"),
])
def test_sample_and_continuity_eligibility(offsets, status):
    summaries, findings = evaluate_trends(history(offsets), END)
    assert all(s.status == status for s in summaries)
    if status != "calculated":
        assert not findings and all(s.change is None for s in summaries)


def test_metric_nulls_and_non_current_evidence():
    readings = history()
    for i in range(5):
        readings[i] = readings[i].model_copy(update={"spo2_pct": None})
    summaries, findings = evaluate_trends(readings, END)
    assert [s.status for s in summaries] == ["insufficient_samples", "calculated"]
    assert [f.metric for f in findings] == ["heart_rate_bpm"]
    summaries, findings = evaluate_trends(readings, END, current=False)
    assert not findings and all(s.status == "not_current" for s in summaries)
