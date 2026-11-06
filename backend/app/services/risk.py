"""Strict absolute thresholds for the fictional adult demonstration."""

from dataclasses import dataclass

from app.models.alerts import Finding, Priority
from app.models.monitoring import Reading

RULE_VERSION = "demo-thresholds-v1"


@dataclass(frozen=True)
class Threshold:
    metric: str
    unit: str
    watch_low: float | None
    watch_high: float | None
    high_low: float | None
    high_high: float | None


THRESHOLDS = (
    Threshold("heart_rate_bpm", "bpm", 50, 110, 40, 130),
    Threshold("spo2_pct", "%", 94, None, 90, None),
    Threshold("systolic_mmhg", "mmHg", 90, 160, 80, 180),
    Threshold("diastolic_mmhg", "mmHg", 50, 100, 40, 120),
    Threshold("temperature_c", "°C", 36, 38, 35, 39),
)


def threshold_findings(reading: Reading) -> tuple[list[Finding], bool]:
    findings = []
    complete = True
    for rule in THRESHOLDS:
        value = getattr(reading, rule.metric)
        if value is None:
            complete = False
            continue
        levels: tuple[tuple[Priority, float | None, float | None], ...] = (
            ("high", rule.high_low, rule.high_high), ("watch", rule.watch_low, rule.watch_high),
        )
        for priority, low, high in levels:
            if low is not None and value < low:
                direction, condition = "low", f"< {low:g}"
            elif high is not None and value > high:
                direction, condition = "high", f"> {high:g}"
            else:
                continue
            findings.append(Finding(
                rule_id=f"{rule.metric}.{direction}.{priority}", priority=priority, metric=rule.metric,
                value=value, unit=rule.unit, condition=condition, reading_id=reading.reading_id,
                observed_at=reading.observed_at,
            ))
            break
    return findings, complete
