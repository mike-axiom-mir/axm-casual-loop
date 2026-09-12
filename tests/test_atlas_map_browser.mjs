import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { chromium } from "playwright-core";

const root = path.resolve(import.meta.dirname, "..");
const evidenceDir = path.join(root, "artifacts", "causal-atlas-map");
fs.mkdirSync(evidenceDir, { recursive: true });
const atlasPath = path.join(evidenceDir, "atlas.json");
const mapPath = path.join(evidenceDir, "atlas-map.html");
const executablePath = process.env.CHROME;
assert.ok(executablePath, "CHROME must point to installed Chromium/Chrome");

function run(command, args) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, { cwd: root, stdio: ["ignore", "pipe", "pipe"] });
    let stdout = "", stderr = "";
    child.stdout.on("data", chunk => stdout += chunk);
    child.stderr.on("data", chunk => stderr += chunk);
    child.on("error", reject);
    child.on("close", code => code === 0 ? resolve({ stdout, stderr }) : reject(new Error(`${command} exited ${code}\n${stderr}`)));
  });
}

await run("python", ["scripts/generate_atlas.py", "--output", atlasPath]);
await run("python", ["scripts/build_atlas_map.py", atlasPath, "--output", mapPath]);
const atlas = JSON.parse(fs.readFileSync(atlasPath, "utf8"));

const browser = await chromium.launch({ executablePath, headless: true });
const receipt = {
  schema: "axm.causal-loop.atlas-map-browser-evidence/v0.01",
  authority: "VISUAL_OBSERVATION_ONLY",
  atlasHash: atlas.atlasHash,
  desktop: {},
  phone: {},
};

async function exercise(context) {
  const page = await context.newPage();
  const errors = { page: [], console: [], requests: [] };
  page.on("pageerror", error => errors.page.push(error.message));
  page.on("console", message => { if (message.type() === "error") errors.console.push(message.text()); });
  page.on("requestfailed", request => errors.requests.push(`${request.url()} :: ${request.failure()?.errorText || "failed"}`));
  await page.goto(`file://${mapPath}`, { waitUntil: "load" });
  await page.waitForFunction(() => document.querySelectorAll(".case").length > 0);
  return { page, errors };
}

try {
  const desktopContext = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  const desktop = await exercise(desktopContext);
  assert.equal(await desktop.page.locator("#caseCount").innerText(), String(atlas.summary.caseCount));
  assert.equal(await desktop.page.locator("#pathCount").innerText(), String(atlas.summary.uniqueRealizedPathCount));
  assert.equal(await desktop.page.locator("#endpointCount").innerText(), String(atlas.summary.uniqueEndStateCount));
  assert.equal(await desktop.page.locator("#failureCount").innerText(), String(atlas.summary.failedCount));
  assert.equal(await desktop.page.locator("#atlasHash").innerText(), atlas.atlasHash);
  assert.equal(await desktop.page.locator(".endpoint").count(), atlas.summary.uniqueEndStateCount);

  await desktop.page.locator("#search").fill("BLOCK_DOOR");
  const narrowed = await desktop.page.locator(".case").count();
  assert.ok(narrowed > 0 && narrowed < atlas.summary.caseCount, `search did not narrow: ${narrowed}`);
  await desktop.page.locator("#search").fill("");
  await desktop.page.locator("#shape").selectOption("single");
  const singles = await desktop.page.locator(".case").count();
  assert.ok(singles > 0, "expected single-action cases");
  await desktop.page.locator(".case").nth(2).click();
  const selected = await desktop.page.locator("#selectedTitle").innerText();
  assert.match(selected, /^single:/);
  await desktop.page.locator("#compareSibling").click();
  const comparison = await desktop.page.locator("#compareBox").innerText();
  assert.match(comparison, /realized path/);
  assert.match(comparison, /endpoint/);

  await desktop.page.screenshot({ path: path.join(evidenceDir, "atlas-map-desktop.png"), fullPage: true });
  const desktopMetrics = await desktop.page.evaluate(() => ({
    clientWidth: document.documentElement.clientWidth,
    scrollWidth: document.documentElement.scrollWidth,
  }));
  assert.ok(desktopMetrics.scrollWidth <= desktopMetrics.clientWidth);
  assert.deepEqual(desktop.errors, { page: [], console: [], requests: [] });
  receipt.desktop = {
    visibleSingleCases: singles,
    selectedCase: selected,
    comparison,
    horizontalOverflowPx: Math.max(0, desktopMetrics.scrollWidth - desktopMetrics.clientWidth),
    ...desktop.errors,
  };
  await desktopContext.close();

  const phoneContext = await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
  const phone = await exercise(phoneContext);
  await phone.page.locator("#shape").selectOption("pair-repeat");
  const phoneCases = await phone.page.locator(".case").count();
  assert.ok(phoneCases > 0);
  await phone.page.locator(".case").first().click();
  await phone.page.locator("#compareSibling").click();
  const phoneMetrics = await phone.page.evaluate(() => ({
    clientWidth: document.documentElement.clientWidth,
    scrollWidth: document.documentElement.scrollWidth,
    minControlHeight: Math.min(...Array.from(document.querySelectorAll("button,input,select")).map(el => el.getBoundingClientRect().height)),
  }));
  assert.ok(phoneMetrics.scrollWidth <= phoneMetrics.clientWidth, `phone overflow ${phoneMetrics.scrollWidth} > ${phoneMetrics.clientWidth}`);
  assert.ok(phoneMetrics.minControlHeight >= 44, `control below 44px: ${phoneMetrics.minControlHeight}`);
  await phone.page.screenshot({ path: path.join(evidenceDir, "atlas-map-phone.png"), fullPage: false });
  assert.deepEqual(phone.errors, { page: [], console: [], requests: [] });
  receipt.phone = {
    viewport: "390x844",
    visibleRepeatedCases: phoneCases,
    horizontalOverflowPx: Math.max(0, phoneMetrics.scrollWidth - phoneMetrics.clientWidth),
    minControlHeightPx: phoneMetrics.minControlHeight,
    ...phone.errors,
  };
  await phoneContext.close();
} finally {
  await browser.close();
}

fs.writeFileSync(path.join(evidenceDir, "browser-receipt.json"), JSON.stringify(receipt, null, 2) + "\n");
console.log(JSON.stringify(receipt, null, 2));
