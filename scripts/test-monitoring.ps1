# Run against a healthy M1 stack. The app is restarted; both volumes are retained.
param([string]$EdgePath = (Join-Path ${env:ProgramFiles(x86)} 'Microsoft/Edge/Application/msedge.exe'))
$ErrorActionPreference = 'Stop'
$binding = docker compose port app 8000
if ($LASTEXITCODE -ne 0 -or !$binding) { throw 'Start the Compose stack first.' }
$base = "http://$binding"

# Capture real rendered cards, then follow their stable IDs while sampling continues.
$tempRoot = (Resolve-Path ([IO.Path]::GetTempPath())).Path
$profile = Join-Path $tempRoot ('wardzero-browser-' + [guid]::NewGuid().ToString('N'))
try {
    $html = (& $EdgePath --headless --disable-gpu --no-first-run "--user-data-dir=$profile" --virtual-time-budget=3000 --dump-dom "$base/" 2>$null | Out-String)
    if ($LASTEXITCODE -ne 0 -or !$html.Contains('Service ready')) { throw 'Browser readiness check failed.' }
    $cards = [regex]::Matches($html, '<article data-reading-id="([0-9a-f-]{36})">(.+?)</article>', 'Singleline')
    if ($cards.Count -ne 3) { throw "Expected three rendered readings, found $($cards.Count)." }
} finally {
    if (Test-Path -LiteralPath $profile) {
        $resolved = (Resolve-Path -LiteralPath $profile).Path
        if ((Split-Path $resolved) -ne $tempRoot.TrimEnd('\') -or (Split-Path $resolved -Leaf) -notmatch '^wardzero-browser-[a-f0-9]{32}$') {
            throw 'Unexpected browser profile location.'
        }
        Remove-Item -LiteralPath $resolved -Recurse -Force
    }
}

$dashboard = Invoke-RestMethod "$base/api/v1/dashboard"
$evidence = foreach ($card in $cards) {
    $id = [guid]::Parse($card.Groups[1].Value).ToString()
    $cardHtml = $card.Groups[2].Value
    $patient = @($dashboard.patients.patient | Where-Object { $cardHtml.Contains($_.display_name) })
    if ($patient.Count -ne 1) { throw "Cannot identify patient on card $id" }
    $patientId = $patient[0].id
    $historyUrl = "$base/api/v1/patients/$patientId/readings"
    $stored = (Invoke-RestMethod $historyUrl).items | Where-Object reading_id -eq $id
    if (!$stored -or !$cardHtml.Contains("<dd>$($stored.heart_rate_bpm) <small>bpm")) {
        throw "Rendered heart rate differs from stored reading $id"
    }
    $lookup = @'
import json, os, sqlite3, sys
with sqlite3.connect(os.environ['BUFFER_PATH']) as conn:
    payload, status = conn.execute('SELECT payload, status FROM frames WHERE reading_id = ?', (sys.argv[1],)).fetchone()
    assert status == 'accepted', status
    print(payload)
'@
    $buffered = $lookup | docker compose exec -T simulator python - $id
    if ($LASTEXITCODE -ne 0) { throw "Missing accepted buffer record $id" }
    $frame = $buffered | ConvertFrom-Json
    foreach ($field in 'device_id','reading_id','sequence','heart_rate_bpm','spo2_pct','systolic_mmhg','diastolic_mmhg','temperature_c') {
        if ($frame.$field -ne $stored.$field) { throw "Buffer and API differ on $field for $id" }
    }
    if ([datetimeoffset]$frame.observed_at -ne [datetimeoffset]$stored.observed_at) { throw "Observation time differs for $id" }
    [pscustomobject]@{ Name=$patient[0].display_name; Id=$id; Url=$historyUrl; Received=$stored.received_at }
}
docker compose restart app
if ($LASTEXITCODE -ne 0) { throw 'App restart failed.' }
docker compose up -d --wait --wait-timeout 60 app
if ($LASTEXITCODE -ne 0) { throw 'App did not become ready.' }
foreach ($record in $evidence) {
    $saved = @((Invoke-RestMethod $record.Url).items | Where-Object reading_id -eq $record.Id)
    if ($saved.Count -ne 1 -or $saved[0].received_at -ne $record.Received) { throw "Restart persistence failed for $($record.Id)" }
    Write-Host "$($record.Name) $($record.Id) matched browser, SQLite and PostgreSQL-backed history across app restart."
}
