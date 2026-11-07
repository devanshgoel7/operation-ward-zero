// Run on an isolated M3/M4 project with three populated cards and fresh simulator data.
const assert = require("node:assert/strict");
const { execFileSync } = require("node:child_process");
const { chromium } = require("playwright");

async function main() {
  const project = process.argv[2];
  if (!/^wardzero-m[34]-[a-z0-9-]+$/.test(project ?? "")) throw new Error("Supply an isolated M3/M4 test project.");
  const compose = (...args) => execFileSync("docker", ["compose", "-p", project, ...args], { encoding: "utf8" });
  const base = "http://" + compose("port", "app", "8000").trim();
  const browser = await chromium.launch({ channel: "msedge", headless: true });
  try {
    const context = await browser.newContext();
    const page = await context.newPage();
    await page.goto(base);
    await page.locator(".patients article[data-reading-id]").nth(2).waitFor();
    const card = page.locator(".patients article").first();
    // A previous run may still have a recovering gap. Start from three live monitors.
    await page.waitForFunction(() => document.querySelectorAll(".patients article strong").length === 3 &&
      [...document.querySelectorAll(".patients article strong")].every(el => el.textContent === "fresh"));
    const initial = await (await fetch(base + "/api/v1/dashboard")).json();
    if (initial.active_alerts.some(a => a.kind === "monitoring_gap")) throw new Error("Wait for three complete recovery frames before running this fixture.");
    compose("stop", "simulator");
    await context.setOffline(true);
    await card.getByText("Refresh unavailable").waitFor({ timeout: 20000 });
    // Wait for the actual worker to persist a gap while this browser is disconnected.
    let snapshot;
    const deadline = Date.now() + 60000;
    do {
      snapshot = await (await fetch(base + "/api/v1/dashboard")).json();
      if (snapshot.active_alerts.some(a => a.kind === "monitoring_gap")) break;
      await new Promise(resolve => setTimeout(resolve, 1000));
    } while (Date.now() < deadline);
    assert.ok(snapshot.active_alerts.some(a => a.kind === "monitoring_gap"));
    await context.setOffline(false);
    await card.getByText("stale", { exact: true }).waitFor();
    await card.getByText(/Last known concern/).waitFor();
    await page.getByText("Monitoring gap", { exact: true }).first().waitFor();
    const fixture = `
import os, time, uuid, json
from datetime import UTC, datetime, timedelta
from urllib.request import Request, urlopen
for age, oxygen in [(60, 87), (12, 88)]:
    payload = dict(reading_id=str(uuid.uuid4()), device_id="30000000-0000-0000-0000-000000000001",
                   sequence=time.time_ns(), observed_at=(datetime.now(UTC)-timedelta(seconds=age)).isoformat(),
                   heart_rate_bpm=75, spo2_pct=oxygen, systolic_mmhg=119, diastolic_mmhg=79, temperature_c=None)
    req = Request("http://localhost:8000/api/v1/readings", data=json.dumps(payload).encode(),
                  headers={"Content-Type":"application/json","X-Simulator-Key":os.environ["SIMULATOR_KEY"]})
    with urlopen(req) as response:
        assert response.status == 201
`;
    execFileSync("docker", ["compose", "-p", project, "exec", "-T", "app", "python", "-"], { input: fixture });
    await card.getByText(/Delayed delivery/).waitFor();
    await card.getByText("Incomplete reading").waitFor();
    await card.getByText("high concern").waitFor();
    async function verifyReview() {
      const saved = await (await fetch(base + "/api/v1/dashboard")).json();
      const review = saved.active_alerts.find(a => a.kind === "delayed_review" && a.patient_id === saved.patients[0].patient.id);
      assert.ok(review);
      await page.getByLabel("Demo caregiver").selectOption(review.assignee_id);
      const episode = page.locator(".episode").filter({ hasText: "Delayed review" }).filter({ hasText: saved.patients[0].patient.display_name });
      await episode.getByText(new RegExp(review.latest_assessment.reading_id)).waitFor();
    }
    await verifyReview();
    await page.reload();
    await verifyReview();
    console.log("Rendered stale and last-known values, recovered the saved gap after reconnect, and displayed an incomplete high, delivery delay and historical review.");
  } finally {
    try { compose("start", "simulator"); } finally { await browser.close(); }
  }
}
main().catch(error => { console.error(error); process.exitCode = 1; });
