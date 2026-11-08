// M6 acceptance: isolated PostgreSQL and a real TCP proxy that can cut browser transport.
const assert = require("node:assert/strict");
const { execFileSync } = require("node:child_process");
const http = require("node:http");
const net = require("node:net");
const { chromium } = require("playwright");

async function main() {
  const project = `wardzero-m6-ui-${Date.now()}`;
  const compose = (...args) => execFileSync("docker", ["compose", "-p", project, ...args], {
    encoding: "utf8", env: { ...process.env, APP_PORT: "0" }, stdio: ["pipe", "pipe", "pipe"],
  });
  const python = source => execFileSync("docker", ["compose", "-p", project, "exec", "-T", "app", "python", "-"],
    { input: source, encoding: "utf8" });
  let base;
  let browser;
  let proxy;
  let offline = false;
  let blockWS = false;
  const sockets = new Set();
  const upgraded = new Set();
  const upstreamSockets = new Set();
  const errors = [];
  const latency = [];
  const seq = [0, 0, 0];
  const patient = n => `20000000-0000-0000-0000-00000000000${n}`;
  const primary = "10000000-0000-0000-0000-000000000001";
  const get = async path => {
    const response = await fetch(base + "/api/v1" + path);
    assert.equal(response.status, 200); return response.json();
  };
  const reading = (n = 1, spo2 = 99, temperature = 36.7, heartRate = 73) => JSON.parse(python(`
import json, os, uuid
from datetime import UTC, datetime
from urllib.request import Request, urlopen
payload=dict(reading_id=str(uuid.uuid4()),device_id="30000000-0000-0000-0000-00000000000${n}",
    sequence=${++seq[n-1]},observed_at=datetime.now(UTC).isoformat(),heart_rate_bpm=${heartRate},spo2_pct=${spo2},
    systolic_mmhg=119,diastolic_mmhg=79,temperature_c=${temperature === null ? "None" : temperature})
with urlopen(Request("http://localhost:8000/api/v1/readings",data=json.dumps(payload).encode(),
    headers={"Content-Type":"application/json","X-Simulator-Key":os.environ["SIMULATOR_KEY"]})) as response:
    assert response.status==201
print(json.dumps(payload))
`));
  async function tabTo(page, target) {
    for (let i = 0; i < 150; i++) {
      if (await target.evaluate(el => el === document.activeElement)) return;
      await page.keyboard.press("Tab");
    }
    throw new Error("Action was not reachable by Tab");
  }
  console.log(`M6 browser project: ${project}`);
  try {
    compose("up", "-d", "--build", "--wait", "app");
    base = "http://" + compose("port", "app", "8000").trim();
    proxy = http.createServer((request, response) => {
      if (offline) { request.socket.destroy(); return; }
      const target = new URL(base);
      const upstream = http.request({ hostname: target.hostname, port: target.port,
        path: request.url, method: request.method, headers: request.headers }, incoming => {
        response.writeHead(incoming.statusCode, incoming.headers); incoming.pipe(response);
      });
      upstream.on("error", () => response.destroy());
      request.pipe(upstream);
    });
    proxy.on("connection", socket => { sockets.add(socket); socket.on("close", () => sockets.delete(socket)); });
    proxy.on("upgrade", (request, socket, head) => {
      if (offline || blockWS) { socket.destroy(); return; }
      const target = new URL(base);
      const upstream = net.connect(Number(target.port), target.hostname, () => {
        const headers = Object.entries(request.headers).map(([k, v]) => `${k}: ${v}`).join("\r\n");
        upstream.write(`${request.method} ${request.url} HTTP/${request.httpVersion}\r\n${headers}\r\n\r\n`);
        if (head.length) upstream.write(head);
        socket.pipe(upstream); upstream.pipe(socket);
      });
      upgraded.add(socket);
      upstreamSockets.add(upstream);
      socket.on("close", () => { upgraded.delete(socket); upstreamSockets.delete(upstream); upstream.destroy(); });
      socket.on("error", () => upstream.destroy());
      upstream.on("error", () => socket.destroy());
      upstream.on("close", () => socket.destroy());
    });
    await new Promise(resolve => proxy.listen(0, "127.0.0.1", resolve));
    const url = `http://127.0.0.1:${proxy.address().port}`;
    browser = await chromium.launch({ channel: "msedge", headless: true });
    const page = await browser.newPage({ viewport: { width: 1366, height: 768 } });
    page.setDefaultTimeout(12000);
    page.on("pageerror", error => errors.push(error.message));
    await page.goto(url);
    await page.getByText("Live updates connected", { exact: true }).waitFor();
    await page.locator(".patients").getByText("unavailable", { exact: true }).first().waitFor();
    await page.locator(".patients article").first().getByText("Unknown risk", { exact: true }).waitFor();
    await page.locator(".patients article").first().getByText("No vital readings available.", { exact: true }).waitFor();
    await page.keyboard.press("Tab");
    assert.equal(await page.locator(":focus").textContent(), "Skip to patient monitoring");
    await page.keyboard.press("Enter");
    for (let n = 1; n <= 3; n++) {
      const start = Date.now();
      const payload = reading(n);
      const row = page.locator(`[data-reading-id="${payload.reading_id}"]`);
      await row.getByText("No risk", { exact: true }).waitFor({ timeout: 2000 });
      await row.getByText("No configured concern detected", { exact: true }).waitFor();
      latency.push(Date.now() - start);
      assert.ok(latency.at(-1) <= 2000, `Reading display latency ${latency.at(-1)}ms`);
    }
    const panel = page.getByRole("region", { name: "History and observations" });
    const vitals = page.getByRole("region", { name: "Vital signs overview" });
    await vitals.getByText(/1 stored readings/).waitFor();
    await tabTo(page, vitals.getByLabel("Chart metric"));
    await page.keyboard.press("ArrowDown");
    await vitals.getByRole("img", { name: "Heart rate history from stored readings" }).waitFor();
    const chartBounds = await vitals.locator(".recharts-surface").boundingBox();
    assert.ok(chartBounds && chartBounds.width > 300 && chartBounds.height >= 200, "Chart must have visible dimensions");
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
    await page.screenshot({ path: "m6-browser-evidence.png", fullPage: true });
    console.log(`Committed reading → rendered card upper bounds (including request overhead): ${latency.join(", ")} ms.`);
    // A slow chart fetch must not block subsequent inbox hints.
    let releaseHistory;
    let historyStarted;
    const historyGate = new Promise(resolve => { releaseHistory = resolve; });
    const historyRequest = new Promise(resolve => { historyStarted = resolve; });
    await page.route("**/readings?*", async route => {
      historyStarted();
      await historyGate;
      await route.continue();
    }, { times: 1 });
    reading(1);
    await historyRequest;
    const low = reading(2, 93);
    await page.locator(`[data-reading-id="${low.reading_id}"]`).getByText("Low risk", { exact: true }).waitFor({ timeout: 2000 });
    const medium = reading(2, 93, 36.7, 115);
    await page.locator(`[data-reading-id="${medium.reading_id}"]`).getByText("Medium risk", { exact: true }).waitFor();
    const alertStart = Date.now();
    const high = reading(2, 88);
    const liveAlert = (await get("/alerts")).items.find(a => a.patient_id === patient(2) && a.kind === "risk");
    await page.locator(`[data-alert-id="${liveAlert.id}"]`).getByText("high priority", { exact: true }).waitFor({ timeout: 2000 });
    const alertLatency = Date.now() - alertStart;
    assert.ok(alertLatency <= 2000, `Alert display latency ${alertLatency}ms`);
    console.log(`Committed alert → rendered inbox upper bound: ${alertLatency} ms.`);
    releaseHistory();
    const highRow = page.locator(`[data-reading-id="${high.reading_id}"]`);
    await highRow.getByText("High risk", { exact: true }).waitFor();

    // Real browser TCP interruption: app stays up, so it can commit a missed alert.
    offline = true;
    for (const socket of sockets) socket.destroy();
    await page.getByText(/Live updates disconnected/).waitFor();
    await page.getByRole("alert").getByText(/Refresh failed/).waitFor();
    await page.locator(".patients").getByText(/Unknown — showing cached data/).first().waitFor();
    await highRow.getByText("High risk", { exact: true }).waitFor();
    await highRow.getByText(/Last received status · Awaiting acknowledgement/).waitFor();
    await panel.getByText(/Cached context/).waitFor();
    const missed = reading(1, 88);
    const alert = (await get("/alerts")).items.find(a => a.patient_id === patient(1) && a.kind === "risk");
    assert.ok(alert);
    offline = false;
    await page.getByText("Live updates connected", { exact: true }).waitFor({ timeout: 20000 });
    let card = page.locator(`[data-alert-id="${alert.id}"]`);
    await card.getByText(/Awaiting acknowledgement/).waitFor();
    await page.locator(`[data-reading-id="${missed.reading_id}"]`).waitFor();
    await vitals.getByText(/3 stored readings/).waitFor();
    console.log("Passed real transport cut, cached/unknown state, and REST reconciliation of missed alert/history.");

    // Lose the actual committed acknowledgement response, then reload and retry the ID.
    let ackId;
    await page.route("**/acknowledge", async route => {
      ackId = route.request().postDataJSON().command_id;
      assert.equal((await route.fetch()).status(), 200); await route.abort("failed");
    }, { times: 1 });
    await tabTo(page, card.getByRole("button", { name: "Acknowledge", exact: true }));
    await page.keyboard.press("Enter");
    await card.getByRole("alert").getByText(/unconfirmed/).waitFor();
    await page.reload();
    await card.getByRole("button", { name: "Retry saved acknowledgement" }).waitFor();
    let retryAck;
    await page.route("**/acknowledge", async route => { retryAck = route.request().postDataJSON().command_id; await route.continue(); }, { times: 1 });
    await card.getByRole("button", { name: "Retry saved acknowledgement" }).click();
    await card.getByRole("button", { name: "Retry saved acknowledgement" }).waitFor({ state: "detached" });
    assert.equal(retryAck, ackId);
    assert.equal(compose("exec", "-T", "db", "psql", "-U", "wardzero", "-Atc",
      `SELECT count(*) FROM alert_events WHERE command_id='${ackId}'`).trim(), "1");

    // Resolution note remains visible and retryable on a failed request/reload.
    for (let i = 0; i < 3; i++) reading();
    await card.getByText(/Recovery: 3\/3/).waitFor();
    await card.getByLabel(/Resolution note/).fill("M6 recovery <literal> note");
    let resolution;
    await page.route("**/resolve", async route => { resolution = route.request().postDataJSON(); await route.abort("failed"); }, { times: 1 });
    await card.getByRole("button", { name: "Resolve alert", exact: true }).click();
    await card.getByRole("alert").getByText(/Note retained/).waitFor();
    await page.reload();
    assert.equal(await card.getByLabel(/Resolution note/).inputValue(), resolution.note);
    let retryResolution;
    await page.route("**/resolve", async route => { retryResolution = route.request().postDataJSON(); await route.continue(); }, { times: 1 });
    await card.getByRole("button", { name: "Retry saved resolution" }).click();
    await page.getByLabel("Show recently resolved alerts").check();
    await card.getByText(/Resolved at/).waitFor();
    assert.deepEqual(retryResolution, resolution);
    await tabTo(page, card.getByText("Lifecycle history", { exact: true }));
    await page.keyboard.press("Enter");
    await card.getByText("Resolution note: M6 recovery <literal> note", { exact: true }).waitFor();

    // Observation payload survives both navigation and a failed save/reload.
    await vitals.getByLabel("Selected patient").selectOption(patient(3));
    await panel.getByLabel("Observation tag").selectOption("dizziness");
    await panel.getByLabel(/Optional note/).fill("M6 retained observation");
    let observation;
    await page.route("**/observations", async route => { observation = route.request().postDataJSON(); await route.abort("failed"); }, { times: 1 });
    await panel.getByRole("button", { name: "Save observation", exact: true }).click();
    await panel.getByRole("alert").getByText(/Draft retained/).waitFor();
    await page.reload();
    await vitals.getByLabel("Selected patient").selectOption(patient(3));
    assert.equal(await panel.getByLabel(/Optional note/).inputValue(), observation.note);
    let retryObservation;
    await page.route("**/observations", async route => { retryObservation = route.request().postDataJSON(); await route.continue(); }, { times: 1 });
    await panel.getByRole("button", { name: "Retry saved observation" }).click();
    await panel.getByRole("status").getByText("Observation saved.").waitFor();
    assert.deepEqual(retryObservation, observation);
    const contextStart = Date.now();
    const clear = await fetch(`${base}/api/v1/patients/${patient(3)}/observations`, {
      method: "POST", headers: { "Content-Type": "application/json", "X-Demo-Caregiver-Id": primary },
      body: JSON.stringify({ observation_id: require("node:crypto").randomUUID(), tag: "dizziness", present: false }),
    });
    assert.equal(clear.status, 201);
    await panel.getByText("No active structured observations.", { exact: true }).waitFor({ timeout: 2000 });
    assert.ok(Date.now() - contextStart <= 2000);
    console.log(`Externally committed observation clear → rendered context upper bound: ${Date.now() - contextStart} ms.`);
    console.log("Passed acknowledgement response loss and retained acknowledgement/observation/resolution payloads across reload; keyboard actions and saved history.");

    // Cut only WebSocket connections: real HTTP polling must still load new evidence.
    blockWS = true;
    for (const socket of upgraded) socket.destroy();
    await page.getByText(/Live updates disconnected/).waitFor();
    const fallback = reading(2, 88, null);
    const incompleteRow = page.locator(`[data-reading-id="${fallback.reading_id}"]`);
    await incompleteRow.getByText("incomplete", { exact: true }).waitFor({ timeout: 7000 });
    await incompleteRow.getByText("High risk", { exact: true }).waitFor();
    await incompleteRow.getByText("Oxygen saturation was below the demo limit (88%).", { exact: true }).waitFor();
    blockWS = false;
    await page.getByText("Live updates connected", { exact: true }).waitFor({ timeout: 20000 });
    console.log("Passed WebSocket-only failure with working polling fallback and incomplete High rendering.");

    reading(1);
    const missing = reading(1, 99, null);
    const missingRow = page.locator(`[data-reading-id="${missing.reading_id}"]`);
    await missingRow.getByText("Unknown risk", { exact: true }).waitFor();
    await missingRow.getByText("Insufficient measurements.", { exact: true }).waitFor();

    // Let a real reading age past the approved freshness limit.
    const stable = reading(1);
    const stableRow = page.locator(`[data-reading-id="${stable.reading_id}"]`);
    await stableRow.getByText("fresh", { exact: true }).waitFor();
    await stableRow.getByText("stale", { exact: true }).waitFor({ timeout: 40000 });
    await stableRow.getByText("Unknown risk", { exact: true }).waitFor();
    await stableRow.getByText("Vital readings are stale.", { exact: true }).waitFor();
    const lastKnown = stableRow.getByText(/Last known concern · No risk/);
    await lastKnown.waitFor();
    assert.equal(new Date(await lastKnown.locator("time").getAttribute("datetime")).toISOString(),
      new Date(stable.observed_at).toISOString());
    // Leave the TCP connection open but stop forwarding frames. Heartbeat loss must be detected.
    blockWS = true;
    for (const upstream of upstreamSockets) upstream.pause();
    await page.getByText(/Live updates disconnected/).waitFor({ timeout: 28000 });
    blockWS = false;
    await page.getByText("Live updates connected", { exact: true }).waitFor({ timeout: 20000 });
    console.log("Passed silent WebSocket heartbeat loss and reconnect.");
    const saved = await get(`/alerts/${alert.id}`);
    compose("restart", "app");
    compose("up", "-d", "--wait", "app");
    base = "http://" + compose("port", "app", "8000").trim();
    await page.getByText("Live updates connected", { exact: true }).waitFor({ timeout: 20000 });
    assert.deepEqual(await get(`/alerts/${alert.id}`), saved);
    console.log("Passed browser reconnection after a real app restart with resolved history preserved.");
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
    await page.screenshot({ path: "m6-disconnected-recovery-evidence.png", fullPage: true });
    assert.deepEqual(errors, []);
    console.log("Passed real staleness transition, last-known concern, laptop layout and no browser page errors.");
  } finally {
    if (browser) await browser.close();
    for (const socket of sockets) socket.destroy();
    if (proxy) await new Promise(resolve => proxy.close(resolve));
    compose("down");
    console.log(`Stopped ${project}; retained PostgreSQL evidence volume.`);
  }
}
main().catch(error => { console.error(error); process.exitCode = 1; });
