import pytest

from app.models.monitoring import ReadingInput
from app.services.risk import threshold_findings
from conftest import frame


@pytest.mark.parametrize("metric,edge,step,at_edge,beyond", [
    ("heart_rate_bpm", 40, -1, "watch", "high"), ("heart_rate_bpm", 50, -1, None, "watch"),
    ("heart_rate_bpm", 110, 1, None, "watch"), ("heart_rate_bpm", 130, 1, "watch", "high"),
    ("spo2_pct", 90, -1, "watch", "high"), ("spo2_pct", 94, -1, None, "watch"),
    ("systolic_mmhg", 80, -1, "watch", "high"), ("systolic_mmhg", 90, -1, None, "watch"),
    ("systolic_mmhg", 160, 1, None, "watch"), ("systolic_mmhg", 180, 1, "watch", "high"),
    ("diastolic_mmhg", 40, -1, "watch", "high"), ("diastolic_mmhg", 50, -1, None, "watch"),
    ("diastolic_mmhg", 100, 1, None, "watch"), ("diastolic_mmhg", 120, 1, "watch", "high"),
    ("temperature_c", 35, -0.1, "watch", "high"), ("temperature_c", 36, -0.1, None, "watch"),
    ("temperature_c", 38, 0.1, None, "watch"), ("temperature_c", 39, 0.1, "watch", "high"),
])
def test_strict_demo_boundaries(metric, edge, step, at_edge, beyond) -> None:
    for value, expected in ((edge, at_edge), (edge + step, beyond)):
        payload = frame() | {"systolic_mmhg": 125, "diastolic_mmhg": 70, metric: value}
        findings, complete = threshold_findings(ReadingInput.model_validate(payload))
        assert complete
        assert [f.priority for f in findings] == ([expected] if expected else [])
