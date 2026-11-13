// End-to-end run of every Business Marketing workflow in a real browser against the real web app, API and database.
// Prereqs: API on :8000 (eco-backend `python -m tests.e2e_server`) and this app on :3000 (`npm run start:prod`).
// Only the LLM is scripted, inside the test API server. Run: node e2e/business.mjs
import { createRequire } from "node:module";
import fs from "node:fs";
import path from "node:path";

const require = createRequire(import.meta.url);
const { chromium, devices } = require("playwright");
const BASE = process.env.WEB_URL || "http://localhost:3000";
const OUT = path.resolve("e2e/out/business");
fs.mkdirSync(OUT, { recursive: true });
const TOTAL = 13;

const results = [];
let page, ctx, browser;
const shot = (name) => page.screenshot({ path: path.join(OUT, `${name}.png`), fullPage: true });
async function step(name, fn) {
  const t0 = Date.now();
  try { await fn(); results.push({ name, ok: true, ms: Date.now() - t0 }); console.log(`  ✓ ${name}`); }
  catch (e) {
    results.push({ name, ok: false, error: String(e).split("\n")[0] });
    console.log(`  ✗ ${name}\n    ${String(e).split("\n").slice(0, 3).join("\n    ")}`);
    await shot(`FAIL-${name.replace(/\W+/g, "-")}`).catch(() => {});
    throw e;
  }
}
const expectText = (t, opts) => page.getByText(t, opts).first().waitFor({ timeout: 15000 });
const toast = (t) => page.locator("[aria-live=polite]").getByText(t).first().waitFor({ timeout: 15000 });
const api = async (p) => (await page.request.get(`${BASE}/api/proxy${p}`)).json();

async function main() {
  browser = await chromium.launch();
  ctx = await browser.newContext({ viewport: { width: 1360, height: 900 }, deviceScaleFactor: 2 });
  page = await ctx.newPage();
  page.setDefaultTimeout(15000);
  const email = `nkechi-${Date.now()}@example.com`;
  let ws;

  await step("1. Sign up, pick Business, six-step onboarding", async () => {
    await page.goto(`${BASE}/signup`);
    await page.getByLabel("Your name").fill("Nkechi Eze");
    await page.getByLabel("Email").fill(email);
    await page.getByLabel("Password").fill("correct-horse-battery");
    await page.getByRole("checkbox", { name: /I agree to the Terms/ }).check();
    await page.getByRole("button", { name: "Create account" }).click();
    await page.waitForURL(/\/start/);
    await expectText("Freelancer Growth");
    await shot("01-product-chooser");
    await page.getByRole("link", { name: /Business Marketing/ }).click();
    await page.waitForURL(/\/business\/onboarding/);
    await page.getByRole("button", { name: "Continue" }).click();
    await page.getByRole("radio", { name: /Food & drink/ }).click();
    await expectText("Typical focus for");
    await page.getByLabel("Stage").selectOption("new");
    await shot("02-category");
    await page.getByRole("button", { name: "Continue" }).click();
    await page.getByLabel("Business name").fill("Mama Nkechi's Kitchen");
    await page.getByLabel("Industry").fill("Catering");
    await page.getByLabel("Speciality (optional)").fill("Party trays");
    await page.getByLabel("Where you're based").fill("Awka, Nigeria");
    await page.getByLabel("Target markets").fill("Awka, Onitsha");
    await page.getByRole("button", { name: "Continue" }).click();
    await page.getByLabel("Product or service 1", { exact: true }).fill("Small chops tray");
    await page.getByLabel("Price (optional)").fill("NGN 25,000");
    await page.getByLabel("Ideal customers").fill("Families and event planners hosting parties");
    await page.getByLabel("What makes you different").fill("Same-day delivery, home recipes");
    await page.getByRole("button", { name: "Continue" }).click();
    await page.getByRole("button", { name: "Add competitor" }).click();
    await page.getByLabel("Competitor name").fill("Chop Express");
    await page.getByLabel("What you've noticed").fill("Cheaper but often late");
    await page.getByLabel("WhatsApp status").selectOption("using");
    await page.getByLabel("Instagram status").selectOption("tried");
    await page.getByRole("button", { name: "Continue" }).click();
    await page.getByLabel("Goal 1", { exact: true }).fill("More weekend party orders");
    await page.getByLabel("How you'll measure it").fill("orders per weekend");
    await page.getByLabel("Target", { exact: true }).fill("20");
    await page.getByLabel("Monthly marketing budget (optional)").fill("50000");
    await shot("03-goals-budget");
    await page.getByRole("button", { name: "Create & build my profile" }).click();
    await page.waitForURL(/\/b\/[0-9a-f-]{36}\/profile/);
    ws = page.url().split("/b/")[1].split("/")[0];
    const cookies = await page.evaluate(() => document.cookie);
    if (cookies.includes("eco_at") || cookies.includes("eco_rt")) throw new Error("auth tokens readable by page script");
  });

  await step("2. AI builds the Intelligence Profile; owner applies and edits it", async () => {
    await expectText("New profile drafted");
    await shot("04-intelligence-draft");
    const before = await api(`/v1/workspaces/${ws}/business-profile`);
    if (Object.keys(before.intelligence).length) throw new Error("profile was applied before the owner chose to");
    await page.getByRole("button", { name: "Use this profile" }).click();
    await toast("Profile updated");
    await page.getByLabel("Priorities (next 90 days)").fill("Get 10 Google reviews\nPost party photos every Friday");
    await page.getByRole("button", { name: "Save intelligence profile" }).click();
    await toast("Intelligence profile saved");
    const after = await api(`/v1/workspaces/${ws}/business-profile`);
    if (after.intelligence.priorities[0] !== "Get 10 Google reviews" || !after.intelligence.edited_by_user) throw new Error("edit not saved");
    await expectText("Edited");
    await shot("05-intelligence-edited");
  });

  await step("3. Dashboard adapts to the business", async () => {
    await page.goto(`${BASE}/b/${ws}`);
    await page.getByRole("heading", { name: "Mama Nkechi's Kitchen" }).waitFor();
    await expectText("Recommended next");
    await expectText("Get 10 Google reviews");
    await expectText("Food & drink");
    await shot("06-dashboard");
  });

  await step("4. Marketing plan (6 months) saved into a new project", async () => {
    await page.goto(`${BASE}/b/${ws}/tools`);
    await page.getByRole("link", { name: /Marketing plan/ }).click();
    await page.getByLabel("Plan length").selectOption("6");
    await page.getByRole("button", { name: "Generate plan" }).click();
    await expectText("Month 6");
    await page.getByRole("button", { name: "Save", exact: true }).click();
    await page.getByLabel("Project").selectOption("__new");
    await page.getByLabel("New project name").fill("December push");
    await page.getByRole("dialog").getByRole("button", { name: "Save" }).click();
    await toast("Saved");
    await shot("07-plan");
  });

  await step("5. Competitor analysis stays on named competitors", async () => {
    await page.goto(`${BASE}/b/${ws}/tools/competitors`);
    await page.getByRole("button", { name: "Compare competitors" }).click();
    await page.getByRole("heading", { name: "Chop Express" }).waitFor();
    await expectText("no live web research");
    await shot("08-competitors");
  });

  await step("6. Positioning applied to the brand section", async () => {
    await page.goto(`${BASE}/b/${ws}/tools/positioning`);
    await page.getByRole("button", { name: "Define my positioning" }).click();
    await expectText("Tagline options");
    await page.getByRole("button", { name: "Apply selected" }).click();
    await toast("Applied to your profile");
    await page.goto(`${BASE}/b/${ws}/profile`);
    await page.getByRole("tab", { name: "Brand & messaging" }).click();
    await expectText("Done right, on time.");
  });

  await step("7. Ad plan → campaign; spend approval never spends", async () => {
    await page.goto(`${BASE}/b/${ws}/tools/ads`);
    await page.getByLabel("Campaign starts").fill("2026-12-01");
    await page.getByLabel("Campaign ends").fill("2026-12-24");
    await page.getByRole("button", { name: "Plan ads" }).click();
    await expectText("Check before launching");
    await page.getByRole("button", { name: "Request approval to spend" }).click();
    await page.getByLabel("Amount to spend").fill("30000");
    await page.getByRole("dialog").getByRole("button", { name: "Request approval" }).click();
    await expectText("Request recorded");
    await page.keyboard.press("Escape");
    await page.getByRole("button", { name: "Create campaign" }).click();
    await page.waitForURL(/\/campaigns\?open=/);
    await expectText("Ad copy from the plan");
    await shot("09-campaign");
    await page.goto(`${BASE}/b/${ws}/approvals`);
    await expectText("Launch: More enquiries");
    await page.getByRole("button", { name: "Approve" }).click();
    await expectText("Can't carry this out yet");
    const acts = await api(`/v1/workspaces/${ws}/actions?status=awaiting_approval`);
    if (acts.data.length !== 1) throw new Error("approval changed state without an integration");
    await shot("10-approvals");
    await page.getByRole("button", { name: "Reject" }).click();
    await toast("Rejected");
  });

  await step("8. Results: manual entry, CSV import, report maths", async () => {
    await page.goto(`${BASE}/b/${ws}/results`);
    await page.getByRole("button", { name: "Add results" }).click();
    const today = new Date().toISOString().slice(0, 10);
    await page.getByLabel("Channel", { exact: true }).selectOption("instagram");
    await page.getByLabel("From", { exact: true }).fill(today);
    await page.getByLabel("To", { exact: true }).fill(today);
    await page.getByLabel("Leads", { exact: true }).fill("5");
    await page.getByRole("dialog").getByRole("button", { name: "Save" }).click();
    await toast("Results saved");
    const csv = `channel,period_start,period_end,spend,leads,customers,revenue\nFacebook Ads,${today},${today},20000,40,8,200000\n`;
    await page.locator("input[type=file]").setInputFiles({ name: "results.csv", mimeType: "text/csv", buffer: Buffer.from(csv) });
    await toast("Imported 1 row(s)");
    await page.locator("td", { hasText: "Meta ads" }).first().waitFor();
    await expectText("NGN 500"); // cost per lead on Meta ads: 20,000 / 40
    await page.locator("input[type=file]").setInputFiles({ name: "bad.csv", mimeType: "text/csv", buffer: Buffer.from("channel,period_start,leads\nmyspace,2026-11-01,3\n") });
    await expectText("Nothing was imported");
    await shot("11-results");
  });

  await step("9. AI performance analysis uses only recorded numbers", async () => {
    await page.goto(`${BASE}/b/${ws}/tools/report`);
    await page.getByRole("button", { name: "Analyse results" }).click();
    await expectText("45 leads recorded");
    await page.getByRole("link", { name: "Download report (HTML)" }).waitFor();
    await shot("12-analysis");
  });

  await step("10. Saved work: open, edit (new version), export", async () => {
    await page.goto(`${BASE}/b/${ws}/work`);
    await page.getByRole("navigation", { name: "Projects" }).getByRole("button", { name: "December push" }).click();
    await page.getByRole("button", { name: /Marketing plan · / }).click();
    await page.getByRole("tab", { name: "Edit" }).click();
    const box = page.getByLabel("Content");
    await box.fill((await box.inputValue()) + "\n\n### Owner notes\n- Book the photographer early");
    await page.getByRole("button", { name: "Save changes" }).click();
    await toast("Saved a new version");
    await expectText("v2 · Edited");
    await page.getByRole("link", { name: "Markdown" }).waitFor();
    await shot("13-saved-work");
  });

  await step("11. Strategist chat answers in this business only", async () => {
    await page.goto(`${BASE}/b/${ws}/strategist`);
    await expectText("Ask your marketing strategist");
    await page.getByLabel("Message").fill("Where should I spend my first marketing budget?");
    await page.getByRole("button", { name: "Send" }).click();
    await expectText("Draft reply to:");
    await expectText("Marketing strategist");
    await page.goto(`${BASE}/c/${ws}`);
    await expectText("Not a Creator & Marketing workspace");
    await shot("14-strategist-guard");
  });

  await step("12. Settings is honest about integrations", async () => {
    await page.goto(`${BASE}/b/${ws}/settings`);
    await expectText("Launching ads / spending budget");
    if ((await page.getByText("Needs integration").count()) < 3) throw new Error("integration status missing");
    await shot("15-settings");
  });

  await step("13. Phone layout has no sideways scroll", async () => {
    const m = await browser.newContext({ ...devices["iPhone 13"], storageState: await ctx.storageState() });
    const mp = await m.newPage();
    for (const p of ["", "/tools", "/tools/plan", "/profile", "/work", "/results", "/approvals", "/campaigns"]) {
      await mp.goto(`${BASE}/b/${ws}${p}`);
      await mp.waitForLoadState("networkidle");
      const over = await mp.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
      if (over > 1) throw new Error(`${p || "/"} overflows by ${over}px`);
    }
    await mp.goto(`${BASE}/b/${ws}`);
    await mp.waitForLoadState("networkidle");
    await mp.screenshot({ path: path.join(OUT, "16-mobile-dashboard.png") });
    await m.close();
  });
}

main().catch(() => {}).finally(async () => {
  await browser?.close();
  const ok = results.filter((r) => r.ok).length;
  fs.writeFileSync(path.join(OUT, "results.json"), JSON.stringify(results, null, 2));
  console.log(`\n${ok}/${results.length} business workflow steps passed${results.length < TOTAL ? " (stopped at first failure)" : ""}`);
  process.exit(ok === TOTAL ? 0 : 1);
});
