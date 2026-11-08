// Read-only browser verification against a running Compose stack with simulator readings.
const assert = require("node:assert/strict");
const path = require("node:path");
const { chromium } = require("playwright");

const base = process.argv[2] ?? "http://127.0.0.1:8010";
const evidenceDir = process.argv[3];

async function main() {
  const browser = await chromium.launch({ channel: "msedge", headless: true });
  try {
    for (const width of [1440, 1024, 768, 375]) {
      const page = await browser.newPage({ viewport: { width, height: 900 }, reducedMotion: "reduce" });
      const errors = [];
      page.on("pageerror", error => errors.push(error.message));
      const snapshotResponse = page.waitForResponse(response =>
        response.url().endsWith("/api/v1/dashboard") && response.ok());
      await page.goto(base);
      const snapshot = await (await snapshotResponse).json();
      const roster = page.getByRole("region", { name: "Patient roster" });
      const vitals = page.getByRole("region", { name: "Vital signs overview" });
      const quality = page.getByRole("region", { name: "Reading quality" });
      await page.getByText("Live updates connected", { exact: true }).waitFor();
      await page.getByText("Service ready", { exact: true }).waitFor();
      const cards = roster.locator("article[data-reading-id]");
      await cards.nth(snapshot.patients.length - 1).waitFor();
      assert.equal(await cards.count(), snapshot.patients.length);
      const firstRisk = cards.first().locator(".assessment-risk");
      await firstRisk.getByText(/^(No|Low|Medium|High|Unknown) risk$/).waitFor();
      const reason = firstRisk.locator(".assessment-risk-reason");
      await reason.waitFor();
      assert.ok((await reason.textContent()).trim(), `Risk reason at ${width}px`);

      const chart = vitals.locator(".recharts-surface");
      await chart.waitFor();
      const chartBounds = await chart.boundingBox();
      assert.ok(chartBounds.width >= 260 && chartBounds.height >= 200, `Vital chart at ${width}px`);
      await quality.locator(".recharts-pie-sector").first().waitFor();
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true, `Overflow at ${width}px`);
      console.log(`${width}px viewport: vital chart ${Math.round(chartBounds.width)}×${Math.round(chartBounds.height)}, donut visible, no page overflow`);

      if (evidenceDir && (width === 1440 || width === 375)) {
        await page.screenshot({ path: path.join(evidenceDir, `wardzero-dashboard-${width}.png`), fullPage: true });
      }

      await page.keyboard.press("Tab");
      assert.equal(await page.locator(":focus").textContent(), "Skip to patient monitoring");
      await page.keyboard.press("Enter");
      await page.waitForFunction(() => document.activeElement?.id === "monitoring");
      const navigation = page.getByRole("navigation", { name: "Dashboard navigation" });
      const menu = page.getByRole("button", { name: "Open navigation" });
      if (width <= 1000) {
        await menu.press("Enter");
        assert.equal(await page.getByRole("button", { name: "Close navigation" }).getAttribute("aria-expanded"), "true");
      }
      const targets = [
        ["Overview", "monitoring"], ["Patients", "patients"], ["Vital signs", "vital-signs"],
        ["History and observations", "patient-context"], ["Caregiver inbox", "caregiver-inbox"], ["System health", "system-health"],
      ];
      const waitForActive = id => page.locator(`#dashboard-navigation [href="#${id}"][aria-current="location"]`).waitFor({ state: "attached" });
      for (const [label, id] of width <= 1000 ? [targets[1]] : targets) {
        const link = navigation.getByRole("link", { name: label, exact: true });
        await link.press("Enter");
        await page.waitForFunction(target => location.hash === `#${target}` && document.activeElement?.id === target, id);
        await waitForActive(id);
      }
      if (width <= 1000) assert.equal(await menu.getAttribute("aria-expanded"), "false");

      if (width === 1440 || width === 375) {
        const start = await page.evaluate(() => ({ hash: location.hash, focus: document.activeElement?.id }));
        const visited = await page.evaluate(async () => {
          const active = [];
          const end = document.documentElement.scrollHeight - innerHeight;
          for (let position = 0; position < end + 40; position += 40) {
            window.scrollTo(0, Math.min(position, end));
            await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
            const href = document.querySelector('#dashboard-navigation [aria-current="location"]')?.getAttribute("href");
            if (href && active.at(-1) !== href) active.push(href);
          }
          return active;
        });
        assert.deepEqual(visited, targets.map(([, id]) => `#${id}`));
        assert.deepEqual(await page.evaluate(() => ({ hash: location.hash, focus: document.activeElement?.id })), start);
        await page.evaluate(() => window.scrollTo(0, 0));
        await waitForActive("monitoring");
        if (width === 1440) {
          await navigation.getByRole("link", { name: "System health" }).press("Enter");
          await waitForActive("system-health");
        }
        console.log(`${width}px viewport: sidebar followed scrolling through all sections and back to Overview`);
      }

      const context = page.getByRole("region", { name: "History and observations" });
      const vitalPicker = vitals.getByLabel("Selected patient");
      const contextPicker = context.getByLabel("Selected patient");
      const review = patient => page.getByRole("button", { name: `Review patient ${patient.display_name}`, exact: true });
      if (width === 1440 || width === 375) {
        const first = snapshot.patients[0].patient;
        const last = snapshot.patients.at(-1).patient;
        assert.equal(await review(first).getAttribute("aria-current"), "true");
        if (width === 1440) await review(last).press("Enter");
        else await review(last).click();
        await page.waitForFunction(() => location.hash === "#vital-signs" && document.activeElement?.id === "vital-signs");
        assert.equal(await review(last).getAttribute("aria-current"), "true");
        assert.equal(await review(first).getAttribute("aria-current"), null);
        const selectedRow = cards.filter({ has: review(last) });
        await selectedRow.getByText("Selected patient", { exact: true }).waitFor();
        assert.equal(await vitalPicker.inputValue(), last.id);
        assert.equal(await contextPicker.inputValue(), last.id);

        const form = context.getByRole("form", { name: "Record observation" });
        await vitals.getByRole("link", { name: "Record observation" }).press("Enter");
        await page.waitForFunction(() => location.hash === "#record-observation" && document.activeElement?.id === "record-observation");
        await waitForActive("patient-context");
        await form.getByText(last.display_name, { exact: true }).waitFor();
        const caregiver = snapshot.caregivers[0];
        await form.getByText(caregiver.display_name, { exact: true }).waitFor();

        await contextPicker.selectOption(first.id);
        assert.equal(await vitalPicker.inputValue(), first.id);
        assert.equal(await review(first).getAttribute("aria-current"), "true");
        await form.getByText(first.display_name, { exact: true }).waitFor();
        await vitalPicker.selectOption(last.id);
        assert.equal(await contextPicker.inputValue(), last.id);
        await page.reload();
        await form.getByText(last.display_name, { exact: true }).waitFor();
        assert.equal(await vitalPicker.inputValue(), last.id);
        assert.equal(await review(last).getAttribute("aria-current"), "true");
        console.log(`${width}px viewport: selected row, shared selectors, observation target and reload persistence verified`);
      }

      if (width === 1440) {
        const metric = label => page.getByRole("article", { name: label }).locator(".metric-value");
        const caregiver = page.getByLabel("Demo caregiver");
        const actor = snapshot.caregivers.at(-1).id;
        await caregiver.selectOption(actor);
        const refreshResponse = page.waitForResponse(response =>
          response.url().endsWith("/api/v1/dashboard") && response.ok());
        await page.getByRole("button", { name: "Refresh now" }).click();
        const current = await (await refreshResponse).json();
        const counts = {
          "Monitored patients": current.patients.length,
          "Fresh readings": current.patients.filter(patient => patient.data_quality === "fresh").length,
          "Active alerts": current.active_alerts.length,
          "Assigned alerts": current.active_alerts.filter(alert => alert.assignee_id === actor).length,
        };
        for (const [label, value] of Object.entries(counts)) {
          await page.getByRole("article", { name: label }).getByText(String(value), { exact: true }).waitFor();
        }
        for (const label of ["Fresh", "Incomplete", "Stale", "Unavailable"]) {
          const count = current.patients.filter(patient => patient.data_quality === label.toLowerCase()).length;
          const legendEntry = quality.getByRole("listitem").filter({ hasText: label });
          await legendEntry.getByText(String(count), { exact: true }).waitFor();
        }

        const patient = current.patients.at(-1).patient;
        const search = page.getByRole("searchbox", { name: "Search patients" });
        await search.fill("no such patient");
        await roster.getByText("No patients match your search.").waitFor();
        assert.equal(await metric("Monitored patients").textContent(), String(counts["Monitored patients"]));
        await search.fill(` ${patient.display_name.toUpperCase()} `);
        await search.press("Enter");
        await roster.getByText(`1 of ${counts["Monitored patients"]} patients`).waitFor();
        await page.waitForFunction(() => document.activeElement?.id === "patients");
        const card = cards.first();
        const { id, heartRate } = await card.evaluate(row => ({
          id: row.dataset.readingId,
          heartRate: row.querySelector("dd").textContent,
        }));
        const historyResponse = await page.request.get(`${base}/api/v1/patients/${patient.id}/readings?limit=2000`);
        assert.ok(historyResponse.ok());
        const stored = (await historyResponse.json()).items.find(reading => reading.reading_id === id);
        assert.ok(stored, "Rendered reading ID is in the patient's REST history");
        assert.equal(heartRate, `${stored.heart_rate_bpm ?? "—"} bpm`);
        await review(patient).click();
        await page.waitForURL("**/#vital-signs");
        assert.equal(await vitalPicker.inputValue(), patient.id);
        assert.equal(await contextPicker.inputValue(), patient.id);
        await page.getByRole("button", { name: "Clear patient search" }).click();
        assert.equal(await search.inputValue(), "");
        assert.equal(await search.evaluate(input => input === document.activeElement), true);
        assert.equal(await cards.count(), counts["Monitored patients"]);
        console.log(`Matched REST counters, reading quality and a stored vital; verified search and shared patient selection (${counts["Active alerts"]} active alerts).`);
      }
      assert.deepEqual(errors, []);
      await page.close();
    }
  } finally {
    await browser.close();
  }
}

main().catch(error => { console.error(error); process.exitCode = 1; });
