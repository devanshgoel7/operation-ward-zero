// Isolated M4 browser acceptance, including a committed response lost to the browser.
const assert = require("node:assert/strict");
const { execFileSync } = require("node:child_process");
const { chromium } = require("playwright");

async function main() {
  const project = `wardzero-m4-ui-${Date.now()}`;
  const compose = (...args) => execFileSync("docker", ["compose", "-p", project, ...args], {
    encoding: "utf8", env: { ...process.env, APP_PORT: "0" }, stdio: ["pipe", "pipe", "pipe"],
  });
  const runPython = source => execFileSync("docker", ["compose", "-p", project, "exec", "-T", "app", "python", "-"],
    { input: source, encoding: "utf8" });
  let browser;
  console.log(`M4 browser project: ${project}`);
  try {
    compose("up", "-d", "--build", "--wait", "app");
    let base = "http://" + compose("port", "app", "8000").trim();
    browser = await chromium.launch({ channel: "msedge", headless: true });
    const page = await browser.newPage();
    const errors = [];
    page.on("pageerror", error => errors.push(error.message));
    runPython(`
import json, os, time, uuid
from datetime import UTC, datetime, timedelta
from urllib.request import Request, urlopen
end=datetime.now(UTC)-timedelta(seconds=1)
for i in range(24):
    payload=dict(reading_id=str(uuid.uuid4()),device_id="30000000-0000-0000-0000-000000000001",
        sequence=i+1,observed_at=(end-timedelta(seconds=115-5*i)).isoformat(),
        heart_rate_bpm=70 if i<12 else 90,spo2_pct=99 if i<12 else 96,
        systolic_mmhg=119,diastolic_mmhg=79,temperature_c=36.7)
    request=Request("http://localhost:8000/api/v1/readings",data=json.dumps(payload).encode(),
        headers={"Content-Type":"application/json","X-Simulator-Key":os.environ["SIMULATOR_KEY"]})
    with urlopen(request) as response: assert response.status==201
`);
    await page.goto(base);
    const panel = page.getByRole("region", { name: "History and observations" });
    await panel.getByText(/change -3 percentage points/).waitFor();
    await panel.getByText(/change \+20 bpm/).waitFor();
    await panel.getByText(/24 stored readings/).waitFor();
    assert.equal(await page.locator(".history-chart .recharts-line-curve").count(), 1);
    const chartBounds = await page.locator(".history-chart .recharts-surface").boundingBox();
    assert.ok(chartBounds && chartBounds.width > 300 && chartBounds.height >= 200, "Chart must render at a readable size");
    await panel.getByLabel("Chart metric").selectOption("heart_rate_bpm");
    await panel.getByRole("img", { name: "Heart rate history from stored readings" }).waitFor();
    await panel.getByLabel(/Optional note/).fill("Synthetic M4 browser demonstration");
    await panel.getByRole("button", { name: "Save observation", exact: true }).click();
    await panel.getByRole("status").getByText("Observation saved.").waitFor();
    let snapshot = (await (await fetch(base + "/api/v1/dashboard")).json()).patients[0];
    assert.equal(snapshot.current_assessment.concern, "high");
    const first = snapshot.active_observations[0];
    await panel.getByText(new RegExp(first.observation_id)).first().waitFor();
    await page.locator(".patients article").first().getByText("high concern").waitFor();
    const evidence = snapshot.current_assessment.findings.find(f => f.rule_id === "breathlessness.spo2.high");
    assert.equal(evidence.evidence.length, 24);
    await page.screenshot({ path: "m4-browser-evidence.png", fullPage: true });

    // Clearing removes the combination while leaving the falling trend active.
    await panel.getByLabel("Observation state").selectOption("false");
    await panel.getByRole("button", { name: "Save observation", exact: true }).click();
    await panel.getByText("No active structured observations.").waitFor();
    snapshot = (await (await fetch(base + "/api/v1/dashboard")).json()).patients[0];
    assert.equal(snapshot.current_assessment.concern, "watch");

    // The server commits, but the response is dropped. Reload and retry the same UUID.
    await page.getByLabel("Demo caregiver").selectOption("10000000-0000-0000-0000-000000000002");
    await panel.getByLabel("Observation tag").selectOption("dizziness");
    await panel.getByLabel(/Optional note/).fill("<b>Literal caregiver note</b>");
    let lostId;
    await page.route("**/observations", async route => {
      lostId = route.request().postDataJSON().observation_id;
      const response = await route.fetch();
      assert.equal(response.status(), 201);
      await route.abort("failed");
    }, { times: 1 });
    await panel.getByRole("button", { name: "Save observation", exact: true }).click();
    await panel.getByRole("alert").getByText(/Draft retained/).waitFor();
    await page.reload();
    await page.getByLabel("Demo caregiver").selectOption("10000000-0000-0000-0000-000000000002");
    await panel.getByRole("button", { name: "Retry saved observation" }).click();
    await panel.getByText("Observation saved.").waitFor();
    await panel.getByText("Note: <b>Literal caregiver note</b>", { exact: true }).waitFor();
    assert.equal(await panel.locator("b").filter({ hasText: "Literal caregiver note" }).count(), 0);
    const count = compose("exec", "-T", "db", "psql", "-U", "wardzero", "-Atc",
      `SELECT count(*) FROM observations WHERE id='${lostId}'`);
    assert.equal(count.trim(), "1");

    // Make expiry overdue while the real app is stopped; startup must process once.
    compose("stop", "app");
    compose("exec", "-T", "db", "psql", "-v", "ON_ERROR_STOP=1", "-U", "wardzero", "-c",
      "UPDATE observations SET created_at=created_at-interval '11 minutes',expires_at=expires_at-interval '11 minutes'; UPDATE patients SET context_expires_at=now()-interval '1 second' WHERE context_expires_at IS NOT NULL;");
    compose("up", "-d", "--wait", "app");
    base = "http://" + compose("port", "app", "8000").trim();
    await page.goto(base);
    await panel.getByText("No active structured observations.").waitFor();
    const after = (await (await fetch(base + "/api/v1/dashboard")).json()).patients[0];
    assert.equal(after.current_assessment.trigger_kind, "observation_expiry");
    assert.ok(!after.current_assessment.findings.some(f => f.observations.length));
    assert.equal(compose("exec", "-T", "db", "psql", "-U", "wardzero", "-Atc",
      "SELECT count(*) FROM assessments WHERE trigger_kind='observation_expiry'").trim(), "1");
    assert.deepEqual(errors, []);
    console.log("Passed: both trends, stored chart, combination High, clearing, actor attribution, literal notes, lost-response retry, and real restart expiry.");
  } finally {
    if (browser) await browser.close();
    compose("down");
    console.log(`Stopped ${project}; retained its PostgreSQL evidence volume.`);
  }
}
main().catch(error => { console.error(error); process.exitCode = 1; });
