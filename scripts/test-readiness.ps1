# Run from the repository root with the M0 stack already healthy.
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Net.Http
$binding = docker compose port app 8000
if ($LASTEXITCODE -ne 0 -or !$binding) { throw 'Start the Compose app first.' }
$client = [System.Net.Http.HttpClient]::new()
$client.BaseAddress = [uri]"http://$binding/"
$client.Timeout = [TimeSpan]::FromSeconds(6)

function Read-Health([string]$Path, [int]$ExpectedStatus) {
    $response = $client.GetAsync($Path).GetAwaiter().GetResult()
    try {
        $body = $response.Content.ReadAsStringAsync().GetAwaiter().GetResult()
        if ([int]$response.StatusCode -ne $ExpectedStatus) {
            throw "$Path returned $([int]$response.StatusCode), expected $ExpectedStatus. $body"
        }
        Write-Host "$Path $ExpectedStatus $body"
        return ($body | ConvertFrom-Json)
    } finally {
        $response.Dispose()
    }
}

try {
    if ((Read-Health '/health/ready' 200).status -ne 'ready') { throw 'Expected ready before outage.' }
    try {
        docker compose stop db
        if ($LASTEXITCODE -ne 0) { throw 'Could not stop the project database.' }
        if ((Read-Health '/health/live' 200).status -ne 'live') { throw 'Expected live during outage.' }
        $outage = Read-Health '/health/ready' 503
        if ($outage.status -ne 'unready' -or $outage.database -ne 'unavailable' -or
            $outage.error.code -ne 'database_unavailable' -or !$outage.request_id) {
            throw 'Unexpected outage response.'
        }
    } finally {
        docker compose up -d --wait --wait-timeout 60 db
        if ($LASTEXITCODE -ne 0) { throw 'Database recovery failed.' }
    }
    $recovered = Read-Health '/health/ready' 200
    if ($recovered.status -ne 'ready' -or $recovered.migrations -ne 'current') {
        throw 'Expected ready with current migrations after recovery.'
    }
} finally {
    $client.Dispose()
}
