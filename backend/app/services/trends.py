"""Descriptive demo trends; no retrospective or predictive assessment."""
from datetime import datetime, timedelta
from statistics import median

from app.models.alerts import Finding, ReadingEvidence, TrendSummary
from app.models.monitoring import Reading

TREND_RULES = (("spo2_pct", "percentage points", -3), ("heart_rate_bpm", "bpm", 20))


def evaluate_trends(readings: list[Reading], end: datetime, current: bool = True
                    ) -> tuple[list[TrendSummary], list[Finding]]:
    start, midpoint = end - timedelta(seconds=120), end - timedelta(seconds=60)
    summaries, findings = [], []
    for metric, unit, threshold in TREND_RULES:
        evidence = [ReadingEvidence(reading_id=r.reading_id, observed_at=r.observed_at,
                                    value=getattr(r, metric))
                    for r in sorted(readings, key=lambda r: (r.observed_at, r.reading_id))
                    if start < r.observed_at <= end and getattr(r, metric) is not None]
        earlier = [e.value for e in evidence if e.observed_at <= midpoint]
        recent = [e.value for e in evidence if e.observed_at > midpoint]
        times = [start, *(e.observed_at for e in evidence), end]
        gap = max((b-a).total_seconds() for a, b in zip(times, times[1:]))
        status = ("not_current" if not current else "insufficient_samples" if min(len(earlier), len(recent)) < 8
                  else "gap" if gap > 10 else "calculated")
        summary = TrendSummary(metric=metric, unit=unit, start=start, midpoint=midpoint, end=end,
                               status=status, earlier_count=len(earlier), recent_count=len(recent),
                               max_gap_seconds=gap, evidence=evidence)
        if status == "calculated":
            summary.earlier_median, summary.recent_median = median(earlier), median(recent)
            summary.change = summary.recent_median - summary.earlier_median
            if (summary.change <= threshold if threshold < 0 else summary.change >= threshold):
                findings.append(Finding(rule_id=f"{metric}.trend.watch", priority="watch", metric=metric,
                    value=summary.change, unit=unit,
                    condition=f"median change {'<=' if threshold < 0 else '>='} {threshold}",
                    reading_id=evidence[-1].reading_id, observed_at=end, evidence=evidence))
        summaries.append(summary)
    return summaries, findings
