# Start an isolated M2 dashboard with one explained episode for the caregiver to acknowledge.
param([ValidateRange(1, 65535)][int]$Port = 8012)
$ErrorActionPreference = 'Stop'
$previousPort = $env:APP_PORT
try {
    $env:APP_PORT = "$Port"
    docker compose -p wardzero-m2-demo up --build --wait --wait-timeout 120 app
    if ($LASTEXITCODE -ne 0) { throw 'Could not start the M2 demo.' }
    @'
import os
from datetime import UTC, datetime
from uuid import uuid4

import httpx

with httpx.Client(base_url="http://127.0.0.1:8000/api/v1") as client:
    dashboard = client.get("/dashboard").raise_for_status().json()
    snapshot = dashboard["patients"][0]
    latest = snapshot["latest_reading"]
    for sequence, oxygen, temperature in [(1, 93, 36.7), (2, 88, None)]:
        if latest and sequence <= latest["sequence"]:
            continue
        frame = {
            "reading_id": str(uuid4()), "device_id": snapshot["patient"]["device_id"], "sequence": sequence,
            "observed_at": datetime.now(UTC).isoformat(), "heart_rate_bpm": 75, "spo2_pct": oxygen,
            "systolic_mmhg": 119, "diastolic_mmhg": 79, "temperature_c": temperature,
        }
        receipt = client.post("/readings", json=frame, headers={"X-Simulator-Key": os.environ["SIMULATOR_KEY"]})
        print(receipt.raise_for_status().json())
'@ | docker compose -p wardzero-m2-demo exec -T app python -
    if ($LASTEXITCODE -ne 0) { throw 'Could not seed the M2 demo readings.' }
    Write-Host "Open http://127.0.0.1:$Port/ to inspect Mira Shah's evidence and acknowledge as Alex Morgan."
} finally {
    $env:APP_PORT = $previousPort
}
