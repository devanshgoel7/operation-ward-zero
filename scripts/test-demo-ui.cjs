// M7's nine-step demo, real sampling/outage, durable IDs, and silent backup recording.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { execFileSync, spawn } = require('node:child_process');
const { chromium } = require('playwright');

const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
async function until(label, probe, timeout = 90000) {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) { const result = await probe(); if (result) return result; await delay(1000); }
  throw new Error(`Timed out: ${label}`);
}
async function main() {
  const project = `wardzero-m7-demo-${Date.now()}`;
  const output = path.resolve(process.argv[2] || `artifacts/${project}`);
  fs.mkdirSync(output, { recursive: true });
  const env = { ...process.env, APP_PORT: '0' };
  const docker = (...args) => execFileSync('docker', args, { encoding: 'utf8', env, timeout: 240000 });
  const compose = (...args) => docker('compose', '-p', project, ...args);
  const python = source => execFileSync('docker', ['compose', '-p', project, 'run', '--rm', '-T', '--no-deps', 'simulator', 'python', '-'],
    { encoding: 'utf8', env, input: source, timeout: 180000 });
  const scenario = name => compose('exec', '-T', 'simulator', 'python', '-m', 'simulator.scenario', 'mira', name);
  const status = () => JSON.parse(compose('exec', '-T', 'simulator', 'python', '-m', 'simulator.recovery', 'status')).counts;
  const report = { project, started_at: new Date().toISOString(), steps: [], continuous_samples: 0 };
  const step = (name, evidence = {}) => {
    report.steps.push({ name, at: new Date().toISOString(), ...evidence });
    fs.writeFileSync(path.join(output, 'demo.json'), JSON.stringify(report, null, 2));
    console.log(name, JSON.stringify(evidence));
  };
  let browser, context, page, base, recording = false, recorder;
  const frames = [];
  const get = async route => {
    const response = await fetch(base + route, { signal: AbortSignal.timeout(8000) });
    assert.equal(response.status, 200); return response.json();
  };
  const reconcile = () => {
    compose('stop', 'simulator');
    compose('run', '--rm', '-T', '--no-deps', 'simulator', 'python', '-m', 'simulator.recovery', 'drain');
    const ids = compose('exec', '-T', 'db', 'psql', '-v', 'ON_ERROR_STOP=1', '-U', 'wardzero', '-Atc', 'SELECT id FROM readings ORDER BY id');
    const result = JSON.parse(execFileSync('docker', ['compose', '-p', project, 'run', '--rm', '-T', '--no-deps', 'simulator',
      'python', '-m', 'simulator.recovery', 'verify', '--require-drained'], { encoding: 'utf8', env, input: ids, timeout: 180000 }));
    assert.equal(result.ok, true); assert.equal(result.pending, 0); assert.equal(result.quarantined, 0);
    return result;
  };
  try {
    compose('config', '-q');
    compose('build');
    compose('up', '-d', '--wait', '--wait-timeout', '120', 'app');
    base = 'http://' + compose('port', 'app', '8000').trim();
    // Seed only synthetic stable history through the same SQLite commit/uploader path.
    // No direct PostgreSQL writes or altered clinical/lifecycle clocks.
    python(`
import os
from contextlib import closing
from pathlib import Path
from datetime import UTC, datetime, timedelta
from simulator.buffer import DEVICE_IDS, connect, initialize, generate
from simulator.scenario import select
with closing(connect(Path(os.environ['BUFFER_PATH']))) as conn:
    initialize(conn)
    for device in DEVICE_IDS: select(conn, device, 'stable')
    end=datetime.now(UTC)-timedelta(seconds=5)
    for i in range(24):
        for device in DEVICE_IDS: generate(conn, device, end-timedelta(seconds=115-5*i))
`);
    compose('run', '--rm', '-T', '--no-deps', 'simulator', 'python', '-m', 'simulator.recovery', 'drain');
    compose('up', '-d', '--wait', 'simulator');
    browser = await chromium.launch({ channel: 'msedge', headless: true });
    context = await browser.newContext({ viewport: { width: 1366, height: 900 } });
    page = await context.newPage();
    page.setDefaultTimeout(20000);
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(base);
    await page.getByText('Live updates connected', { exact: true }).waitFor();
    await page.getByText('Service ready', { exact: true }).waitFor();
    const roster = page.getByRole('region', { name: 'Patient roster' });
    await roster.getByText('No risk', { exact: true }).nth(2).waitFor();
    recording = true;
    recorder = (async () => {
      while (recording) {
        const filename = `frame-${String(frames.length).padStart(5, '0')}.jpg`;
        const at = Date.now();
        await page.screenshot({ path: path.join(output, filename), type: 'jpeg', quality: 65 });
        frames.push({ filename, at });
        await delay(1000);
      }
    })();
    // Attach a handler immediately so recording failures cannot become unhandled rejections.
    recorder.catch(() => { recording = false; });
    step('1. Stable patients and fresh startup', { base, migration: compose('exec', '-T', 'app', 'alembic', 'current').trim() });
    let previous = (await get('/api/v1/dashboard')).patients.map(p => p.latest_reading.reading_id);
    const startCounts = status();
    const continuousStart = Date.now();
    while (Date.now() - continuousStart < 60000) {
      await delay(5000);
      assert.equal((await get('/health/ready')).status, 'ready');
      const snapshot = await get('/api/v1/dashboard');
      assert.ok(snapshot.patients.every(p => p.data_quality === 'fresh'));
      const current = snapshot.patients.map(p => p.latest_reading.reading_id);
      assert.ok(current.every((id, i) => id !== previous[i]), 'All three monitors continue sampling');
      previous = current; report.continuous_samples++;
    }
    assert.ok(status().accepted >= startCounts.accepted + 36);
    step('Short continuous run passed', { seconds: (Date.now() - continuousStart) / 1000, checks: report.continuous_samples });
    scenario('deterioration');
    const snapshot = await until('falling oxygen and rising heart-rate trends', async () => {
      const s = await get('/api/v1/dashboard');
      const findings = s.patients[0].current_assessment?.findings ?? [];
      return ['spo2_pct.trend.watch', 'heart_rate_bpm.trend.watch'].every(id => findings.some(f => f.rule_id === id)) && s;
    });
    const panel = page.getByRole('region', { name: 'History and observations' });
    await panel.scrollIntoViewIfNeeded();
    await panel.getByText(/change -3 percentage points/).waitFor();
    await panel.getByLabel(/Optional note/).fill('Synthetic M7 demonstration: breathlessness observed.');
    await panel.getByRole('button', { name: 'Save observation', exact: true }).click();
    await panel.getByText('Observation saved.', { exact: true }).waitFor();
    const combined = await get('/api/v1/dashboard');
    const finding = combined.patients[0].current_assessment.findings.find(f => f.rule_id === 'breathlessness.spo2.high');
    assert.ok(finding && finding.evidence.length >= 16 && finding.observations.length === 1);
    step('2. Falling SpO2 plus breathlessness', { assessment_id: combined.patients[0].current_assessment.id, reading_ids: finding.evidence.map(e => e.reading_id) });
    const alert = combined.active_alerts.find(a => a.patient_id === snapshot.patients[0].patient.id && a.kind === 'risk');
    const card = page.locator(`[data-alert-id="${alert.id}"]`);
    await card.scrollIntoViewIfNeeded();
    await card.getByText('High risk', { exact: true }).first().waitFor();
    await card.getByText('Stored reading evidence (' + finding.evidence.length + ')', { exact: true }).first().click();
    await card.getByText(new RegExp(finding.evidence[0].reading_id)).first().waitFor();
    await page.screenshot({ path: path.join(output, 'explained-alert.png'), fullPage: true });
    step('3. Inspected exact stored evidence', { alert_id: alert.id });
    const escalated = await until('saved primary timeout', async () => {
      const a = await get(`/api/v1/alerts/${alert.id}`); return a.escalated_at && a;
    }, 65000);
    const lag = Date.parse(escalated.escalated_at) - Date.parse(alert.escalation_due_at);
    assert.ok(lag >= 0 && lag <= 5000, `Escalation lag ${lag} ms`);
    step('4. Backup escalation', { lag_ms: lag });
    await page.getByLabel('Demo caregiver').selectOption('10000000-0000-0000-0000-000000000002');
    await card.getByRole('button', { name: 'Acknowledge', exact: true }).click();
    await card.getByText(/Acknowledged by Backup caregiver/).waitFor();
    const acknowledged = await get(`/api/v1/alerts/${alert.id}`);
    assert.equal(acknowledged.status, 'acknowledged');
    step('5. Backup acknowledgement saved');
    const container = compose('ps', '-q', 'simulator').trim();
    const network = project + '_default';
    const initial = status();
    docker('network', 'disconnect', network, container);
    try {
      await roster.scrollIntoViewIfNeeded();
      await until('offline buffer and stale data', async () => {
        const s = await get('/api/v1/dashboard');
        return (status().pending >= 18 && s.patients.every(p => p.data_quality === 'stale'));
      });
      assert.equal(status().accepted, initial.accepted);
      step('6. Real network disconnected; buffer grew', { counts: status() });
      await page.screenshot({ path: path.join(output, 'network-outage.png'), fullPage: true });
    } finally { docker('network', 'connect', network, container); }
    await until('buffer drain', () => !status().pending);
    const recoveredAlert = await get(`/api/v1/alerts/${alert.id}`);
    for (const event of acknowledged.events) assert.deepEqual(recoveredAlert.events.find(e => e.id === event.id), event);
    assert.equal(recoveredAlert.status, 'acknowledged');
    step('7. Replay preserved alert history');
    step('8. Exact identifier reconciliation', reconcile());
    compose('start', 'simulator');
    scenario('recovery');
    await panel.scrollIntoViewIfNeeded();
    await panel.getByLabel('Observation state').selectOption('false');
    await panel.getByLabel(/Optional note/).fill('Synthetic recovery: breathlessness cleared.');
    await panel.getByRole('button', { name: 'Save observation', exact: true }).click();
    await panel.getByText('No active structured observations.').waitFor();
    await until('three fresh recovered readings', async () => (await get(`/api/v1/alerts/${alert.id}`)).recovery_count === 3);
    await card.scrollIntoViewIfNeeded();
    await card.getByText(/Recovery: 3\/3/).waitFor();
    await card.getByLabel(/Resolution note/).fill('M7: three fresh complete recovery readings; synthetic episode reviewed.');
    await page.getByLabel('Show recently resolved alerts').check();
    await card.getByRole('button', { name: 'Resolve alert', exact: true }).click();
    await card.getByText(/Resolved at/).waitFor();
    await card.getByText('Lifecycle history', { exact: true }).click();
    await card.getByText(/Resolution note: M7:/).waitFor();
    const resolved = await get(`/api/v1/alerts/${alert.id}`);
    assert.equal(resolved.status, 'resolved');
    assert.equal(resolved.events.filter(e => e.event_type === 'escalated').length, 1);
    assert.equal(resolved.events.filter(e => e.event_type === 'acknowledged').length, 1);
    assert.equal(resolved.events.filter(e => e.event_type === 'resolved').length, 1);
    step('9. Recovery and resolution saved', { alert: resolved });
    compose('restart', 'app');
    compose('up', '-d', '--wait', 'app');
    base = 'http://' + compose('port', 'app', '8000').trim();
    assert.deepEqual(await get(`/api/v1/alerts/${alert.id}`), resolved);
    await page.goto(base);
    await page.getByText('Live updates connected', { exact: true }).waitFor();
    await page.getByLabel('Demo caregiver').selectOption('10000000-0000-0000-0000-000000000002');
    await page.getByLabel('Show recently resolved alerts').check();
    await card.getByText(/Resolved at/).waitFor();
    step('Restart preserved exact resolved state and history');
    step('Final identifier reconciliation', reconcile());
    assert.deepEqual(errors, []);
    report.passed = true;
  } finally {
    recording = false;
    try {
      if (recorder) await recorder;
      if (frames.length) {
        const concat = [];
        for (let i = 0; i < frames.length; i++) {
          concat.push(`file '${frames[i].filename}'`, `duration ${((frames[i + 1]?.at ?? Date.now()) - frames[i].at) / 1000}`);
        }
        concat.push(`file '${frames.at(-1).filename}'`);
        fs.writeFileSync(path.join(output, 'frames.txt'), concat.join('\n'));
        await new Promise((resolve, reject) => {
          const process = spawn('ffmpeg', ['-y', '-loglevel', 'error', '-f', 'concat', '-safe', '0', '-i', 'frames.txt',
            '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-r', '10', '-movflags', '+faststart', 'backup-demo.mp4'], { cwd: output, stdio: 'inherit' });
          process.on('error', reject); process.on('exit', code => code === 0 ? resolve() : reject(new Error(`ffmpeg exit ${code}`)));
        });
        for (const frame of frames) fs.unlinkSync(path.join(output, frame.filename));
        report.recording = 'backup-demo.mp4';
      }
    } finally {
      if (browser) await browser.close();
      compose('down');
      report.finished_at = new Date().toISOString();
      fs.writeFileSync(path.join(output, 'demo.json'), JSON.stringify(report, null, 2));
      console.log(`Stopped ${project}; retained both evidence volumes. Evidence: ${output}`);
    }
  }
  assert.equal(report.passed, true);
}
main().catch(error => { console.error(error); process.exitCode = 1; });
