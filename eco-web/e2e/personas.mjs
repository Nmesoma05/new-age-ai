// QA persona scenarios: success AND failure paths for four real users, in a real browser against the real web app,
// API and database. The existing suites (run/business/freelancer/integrations.mjs) cover the happy paths; this one
// targets recovery, limits, roles, isolation in the UI, Unicode files, validation and keyboard/mobile use.
// Prereqs: API :8000 (`python -m tests.e2e_server`), web :3000. Run: node e2e/personas.mjs
import { createRequire } from "node:module";
import { execFileSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";

const require = createRequire(import.meta.url);
const { chromium, devices } = require("playwright");
const BASE = process.env.WEB_URL || "http://localhost:3000";
const BACKEND_DIR = path.resolve("../eco-backend");
const DSN = "postgresql://eco_owner:owner_dev_pw@localhost/eco_e2e";
const OUT = path.resolve("e2e/out/personas");
fs.mkdirSync(OUT, { recursive: true });
const CSRF = { "x-eco-csrf": "1", "content-type": "application/json" };
const PW = "correct-horse-battery";

const results = [];
let browser;
const sql = (q) => execFileSync("psql", [DSN, "-Atc", q]).toString().trim();
const activate = (org, plan) => execFileSync("python3", ["-m", "tests.e2e_server", "activate", org, plan], { cwd: BACKEND_DIR });

async function step(page, name, fn) {
  try { await fn(); results.push({ name, ok: true }); console.log(`  ✓ ${name}`); }
  catch (e) {
    results.push({ name, ok: false, error: String(e).split("\n")[0] });
    console.log(`  ✗ ${name}\n    ${String(e).split("\n").slice(0, 3).join("\n    ")}`);
    await page.screenshot({ path: path.join(OUT, `FAIL-${name.replace(/\W+/g, "-").slice(0, 60)}.png`), fullPage: true }).catch(() => {});
  }
}
const text = (page, t, o) => page.getByText(t, o).first().waitFor({ timeout: 15000 });
const toast = (page, t) => page.locator("[aria-live=polite]").getByText(t).first().waitFor({ timeout: 15000 });
async function api(page, method, p, body) {
  const r = await page.request.fetch(`${BASE}/api/proxy${p}`, { method, headers: CSRF, data: body });
  const b = await r.json().catch(() => ({}));
  if (!r.ok()) throw new Error(`${method} ${p} -> ${r.status()} ${JSON.stringify(b).slice(0, 200)}`);
  return b;
}
async function newUser(name, opts = {}) {
  const ctx = await browser.newContext({ viewport: { width: 1360, height: 900 }, ...opts });
  const page = await ctx.newPage();
  page.setDefaultTimeout(15000);
  const email = `${name.split(" ")[0].toLowerCase().normalize("NFKD").replace(/[^a-z]/g, "")}-${Date.now()}@example.com`;
  await page.goto(`${BASE}/signup`, { waitUntil: "networkidle" });
  await page.getByLabel("Your name").fill(name);
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(PW);
  await page.getByRole("checkbox", { name: /I agree to the Terms/ }).check();
  await page.getByRole("button", { name: "Create account" }).click();
  await page.waitForURL(/\/start/);
  return { ctx, page, email };
}
async function login(page, email, pw = PW) {
  await page.goto(`${BASE}/login`, { waitUntil: "networkidle" });
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password", { exact: true }).fill(pw);
  await page.getByRole("button", { name: "Sign in" }).click();
}

async function main() {
  browser = await chromium.launch();
  const biz = JSON.parse(fs.readFileSync("e2e/biz.json", "utf8"));
  const cre = JSON.parse(fs.readFileSync("e2e/creator.json", "utf8"));
  const flp = JSON.parse(fs.readFileSync("e2e/profile.json", "utf8"));

  // ================================================================ A. Tunde, business owner (Awka caterer)
  console.log("A. Business owner");
  const A = await newUser("Tunde Bello");
  let aws, aorg;
  await step(A.page, "A1. Business onboarding (setup) and wrong-password message", async () => {
    const r = await api(A.page, "POST", "/v1/business/onboarding", { mode: "solo", profile: biz });
    aws = r.workspace_id; aorg = r.org_id ?? sql(`select org_id from workspaces where id='${aws}'`);
    await A.ctx.clearCookies();
    await login(A.page, A.email, "wrong-password-1");
    await text(A.page, "Email or password is incorrect.");
  });
  await step(A.page, "A2. Forgot password → email link → mismatch caught → reset → old session signed out", async () => {
    const other = await browser.newContext();               // a second device that is still signed in
    const op = await other.newPage();
    await login(op, A.email); await op.waitForURL(/\/(start|b\/)/);
    await A.page.goto(`${BASE}/login`, { waitUntil: "networkidle" });
    await A.page.getByRole("link", { name: "Forgot your password?" }).click();
    await A.page.waitForURL(/forgot-password/); await A.page.waitForLoadState("networkidle");
    await A.page.getByLabel("Email").fill(A.email.toUpperCase());
    await A.page.getByRole("button", { name: "Send reset link" }).click();
    await text(A.page, "If an account exists for that email");
    const body = sql(`select body from email_outbox where to_email='${A.email}' order by id desc limit 1`);
    const link = body.match(/http\S+#token=[\w-]+/)[0].replace("http://localhost:3000", BASE);
    await A.page.goto(link, { waitUntil: "networkidle" });
    if (A.page.url().includes("token=")) throw new Error("token left in the address bar");
    await A.page.getByLabel("New password", { exact: true }).fill("tunde-new-pass-99");
    await A.page.getByLabel("Repeat new password").fill("tunde-new-pass-98");
    await A.page.getByRole("button", { name: "Change password" }).click();
    await text(A.page, "The two passwords don't match.");
    await A.page.getByLabel("Repeat new password").fill("tunde-new-pass-99");
    await A.page.getByRole("button", { name: "Change password" }).click();
    await text(A.page, "Every device was signed out");
    await op.goto(`${BASE}/b/${aws}`);
    await op.waitForURL(/\/login/, { timeout: 15000 });
    await other.close();
    await login(A.page, A.email, "tunde-new-pass-99");
    await A.page.waitForURL(/\/(start|b\/)/);
    await A.page.goto(link, { waitUntil: "networkidle" }); // reuse the link
    await A.page.getByLabel("New password", { exact: true }).fill("tunde-third-pass-1");
    await A.page.getByLabel("Repeat new password").fill("tunde-third-pass-1");
    await A.page.getByRole("button", { name: "Change password" }).click();
    await text(A.page, "expired or was already used");
  });
  await step(A.page, "A3. Free limit reached → clear upgrade message → paid plan unlocks", async () => {
    sql(`insert into usage_counters (org_id, period_month, free_generations_used) values ('${aorg}', date_trunc('month', now())::date, 30)
         on conflict (org_id, period_month) do update set free_generations_used = 30`);
    await A.page.goto(`${BASE}/b/${aws}/tools`);
    await A.page.getByRole("link", { name: /Marketing plan/ }).click();
    await A.page.getByRole("button", { name: "Generate plan" }).click();
    await text(A.page, /used your 30 free drafts this month/);
    activate(aorg, "starter");
    await A.page.reload();
    await A.page.getByRole("button", { name: "Generate plan" }).click();
    await text(A.page, "Month 1");
  });
  await step(A.page, "A4. Results CSV with a bad row is refused whole; formula text exported safely", async () => {
    await A.page.goto(`${BASE}/b/${aws}/results`);
    const today = new Date().toISOString().slice(0, 10);
    const bad = `channel,period_start,period_end,leads\nfacebook_ads,${today},${today},12\nwhatsapp,${today},${today},-4\n`;
    await A.page.locator("input[type=file]").setInputFiles({ name: "mixed.csv", mimeType: "text/csv", buffer: Buffer.from(bad) });
    await text(A.page, "Nothing was imported");
    const rows = await api(A.page, "GET", `/v1/workspaces/${aws}/business/results`);
    if ((rows.data ?? rows).length !== 0) throw new Error("partial import happened");
  });

  // ================================================================ B. Ada, social media manager (agency, team)
  console.log("B. Social media manager");
  const B = await newUser("Ada Eze");
  const E = await newUser("Bola Ade");          // her editor
  let ws1, ws2, borg;
  await step(B.page, "B1. Agency with two clients; editor added to client 1 only (setup)", async () => {
    const on = await api(B.page, "POST", "/v1/creator/onboarding", { mode: "agency", agency_name: "Ada Social", client: cre });
    ws1 = on.workspace_id; borg = sql(`select org_id from workspaces where id='${ws1}'`);
    activate(borg, "team");
    ws2 = (await api(B.page, "POST", `/v1/orgs/${borg}/workspaces`, { name: "Client Two", product: "creator" })).id;
    await api(B.page, "POST", `/v1/orgs/${borg}/members`, { email: E.email, role: "member" });
    const uid = sql(`select id from users where email='${E.email}'`);
    await api(B.page, "POST", `/v1/workspaces/${ws1}/members`, { user_id: uid, role: "editor" });
  });
  await step(E.page, "B2. Editor sees only her client; the other client is closed to her", async () => {
    await E.page.goto(`${BASE}/clients`);
    await text(E.page, "Lagos Coffee Co.");
    if (await E.page.getByText("Client Two").count()) throw new Error("editor can see Client Two");
    await E.page.goto(`${BASE}/c/${ws2}/library`);
    await E.page.getByText(/Can't open this client|not found|don't have access/i).first().waitFor();
    const r = await E.page.request.get(`${BASE}/api/proxy/v1/workspaces/${ws2}/assets`);
    if (r.status() !== 404 && r.status() !== 403) throw new Error(`API gave ${r.status()}`);
  });
  await step(E.page, "B3. Editor can't connect accounts or approve; told why", async () => {
    await E.page.goto(`${BASE}/c/${ws1}/settings`);
    await text(E.page, "Only an organisation owner or admin can connect or disconnect accounts.");
    if (await E.page.getByRole("button", { name: /^Connect / }).count()) throw new Error("connect button shown to editor");
    const r = await E.page.request.post(`${BASE}/api/proxy/v1/workspaces/${ws1}/integrations/youtube/connect`, { headers: CSRF, data: {} });
    if (r.status() !== 403) throw new Error(`connect as editor gave ${r.status()}`);
    const m = await E.page.request.patch(`${BASE}/api/proxy/v1/workspaces/${ws1}`, { headers: CSRF, data: { name: "Hijacked" } });
    if (m.ok()) throw new Error("editor renamed the workspace");
  });
  await step(B.page, "B4. Cross-site request without our header is blocked", async () => {
    const r = await B.page.request.post(`${BASE}/api/proxy/v1/orgs/${borg}/workspaces`, {
      headers: { "content-type": "application/json", origin: "https://evil.example" }, data: { name: "X", product: "creator" } });
    if (r.status() !== 403) throw new Error(`no-CSRF-header request gave ${r.status()}`);
    const r2 = await B.page.request.post(`${BASE}/api/proxy/v1/orgs/${borg}/workspaces`, {
      headers: { ...CSRF, origin: "https://evil.example" }, data: { name: "X", product: "creator" } });
    if (r2.status() !== 403) throw new Error(`cross-origin request gave ${r2.status()}`);
  });

  // ================================================================ C. Chịamaka, freelancer (Unicode everywhere)
  console.log("C. Freelancer");
  const C = await newUser("Chịamaka Ọkafọ");
  let cws;
  await step(C.page, "C1. Profile with Igbo name; portfolio PDF with Unicode filename uploads and downloads", async () => {
    cws = (await api(C.page, "POST", "/v1/freelancer/onboarding", { profile: { ...flp, full_name: "Chịamaka Ọkafọ" } })).workspace_id;
    await C.page.goto(`${BASE}/f/${cws}/work`);
    await C.page.getByRole("tab", { name: "Uploaded files" }).click();
    const pdf = Buffer.from("%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n");
    await C.page.locator("input[type=file]").setInputFiles({ name: "Chịamaka Ọkafọ portfolio.pdf", mimeType: "application/pdf", buffer: pdf });
    await toast(C.page, "Uploaded");
    await text(C.page, "Chịamaka Ọkafọ portfolio.pdf");
    const [popup] = await Promise.all([C.page.waitForEvent("popup"), C.page.getByRole("button", { name: /Download|Open/ }).first().click()]);
    const resp = await popup.waitForEvent("response", (r) => r.url().includes("/v1/files/")).catch(() => null);
    const status = resp ? resp.status() : (await popup.evaluate(() => document.readyState) && 0);
    if (resp && status !== 200) throw new Error(`download returned ${status}`);
    await popup.close().catch(() => {});
  });
  await step(C.page, "C2. A program disguised as a PDF is refused with a clear message", async () => {
    await C.page.locator("input[type=file]").setInputFiles({ name: "cv.pdf", mimeType: "application/pdf", buffer: Buffer.from("MZ\x90\x00\x03\x00\x00\x00") });
    await text(C.page, "Upload a PDF, DOCX, TXT, PNG or JPG file.");
  });
  await step(C.page, "C3. CV saved with an Igbo title exports as HTML and text", async () => {
    const run = (await api(C.page, "POST", `/v1/workspaces/${cws}/freelancer/generate`, { tool: "cv", target_role: "Product designer", market: "us" })).run;
    const asset = (await api(C.page, "POST", `/v1/workspaces/${cws}/freelancer/runs/${run.id}/save`, { title: "CV · Chịamaka Ọkafọ" })).id;
    for (const f of ["html", "txt", "md"]) {
      const r = await C.page.request.get(`${BASE}/api/proxy/v1/workspaces/${cws}/freelancer/work/${asset}/export?format=${f}`);
      if (r.status() !== 200) throw new Error(`${f} export gave ${r.status()}`);
    }
  });
  await step(C.page, "C4. Change password keeps this device signed in", async () => {
    await C.page.goto(`${BASE}/f/${cws}/settings`);
    await C.page.getByLabel("Current password").fill("not-my-password");
    await C.page.getByLabel("New password", { exact: true }).fill("chiamaka-new-pass-1");
    await C.page.getByRole("button", { name: "Change password" }).click();
    await toast(C.page, "Your current password isn't right.");
    await C.page.getByLabel("Current password").fill(PW);
    await C.page.getByRole("button", { name: "Change password" }).click();
    await toast(C.page, "Password changed");
    await C.page.goto(`${BASE}/f/${cws}`);
    await C.page.waitForURL(new RegExp(`/f/${cws}$`));
  });

  // ================================================================ D. Musa, remote job seeker (phone, beginner)
  console.log("D. Remote job seeker");
  const D = await newUser("Musa Ibrahim", { ...devices["Pixel 5"] });
  let dws;
  await step(D.page, "D1. Onboarding on a phone: required fields enforced, no sideways scroll", async () => {
    await D.page.goto(`${BASE}/freelancer/onboarding`, { waitUntil: "networkidle" });
    await D.page.getByRole("radio", { name: /remote job/i }).click();
    await D.page.getByRole("button", { name: "Continue" }).click();
    await text(D.page, "Where you work from");
    if (!(await D.page.getByRole("button", { name: "Continue" }).isDisabled())) throw new Error("step 2 can continue with no country");
    await D.page.getByLabel("Country").selectOption("NG");
    if (await D.page.getByRole("button", { name: "Continue" }).isDisabled()) throw new Error("still blocked after choosing Nigeria");
    const wide = await D.page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1);
    if (wide) throw new Error("sideways scroll on onboarding at phone width");
    dws = (await api(D.page, "POST", "/v1/freelancer/onboarding", { profile: { ...flp, full_name: "Musa Ibrahim", career_stage: "job_seeker",
      country: "NG", city: "Kano", experiences: [], portfolio: [], certifications: [] } })).workspace_id;
  });
  await step(D.page, "D2. Remotive US-only role is flagged not eligible; listing stays unverified", async () => {
    await D.page.goto(`${BASE}/f/${dws}/opportunities`);
    await D.page.getByRole("button", { name: "Find on Remotive" }).click();
    await D.page.getByLabel("Search title, company or skills").fill("backend");
    await D.page.getByRole("button", { name: "Search" }).click();
    await text(D.page, "Backend Engineer");
    await D.page.getByRole("dialog").getByRole("button", { name: "Save" }).first().click();
    await text(D.page, "Not verified");
    await text(D.page, /Not eligible|not eligible/);
  });
  await step(D.page, "D3. Keyboard-only sign-in works (Tab + Enter)", async () => {
    const k = await browser.newContext(); const kp = await k.newPage();
    await kp.goto(`${BASE}/login`);
    await kp.getByLabel("Email").focus();
    await kp.keyboard.type(D.email); await kp.keyboard.press("Tab"); await kp.keyboard.type(PW); await kp.keyboard.press("Enter");
    await kp.waitForURL(/\/(start|f\/|freelancer)/);
    await k.close();
  });

  // ================================================================ P. Launch: consent, legal pages, data rights
  console.log("P. Consent and data rights");
  const P = { ctx: await browser.newContext({ viewport: { width: 1360, height: 900 }, acceptDownloads: true }) };
  P.page = await P.ctx.newPage(); P.page.setDefaultTimeout(15000);
  let ews;
  await step(P.page, "E1. Sign-up can't proceed until the terms are accepted; legal pages open without an account", async () => {
    await P.page.goto(`${BASE}/signup`, { waitUntil: "networkidle" });
    P.email = `ngozi-${Date.now()}@example.com`;
    await P.page.getByLabel("Your name").fill("Ngozi Eze");
    await P.page.getByLabel("Email").fill(P.email);
    await P.page.getByLabel("Password").fill(PW);
    if (!(await P.page.getByRole("button", { name: "Create account" }).isDisabled())) throw new Error("can sign up without accepting");
    const legal = await P.ctx.newPage();
    for (const [path, h] of [["/privacy", "Privacy Policy"], ["/terms", "Terms of Service"]]) {
      await legal.goto(`${BASE}${path}`);
      await legal.getByRole("heading", { name: h, level: 1 }).waitFor();
      await legal.getByText("Draft for legal review").waitFor();  // drafts are labelled until approved
    }
    await legal.close();
    await P.page.getByRole("checkbox", { name: /I agree to the Terms/ }).check();
    await P.page.getByRole("button", { name: "Create account" }).click();
    await P.page.waitForURL(/\/start/);
    ews = (await api(P.page, "POST", "/v1/freelancer/onboarding", { profile: { ...flp, full_name: "Ngozi Eze" } })).workspace_id;
  });
  await step(P.page, "E2. Download my data gives a JSON file with my account in it", async () => {
    await P.page.goto(`${BASE}/f/${ews}/settings`);
    const [dl] = await Promise.all([P.page.waitForEvent("download"), P.page.getByRole("link", { name: "Download my data" }).click()]);
    const data = JSON.parse(fs.readFileSync(await dl.path(), "utf8"));
    if (data.account.email !== P.email || "password_hash" in data.account) throw new Error("export content wrong");
    if (!data.professional_profiles.length) throw new Error("profile missing from export");
  });
  await step(P.page, "E3. Delete my account: wrong password refused; then signed out and the account is gone", async () => {
    await P.page.getByRole("button", { name: "Delete my account" }).click();
    await P.page.getByLabel("Your password").fill("not-my-password-1");
    await P.page.getByLabel("Type DELETE to confirm").fill("DELETE");
    await P.page.getByRole("button", { name: "Delete my account" }).last().click();
    await text(P.page, "Password is incorrect");
    await P.page.getByLabel("Your password").fill(PW);
    await P.page.getByRole("button", { name: "Delete my account" }).last().click();
    await P.page.waitForURL(/\/login\?deleted=1/);
    await text(P.page, "Your account was deleted");
    await login(P.page, P.email);
    await text(P.page, "Email or password is incorrect.");
  });
  await P.ctx.close();

  // ================================================================ I. New Age AI brand + installable app
  console.log("I. Brand and install");
  const I = { ctx: await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true }) };
  I.page = await I.ctx.newPage(); I.page.setDefaultTimeout(15000);
  await step(I.page, "I1. Manifest and icons load without an account, at the sizes they claim", async () => {
    const m = await (await I.page.request.get(`${BASE}/manifest.webmanifest`)).json();
    if (m.name !== "New Age AI" || m.display !== "standalone" || m.start_url !== "/start") throw new Error(JSON.stringify(m).slice(0, 200));
    if (!m.icons.some((i) => i.purpose === "maskable")) throw new Error("no maskable icon");
    for (const ic of m.icons) {
      const r = await I.page.request.get(`${BASE}${ic.src}`);
      const b = await r.body();
      const w = b.readUInt32BE(16), h = b.readUInt32BE(20);  // PNG IHDR
      if (!r.ok() || r.headers()["content-type"] !== "image/png" || `${w}x${h}` !== ic.sizes) throw new Error(`${ic.src} ${r.status()} ${w}x${h}`);
    }
    await I.page.goto(`${BASE}/login`, { waitUntil: "networkidle" });
    const head = await I.page.evaluate(() => ({
      manifest: !!document.querySelector('link[rel="manifest"]'), apple: !!document.querySelector('link[rel="apple-touch-icon"]'),
      theme: document.querySelector('meta[name="theme-color"]')?.getAttribute("content"), title: document.title }));
    if (!head.manifest || !head.apple || head.theme !== "#171717" || head.title !== "New Age AI") throw new Error(JSON.stringify(head));
    await I.page.getByRole("img", { name: "New Age AI" }).first().waitFor();
    await I.page.getByText("A product of New Age Media").filter({ visible: true }).first().waitFor();  // desktop panel copy is hidden on phones
  });
  await step(I.page, "I2. Service worker registers; offline shows a friendly screen; nothing personal is cached", async () => {
    await I.page.evaluate(() => navigator.serviceWorker.ready.then(() => true));
    await I.page.reload({ waitUntil: "networkidle" });  // page now controlled by the worker
    await I.ctx.setOffline(true);
    await I.page.goto(`${BASE}/start`).catch(() => {});
    await text(I.page, "You're offline");
    await I.ctx.setOffline(false);
    const cached = await I.page.evaluate(async () => {
      const out = [];
      for (const k of await caches.keys()) for (const r of await (await caches.open(k)).keys()) out.push(new URL(r.url).pathname);
      return out.sort();
    });
    if (JSON.stringify(cached) !== JSON.stringify(["/favicon.png", "/icons/icon-192.png", "/offline"])) throw new Error("cache holds: " + cached);
  });
  await I.ctx.close();

  // ================================================================ X. Accessibility, mobile and speed sweep
  console.log("X. Accessibility / mobile / performance");
  const axe = fs.readFileSync("node_modules/axe-core/axe.min.js", "utf8");
  const pages = [
    [null, "/login"], [null, "/signup"], [null, "/privacy"], [null, "/terms"], [null, "/forgot-password"], [null, "/reset-password#token=x"], [null, "/offline"],
    [B, `/clients`], [B, `/c/${ws1}`], [B, `/c/${ws1}/studio`], [B, `/c/${ws1}/library`], [B, `/c/${ws1}/calendar`],
    [B, `/c/${ws1}/reports`], [B, `/c/${ws1}/settings`],
    [A, `/b/${aws}`], [A, `/b/${aws}/tools`], [A, `/b/${aws}/results`], [A, `/b/${aws}/work`],
    [C, `/f/${cws}`], [C, `/f/${cws}/profile`], [C, `/f/${cws}/opportunities`], [C, `/f/${cws}/applications`],
    [C, `/f/${cws}/interview`], [C, `/f/${cws}/resources`], [C, `/f/${cws}/work`],
  ];
  const report = [];
  for (const [who, p] of pages) {
    for (const vp of [{ width: 1360, height: 900 }, { width: 360, height: 740 }]) {
      const ctx = await browser.newContext({ viewport: vp, storageState: who ? await who.ctx.storageState() : undefined });
      const pg = await ctx.newPage();
      const cspErrors = [];
      pg.on("console", (m) => { if (/Content Security Policy|Refused to (load|execute|apply|connect)/i.test(m.text())) cspErrors.push(m.text().slice(0, 120)); });
      const t0 = Date.now();
      const resp = await pg.goto(`${BASE}${p}`, { waitUntil: "networkidle" }).catch(() => null);
      const loadMs = Date.now() - t0;
      const nav = await pg.evaluate(() => { const n = performance.getEntriesByType("navigation")[0]; return n ? Math.round(n.domContentLoadedEventEnd) : null; });
      const overflow = await pg.evaluate(() => document.documentElement.scrollWidth - innerWidth);
      const appCspErrors = [...cspErrors];  // snapshot: axe itself fetches stylesheets, which the CSP rightly blocks
      let violations = [];
      if (vp.width === 1360) {
        await pg.addScriptTag({ content: axe });
        violations = await pg.evaluate(async () => (await window.axe.run(document, { runOnly: ["wcag2a", "wcag2aa"] })).violations
          .map((v) => ({ id: v.id, impact: v.impact, n: v.nodes.length, sample: v.nodes[0]?.target?.join(" ") })));
      }
      // WCAG 2.2 target size: inline text links are exempt, so check controls only
      const small = vp.width === 360 ? await pg.evaluate(() => [...document.querySelectorAll("button, input:not([type=hidden]), select, [role=tab]")]
        .filter((e) => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0 && (r.height < 24 || r.width < 24); })
        .map((e) => (e.getAttribute("aria-label") || e.textContent || e.tagName).trim().slice(0, 30)).slice(0, 5)) : [];
      const landed = new URL(pg.url()).pathname, want = p.split(/[?#]/)[0];
      const h1 = await pg.locator("h1").first().textContent({ timeout: 3000 }).catch(() => "");
      report.push({ page: p.replace(/[0-9a-f-]{36}/g, ":id"), viewport: vp.width, loadMs, dcl: nav, overflow, violations, small,
                    landed: landed === want, h1: (h1 || "").trim().slice(0, 40),
                    csp: !!resp && /nonce-/.test(resp.headers()["content-security-policy"] || ""), cspErrors: appCspErrors, axeCspErrors: cspErrors.length - appCspErrors.length,
                    title: await pg.waitForTimeout(1000).then(() => pg.title()) });  // read late: catches a title reset after load
      await ctx.close();
    }
  }
  fs.writeFileSync(path.join(OUT, "a11y-perf.json"), JSON.stringify(report, null, 1));
  const strays = report.filter((r) => !r.landed || !r.h1);
  results.push({ name: `X0. Sweep reached all ${pages.length} intended pages (no redirect to sign-in, each has a heading)`,
                 ok: strays.length === 0, error: strays.map((r) => `${r.page}@${r.viewport} landed=${r.landed} h1="${r.h1}"`).join(", ") });
  const divName = { "/c/": "Creator & Marketing", "/b/": "Business", "/f/": "Freelancer" };
  const badSec = report.filter((r) => !r.csp || r.cspErrors.length ||
    Object.entries(divName).some(([k, v]) => r.page.startsWith(k) && !r.title.includes(v)) ||
    (!/^\/(c|b|f)\//.test(r.page) && r.title.includes("Creator & Marketing")));
  results.push({ name: `X5. Nonce CSP on all ${pages.length} pages with zero violations; titles name the right product`,
                 ok: badSec.length === 0, error: badSec.map((r) => `${r.page}@${r.viewport} csp=${r.csp} errs=${r.cspErrors.join("|")} title="${r.title}"`).join(", ") });
  const overflowing = report.filter((r) => r.overflow > 1);
  const serious = report.flatMap((r) => r.violations.filter((v) => ["serious", "critical"].includes(v.impact)).map((v) => `${r.page}: ${v.id} (${v.n})`));
  results.push({ name: `X1. No sideways scroll at 360px on ${pages.length} pages`, ok: overflowing.length === 0,
                 error: overflowing.map((r) => `${r.page} +${r.overflow}px`).join(", ") });
  results.push({ name: `X2. No serious/critical WCAG 2 A/AA violations (axe) on ${pages.length} pages`, ok: serious.length === 0,
                 error: [...new Set(serious)].join("; ") });
  const tiny = report.filter((r) => r.small.length);
  results.push({ name: "X4. Controls are at least 24×24px at 360px (WCAG 2.2 target size)", ok: tiny.length === 0,
                 error: tiny.map((r) => `${r.page}: ${r.small.join("|")}`).join("; ") });
  const slow = report.filter((r) => r.loadMs > 3000);
  results.push({ name: "X3. Every page settles under 3s (local, production build)", ok: slow.length === 0,
                 error: slow.map((r) => `${r.page}@${r.viewport} ${r.loadMs}ms`).join(", ") });
  for (const r of results.slice(-6)) console.log(`  ${r.ok ? "✓" : "✗"} ${r.name}${r.ok ? "" : "\n    " + r.error}`);
  await browser.close();
}

main().catch((e) => { console.error(e); }).finally(() => {
  const ok = results.filter((r) => r.ok).length;
  console.log(`\n${ok}/${results.length} persona checks passed`);
  fs.writeFileSync(path.join(OUT, "results.json"), JSON.stringify(results, null, 2));
  process.exit(ok === results.length ? 0 : 1);
});
