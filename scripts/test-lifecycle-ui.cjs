// M5 acceptance uses a separate PostgreSQL volume, a real loop and app restarts.
const assert = require("node:assert/strict");
const { execFileSync } = require("node:child_process");
const { chromium } = require("playwright");

async function main() {
  const project = `wardzero-m5-ui-${Date.now()}`;
  const compose = (...args) => execFileSync("docker", ["compose", "-p", project, ...args], {
    encoding: "utf8", env: { ...process.env, APP_PORT: "0" }, stdio: ["pipe", "pipe", "pipe"],
  });
  const sql = statement => compose("exec", "-T", "db", "psql", "-v", "ON_ERROR_STOP=1", "-U", "wardzero", "-Atc", statement).trim();
  const reading = (sequence, spo2 = 99, patient = 1) => execFileSync("docker",
    ["compose", "-p", project, "exec", "-T", "app", "python", "-"], { encoding: "utf8", input: `
import json, os, uuid
from datetime import UTC, datetime
from urllib.request import Request, urlopen
payload=dict(reading_id=str(uuid.uuid4()),device_id="30000000-0000-0000-0000-00000000000${patient}",
    sequence=${sequence},observed_at=datetime.now(UTC).isoformat(),heart_rate_bpm=73,spo2_pct=${spo2},
    systolic_mmhg=119,diastolic_mmhg=79,temperature_c=36.7)
with urlopen(Request("http://localhost:8000/api/v1/readings",data=json.dumps(payload).encode(),
    headers={"Content-Type":"application/json","X-Simulator-Key":os.environ["SIMULATOR_KEY"]})) as response:
    assert response.status==201
` });
  let browser;
  let base;
  const get = async path => {
    const response = await fetch(base + "/api/v1" + path);
    assert.equal(response.status, 200);
    return response.json();
  };
  console.log(`M5 browser project: ${project}`);
  try {
    compose("up", "-d", "--build", "--wait", "app");
    base = "http://" + compose("port", "app", "8000").trim();
    reading(1, 88);
    const alert = (await get("/alerts")).items.find(a => a.kind === "risk");
    browser = await chromium.launch({ channel: "msedge", headless: true });
    const page = await browser.newPage({ viewport: { width: 1366, height: 900 } });
    const errors = [];
    page.on("pageerror", error => errors.push(error.message));
    await page.goto(base);
    let card = page.locator(`[data-alert-id="${alert.id}"]`);
    await card.getByText(/Assigned to primary caregiver Alex/).waitFor();
    await card.getByText(/Backup escalation due/).waitFor();
    const deadline = Date.parse(alert.escalation_due_at);
    let escalated;
    while (Date.now() < deadline + 6500) {
      const current = await get(`/alerts/${alert.id}`);
      if (current.escalated_at) { escalated = current; break; }
      await new Promise(resolve => setTimeout(resolve, 100));
    }
    assert.ok(escalated, "Actual periodic loop must escalate the saved deadline");
    const lag = Date.parse(escalated.escalated_at) - deadline;
    assert.ok(lag >= 0 && lag <= 5000, `Escalation lag ${lag} ms exceeded one loop interval`);
    console.log(`Actual primary timeout processed ${lag} ms after deadline.`);
    await page.getByLabel("Demo caregiver").selectOption("10000000-0000-0000-0000-000000000002");
    await card.getByText(/Escalated to backup caregiver Sam/).waitFor();
    await card.getByRole("button", { name: "Acknowledge", exact: true }).click();
    await card.getByText(/Acknowledged by Sam/).waitFor();
    await card.getByLabel(/Resolution note/).fill("Recovery verified <b>synthetic note</b>");
    await card.getByRole("button", { name: "Resolve alert", exact: true }).click();
    await card.getByRole("alert").getByText(/three consecutive fresh complete readings/).waitFor();
    await page.reload();
    await page.getByLabel("Demo caregiver").selectOption("10000000-0000-0000-0000-000000000002");
    assert.equal(await card.getByLabel(/Resolution note/).inputValue(), "Recovery verified <b>synthetic note</b>");
    for (const sequence of [2, 3, 4]) reading(sequence);
    await card.getByText(/Recovery: 3\/3/).waitFor();
    await page.getByLabel("Show recently resolved alerts").check();
    let lostCommand;
    await page.route("**/resolve", async route => {
      lostCommand = route.request().postDataJSON().command_id;
      const response = await route.fetch();
      assert.equal(response.status(), 200);
      await route.abort("failed");
    }, { times: 1 });
    await card.getByRole("button", { name: "Retry saved resolution" }).click();
    await card.getByText(/Resolved at/).waitFor();
    await page.reload();
    await page.getByLabel("Demo caregiver").selectOption("10000000-0000-0000-0000-000000000002");
    await page.getByLabel("Show recently resolved alerts").check();
    await card.getByRole("button", { name: "Retry saved resolution" }).click();
    await card.getByRole("button", { name: "Retry saved resolution" }).waitFor({ state: "detached" });
    await card.getByText("Lifecycle history", { exact: true }).click();
    await card.getByText("Resolution note: Recovery verified <b>synthetic note</b>", { exact: true }).waitFor();
    await card.getByText(/seconds since opening\/reopening/).waitFor();
    assert.equal(await card.locator("b").filter({ hasText: "synthetic note" }).count(), 0);
    assert.equal(sql(`SELECT count(*) FROM alert_events WHERE command_id='${lostCommand}'`), "1");
    const saved = await get(`/alerts/${alert.id}`);
    assert.equal(saved.status, "resolved");
    assert.equal(saved.resolved_by, "10000000-0000-0000-0000-000000000002");
    assert.equal(saved.events.filter(e => e.event_type === "escalated").length, 1);
    assert.equal(saved.events.filter(e => e.event_type === "resolved").length, 1);
    await page.screenshot({ path: "m5-browser-evidence.png", fullPage: true });
    console.log("Passed browser primary timeout → backup acknowledgement → recovery → resolution; lost-response replay and literal history note.");

    reading(1, 88, 2);
    const pending = (await get("/alerts")).items.find(a => a.kind === "risk" && a.status === "open");
    compose("stop", "app");
    // Set only this isolated fixture's saved deadline overdue while the app is stopped.
    sql(`UPDATE alerts SET escalation_due_at=now()-interval '1 second' WHERE id='${pending.id}'`);
    compose("up", "-d", "--wait", "app");
    base = "http://" + compose("port", "app", "8000").trim();
    let restarted = await get(`/alerts/${pending.id}`);
    assert.equal(restarted.assignee_id, "10000000-0000-0000-0000-000000000002");
    assert.equal(restarted.events.filter(e => e.event_type === "escalated").length, 1);
    compose("restart", "app");
    compose("up", "-d", "--wait", "app");
    base = "http://" + compose("port", "app", "8000").trim();
    restarted = await get(`/alerts/${pending.id}`);
    assert.equal(restarted.events.filter(e => e.event_type === "escalated").length, 1);
    assert.deepEqual(await get(`/alerts/${alert.id}`), saved);
    assert.deepEqual(errors, []);
    console.log("Passed real stop/start overdue recovery, second restart without duplicate escalation, and durable resolved state/history.");
  } finally {
    if (browser) await browser.close();
    compose("down");
    console.log(`Stopped ${project}; retained PostgreSQL evidence volume.`);
  }
}
main().catch(error => { console.error(error); process.exitCode = 1; });
