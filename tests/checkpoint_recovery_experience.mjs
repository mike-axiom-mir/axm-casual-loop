import { spawn, execFileSync } from 'node:child_process';
import fs from 'node:fs';
import net from 'node:net';
import os from 'node:os';
import path from 'node:path';
import process from 'node:process';
import { chromium } from 'playwright';

const evidenceDir = process.env.AXM_EVIDENCE_DIR || '/tmp/axm-causal-loop-recovery-evidence';
fs.mkdirSync(evidenceDir, { recursive: true });
const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'axm-causal-recovery-'));
const store = path.join(tempRoot, 'store');

const seed = `
import sys
from pathlib import Path
from causal_loop import TimedInfluence
from causal_loop.checkpoint_store import LocalCheckpointStore
from causal_loop.train_platform import build_engine, initial_state
engine=build_engine()
schedule=[TimedInfluence(2,"BLOCK_DOOR"),TimedInfluence(3,"TRIGGER_ALARM")]
store=LocalCheckpointStore(sys.argv[1])
for waves in (1,2):
    store.save(engine.pause(initial_state(),timed_influences=schedule,after_waves=waves))
held="0"*64
(Path(sys.argv[1])/f"{held}.json").write_text("{}",encoding="utf-8")
`;
execFileSync('python', ['-c', seed, store], { stdio: 'inherit' });

async function freePort() {
  return await new Promise((resolve, reject) => {
    const server = net.createServer();
    server.on('error', reject);
    server.listen(0, '127.0.0.1', () => {
      const { port } = server.address();
      server.close(() => resolve(port));
    });
  });
}
async function waitFor(url) {
  for (let i=0;i<80;i++) {
    try {
      const response = await fetch(url);
      if (response.ok) return;
    } catch {}
    await new Promise(r => setTimeout(r, 125));
  }
  throw new Error(`server did not become ready: ${url}`);
}
function assert(condition, message) {
  if (!condition) throw new Error(message);
}

const port = await freePort();
const origin = `http://127.0.0.1:${port}`;
const server = spawn('python', ['-m', 'tools.checkpoint_recovery_station', '--store', store, '--port', String(port)], {
  stdio: ['ignore', 'pipe', 'pipe']
});
let serverErr = '';
server.stderr.on('data', chunk => { serverErr += chunk.toString(); });

let browser;
try {
  await waitFor(`${origin}/api/inventory`);
  browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: 390, height: 844 },
    permissions: ['clipboard-read', 'clipboard-write']
  });
  const page = await context.newPage();
  const pageErrors = [];
  const consoleErrors = [];
  const foreignRequests = [];
  page.on('pageerror', error => pageErrors.push(String(error)));
  page.on('console', message => { if (message.type() === 'error') consoleErrors.push(message.text()); });
  page.on('request', request => { if (!request.url().startsWith(origin)) foreignRequests.push(request.url()); });

  await page.goto(origin, { waitUntil: 'networkidle' });
  await page.waitForFunction(() => document.querySelector('#candidateCount')?.textContent === '2');
  assert(await page.locator('.candidate').count() === 2, 'expected two verified checkpoint candidates');
  assert(await page.locator('#heldCount').textContent() === '1', 'expected one held checkpoint');
  assert((await page.locator('#planBanner').textContent()).includes('No checkpoint selected'), 'station must not auto-select a checkpoint');

  const initialSet = (await page.locator('#setMeta').textContent()).trim();
  const measurements = await page.evaluate(() => {
    const buttons = [...document.querySelectorAll('button')];
    const heights = buttons.map(button => button.getBoundingClientRect().height);
    return {
      innerWidth: window.innerWidth,
      scrollWidth: document.documentElement.scrollWidth,
      minButtonHeight: Math.min(...heights),
    };
  });
  assert(measurements.scrollWidth === measurements.innerWidth, `mobile horizontal overflow: ${JSON.stringify(measurements)}`);
  assert(measurements.minButtonHeight >= 44, `interactive target below 44px: ${measurements.minButtonHeight}`);

  await page.locator('.candidate .btn.primary').first().click();
  await page.waitForFunction(() => document.querySelector('#planBanner')?.textContent?.includes('Plan ready'));
  const planText = await page.locator('#planPanel').textContent();
  assert(planText.includes('Plan ready · not resumed'), 'plan readiness must explicitly preserve no-resume boundary');
  assert(planText.includes('EXPLICIT_SELECTION_ONLY_NO_AUTOMATIC_SELECTION_NO_RESUME_NO_CANON'), 'authority boundary missing from prepared plan');
  await page.locator('#copyPlan').click();
  const copiedText = await page.evaluate(() => navigator.clipboard.readText());
  const copiedPlan = JSON.parse(copiedText);
  assert(copiedPlan.receipt?.authority === 'EXPLICIT_SELECTION_ONLY_NO_AUTOMATIC_SELECTION_NO_RESUME_NO_CANON', 'copied plan widened authority');
  assert(typeof copiedPlan.receipt?.planHash === 'string' && /^[0-9a-f]{64}$/.test(copiedPlan.receipt.planHash), 'copied plan hash missing');
  assert(!('resumeExecuted' in copiedPlan.receipt), 'prepared plan receipt must not claim resume execution');

  const addThird = `
import sys
from causal_loop import TimedInfluence
from causal_loop.checkpoint_store import LocalCheckpointStore
from causal_loop.train_platform import build_engine, initial_state
engine=build_engine()
schedule=[TimedInfluence(2,"BLOCK_DOOR"),TimedInfluence(3,"TRIGGER_ALARM")]
LocalCheckpointStore(sys.argv[1]).save(engine.pause(initial_state(),timed_influences=schedule,after_waves=3))
`;
  execFileSync('python', ['-c', addThird, store], { stdio: 'inherit' });

  assert(consoleErrors.length === 0, `unexpected console errors before intentional HOLD: ${consoleErrors.join(' | ')}`);
  await page.locator('.candidate .btn.primary').nth(1).click();
  await page.waitForFunction(() => document.querySelector('#planBanner')?.textContent?.includes('Selection held'));
  const holdText = await page.locator('#planPanel').textContent();
  assert(holdText.includes('candidate set changed'), 'stale candidate set must fail closed visibly');
  assert(await page.locator('#candidateCount').textContent() === '3', 'held response should expose refreshed verified candidate count');
  await page.screenshot({ path: path.join(evidenceDir, 'checkpoint-recovery-stale-hold-mobile.png'), fullPage: true });
  const expectedHoldConsoleErrors = consoleErrors.splice(0);
  assert(
    expectedHoldConsoleErrors.every(message => /409|Conflict/i.test(message)),
    `unexpected console output during intentional 409 HOLD: ${expectedHoldConsoleErrors.join(' | ')}`
  );

  await page.locator('#refresh').click();
  await page.waitForFunction(() => document.querySelector('#candidateCount')?.textContent === '3');
  const refreshedSet = (await page.locator('#setMeta').textContent()).trim();
  assert(initialSet !== refreshedSet, 'candidate-set identity should visibly change after store growth');
  await page.locator('.candidate .btn.primary').first().click();
  await page.waitForFunction(() => document.querySelector('#planBanner')?.textContent?.includes('Plan ready'));
  await page.screenshot({ path: path.join(evidenceDir, 'checkpoint-recovery-ready-mobile.png'), fullPage: true });

  await page.setViewportSize({ width: 1280, height: 900 });
  await page.screenshot({ path: path.join(evidenceDir, 'checkpoint-recovery-ready-desktop.png'), fullPage: true });
  const desktop = await page.evaluate(() => ({
    innerWidth: window.innerWidth,
    scrollWidth: document.documentElement.scrollWidth,
    panelCount: document.querySelectorAll('.panel').length,
  }));
  assert(desktop.scrollWidth === desktop.innerWidth, `desktop horizontal overflow: ${JSON.stringify(desktop)}`);
  assert(desktop.panelCount === 2, 'expected inventory and handoff panels');

  assert(pageErrors.length === 0, `page errors: ${pageErrors.join(' | ')}`);
  assert(consoleErrors.length === 0, `console errors: ${consoleErrors.join(' | ')}`);
  assert(foreignRequests.length === 0, `unexpected non-local requests: ${foreignRequests.join(' | ')}`);

  const receipt = {
    schema: 'axm.causal-loop.checkpoint-recovery-experience-evidence/v0.01',
    viewport: { mobile: [390, 844], desktop: [1280, 900] },
    verifiedCandidateCountBefore: 2,
    heldCandidateCountBefore: 1,
    verifiedCandidateCountAfter: 3,
    mobileHorizontalOverflowPx: measurements.scrollWidth - measurements.innerWidth,
    minimumButtonHeightPx: measurements.minButtonHeight,
    desktopHorizontalOverflowPx: desktop.scrollWidth - desktop.innerWidth,
    explicitPlanPrepared: true,
    copiedPlanAuthority: copiedPlan.receipt.authority,
    staleCandidateSetHeld: true,
    pageErrors,
    expectedHoldConsoleErrors,
    unexpectedConsoleErrors: consoleErrors,
    foreignRequests,
    resumeExecutedByStation: false,
  };
  fs.writeFileSync(path.join(evidenceDir, 'browser-receipt.json'), JSON.stringify(receipt, null, 2) + '\n');
  console.log(JSON.stringify(receipt));
  await context.close();
} finally {
  if (browser) await browser.close();
  server.kill('SIGTERM');
  await new Promise(resolve => {
    if (server.exitCode !== null) return resolve();
    const timeout = setTimeout(() => { server.kill('SIGKILL'); resolve(); }, 1500);
    server.once('exit', () => { clearTimeout(timeout); resolve(); });
  });
  fs.rmSync(tempRoot, { recursive: true, force: true });
  if (serverErr.trim()) process.stderr.write(serverErr);
}
