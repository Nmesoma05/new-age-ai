// End-to-end run of every Creator workflow in a real browser against the real web app, API and database.
// Prereqs: API on :8000 (eco-backend `python -m tests.e2e_server`) and this app on :3000 (`npm run start:prod`).
// Only the LLM is scripted, inside the test API server. Run: node e2e/run.mjs
import { createRequire } from "node:module";
import { execFileSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";

const require = createRequire(import.meta.url);
const { chromium } = require("playwright");
const BASE = process.env.WEB_URL || "http://localhost:3000";
const BACKEND_DIR = process.env.BACKEND_DIR || path.resolve("../eco-backend");
const OUT = path.resolve("e2e/out");
fs.mkdirSync(OUT, { recursive: true });

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

async function main() {
  browser = await chromium.launch();
  ctx = await browser.newContext({ viewport: { width: 1360, height: 900 }, deviceScaleFactor: 2 });
  page = await ctx.newPage();
  page.setDefaultTimeout(15000);
  const email = `ada-${Date.now()}@example.com`;
  let ws, ws2;

  await step("1. Sign up and complete onboarding", async () => {
    await page.goto(`${BASE}/c/anything`);
    await page.waitForURL(/\/login/);
    await page.goto(`${BASE}/signup`);
    await page.getByLabel("Your name").fill("Ada Obi");
    await page.getByLabel("Email").fill(email);
    await page.getByLabel("Password").fill("correct-horse-battery");
    await page.getByRole("checkbox", { name: /I agree to the Terms/ }).check();
    await page.getByRole("button", { name: "Create account" }).click();
    await page.waitForURL(/\/start/);
    await page.getByRole("link", { name: /Creator & Marketing/ }).click();
    await page.waitForURL(/\/onboarding/);
    await page.getByRole("button", { name: "Continue" }).click();
    await page.getByLabel("Client or brand name").fill("Lagos Coffee Co. (sample client)");
    await page.getByLabel("Industry").fill("Food & drink");
    await page.getByLabel("Website").fill("https://lagoscoffee.example");
    await page.getByLabel("What do they do?").fill("Specialty coffee bar in Victoria Island");
    await page.getByLabel("Location").fill("Lagos");
    await page.getByRole("button", { name: "X", exact: true }).click();
    await page.getByRole("button", { name: "Continue" }).click();
    await page.getByLabel("Audience").fill("Young professionals on the Island");
    await page.getByLabel("Main goal for the next few months").fill("More weekday morning orders");
    await page.getByLabel("Voice in a few words").fill("warm, witty");
    await shot("01-onboarding");
    await page.getByRole("button", { name: "Create workspace" }).click();
    await page.waitForURL(/\/c\/[0-9a-f-]{36}$/);
    ws = page.url().split("/c/")[1];
    await expectText("Getting set up");
    await page.getByRole("heading", { name: "Lagos Coffee Co. (sample client)" }).waitFor();
    const cookies = await page.evaluate(() => document.cookie);
    if (cookies.includes("eco_at") || cookies.includes("eco_rt")) throw new Error("auth tokens readable by page script");
    await shot("02-dashboard");
  });

  await step("2. Brand profile: add competitor, save, AI voice, apply", async () => {
    await page.goto(`${BASE}/c/${ws}/brand`);
    await page.getByRole("button", { name: "Add competitor" }).click();
    await page.getByLabel("Name", { exact: true }).last().fill("Bean Bar");
    await page.getByLabel("What you've noticed").fill("Mostly product photos, few people");
    await page.getByRole("button", { name: "Save profile" }).first().click();
    await toast("Profile saved");
    await page.getByRole("button", { name: "Build voice with AI" }).click();
    await page.getByRole("button", { name: "Build brand voice" }).click();
    await expectText("Apply to the client profile");
    await page.getByRole("button", { name: "Apply selected" }).click();
    await toast("Applied to the client profile");
    await shot("03-brand-ai");
    await page.keyboard.press("Escape");
    await expectText("Content pillars");
  });

  await step("3. Studio: generate, edit, save drafts", async () => {
    await page.goto(`${BASE}/c/${ws}/studio`);
    await page.getByLabel("What should the content be about?").fill("Launch of our cold brew, weekday mornings only");
    await page.getByRole("button", { name: /Generate 3 drafts/ }).click();
    await expectText("Check these before using it");
    const posts = page.getByLabel("Post");
    if ((await posts.count()) !== 3) throw new Error(`expected 3 drafts, got ${await posts.count()}`);
    await posts.first().fill("Cold brew is here. Weekday mornings only, while it lasts.");
    await shot("04-studio");
    await page.getByRole("button", { name: "Save 3 to library" }).click();
    await toast("Saved 3 drafts to the library");
  });

  let firstTitle;
  await step("4. Library: edit history, send for approval, approve", async () => {
    await page.goto(`${BASE}/c/${ws}/library`);
    const cards = page.locator("main ul li button");
    await cards.first().waitFor();
    if ((await cards.count()) < 3) throw new Error("expected 3 library items");
    const edited = page.locator("main ul li button", { hasText: "Hook idea A" });
    await edited.click();
    firstTitle = "Hook idea A";
    await expectText("v2 · Edited");
    await page.getByRole("button", { name: "Send for approval" }).click();
    await toast("Sent for approval");
    await page.getByRole("button", { name: "Approve" }).click();
    await toast("Approved");
    await shot("05-library-approved");
    await page.keyboard.press("Escape");
  });

  await step("5. Calendar: AI plan, import, link content, mark as posted", async () => {
    await page.goto(`${BASE}/c/${ws}/calendar`);
    await page.getByRole("button", { name: "Plan with AI" }).click();
    await page.getByRole("button", { name: "Plan the calendar" }).click();
    await expectText("Strategy");
    await page.getByRole("button", { name: /^Add \d+ to calendar$/ }).click();
    await toast(/Added \d+ item\(s\) to the calendar/);
    await page.waitForTimeout(500);
    const chips = page.locator("main .grid.grid-cols-7 li button");
    await chips.first().waitFor();
    await shot("06-calendar");
    await chips.first().click();
    await page.getByLabel("Content").selectOption({ label: /Hook idea A/ }).catch(async () => {
      const opt = await page.getByLabel("Content").locator("option", { hasText: "Hook idea A" }).first().getAttribute("value");
      await page.getByLabel("Content").selectOption(opt);
    });
    await page.getByRole("button", { name: "Save", exact: true }).click();
    await toast("Saved");
    await chips.first().click();
    await page.getByRole("button", { name: "Mark as posted" }).first().click();
    await page.getByLabel("Link to the live post (optional)").fill("https://instagram.com/p/sample");
    await page.getByLabel("I've posted this myself").check();
    await page.getByRole("dialog", { name: "Mark as posted" }).getByRole("button", { name: "Mark as posted" }).click();
    await toast("Marked as posted");
  });

  await step("6. Campaign: AI plan → campaign detail", async () => {
    await page.goto(`${BASE}/c/${ws}/campaigns`);
    await page.getByRole("button", { name: "Plan with AI" }).click();
    await page.getByLabel("What's the campaign for?").fill("December gift boxes");
    await page.getByRole("button", { name: "Plan the campaign" }).click();
    await page.getByRole("button", { name: "Create campaign from this plan" }).click();
    await page.waitForURL(/\/campaigns\/[0-9a-f-]{36}$/);
    await expectText("Phases");
    await expectText("How to measure it");
    await shot("07-campaign");
  });

  await step("7. Client review link: client asks for changes without an account", async () => {
    await page.goto(`${BASE}/c/${ws}/approvals`);
    await page.getByRole("button", { name: "Share with client" }).click();
    const dialog = page.getByRole("dialog", { name: "Share with your client" });
    await dialog.locator("li", { hasText: "Hook idea B" }).getByRole("checkbox").check();
    await dialog.getByRole("button", { name: "Create link" }).click();
    const url = (await dialog.locator(".font-mono").innerText()).trim();
    if (!url.includes("/review/")) throw new Error("no review url");
    await shot("08-share-link");
    const anon = await browser.newContext({ viewport: { width: 1200, height: 900 } });
    const p2 = await anon.newPage();
    await p2.goto(url);
    await p2.getByText("Hook idea B").first().waitFor();
    await p2.getByLabel("Your name").fill("Tolu (client)");
    await p2.getByLabel(/Feedback on/).first().fill("Make it shorter, please");
    await p2.getByRole("button", { name: "Ask for changes" }).first().click();
    await p2.getByText("changes requested: Make it shorter, please").waitFor();
    await p2.screenshot({ path: path.join(OUT, "09-client-review.png"), fullPage: true });
    await anon.close();
    await page.goto(`${BASE}/c/${ws}/library`);
    await page.locator("main ul li button", { hasText: "Hook idea B" }).click();
    await expectText("Tolu (client) (client)");
    await page.keyboard.press("Escape");
  });

  await step("8. Reports: manual figures, CSV upload, AI summary, export", async () => {
    await page.goto(`${BASE}/c/${ws}/reports`);
    await expectText("No figures recorded for this period");
    await page.getByRole("button", { name: "Add figures" }).first().click();
    await page.getByLabel("Post", { exact: true }).fill("Cold brew launch");
    await page.getByLabel("impressions").fill("5100");
    await page.getByLabel("likes").fill("300");
    await page.getByLabel("comments").fill("40");
    await page.getByRole("button", { name: "Save", exact: true }).click();
    await toast("Figures saved");
    await page.getByRole("button", { name: "Upload CSV" }).click();
    const today = new Date().toISOString().slice(0, 10);
    await page.getByLabel("CSV file").setInputFiles({ name: "x.csv", mimeType: "text/csv",
      buffer: Buffer.from(`title,platform,published_on,impressions,likes\nMorning menu,x,${today},1300,30\n`) });
    await page.getByRole("button", { name: "Import" }).click();
    await toast("Imported 1 row(s)");
    await expectText("6,400");
    await page.getByRole("button", { name: "Write summary" }).click();
    await expectText("2 posts recorded with 6,400 impressions");
    await shot("10-reports");
    const href = await page.getByRole("link", { name: "Report (HTML)" }).getAttribute("href");
    const r = await page.request.get(BASE + href);
    if (r.status() !== 200 || !(r.headers()["content-disposition"] || "").startsWith("attachment")) throw new Error("export failed");
    if (!(await r.text()).includes("not fetched from the platforms")) throw new Error("export lacks data-source note");
  });

  await step("9. Research uses only recorded information", async () => {
    await page.goto(`${BASE}/c/${ws}/research`);
    await expectText("Bean Bar");
    await page.getByRole("button", { name: "Analyse" }).click();
    await expectText("no live web research");
    await expectText("Saved to the library");
  });

  await step("10. Assistant chat", async () => {
    await page.goto(`${BASE}/c/${ws}/assistant`);
    await page.getByLabel("Message").fill("Give me 5 hook ideas for this week");
    await page.getByRole("button", { name: "Send" }).click();
    await expectText("Draft reply to: Give me 5 hook ideas for this week");
    await shot("11-assistant");
  });

  await step("11. Settings shows what needs integrations", async () => {
    await page.goto(`${BASE}/c/${ws}/settings`);
    await expectText("Publishing / scheduling to platforms");
    if ((await page.getByText("Needs integration").count()) < 10) throw new Error("integration status missing");
    await shot("12-settings");
  });

  await step("12. Dashboard reflects the work", async () => {
    await page.goto(`${BASE}/c/${ws}`);
    await expectText("Getting set up");
    const posted = page.locator("text=Posted").first();
    await posted.waitFor();
    await shot("13-dashboard-after");
  });

  await step("13. Multi-client: Free limit, upgrade, second client isolated", async () => {
    await page.goto(`${BASE}/clients`);
    await page.getByRole("button", { name: "Add client" }).click();
    await page.getByLabel("Client or brand name").fill("Second Client");
    await page.getByRole("button", { name: "Create workspace" }).click();
    await expectText("Your plan's client limit is reached");
    await page.keyboard.press("Escape");
    const st = await page.request.get(`${BASE}/api/proxy/v1/creator/onboarding`);
    const orgId = (await st.json()).orgs[0].id;
    execFileSync("python3", ["-m", "tests.e2e_server", "activate", orgId, "pro"], { cwd: BACKEND_DIR });
    await page.reload();
    await page.getByRole("button", { name: "Add client" }).click();
    await page.getByLabel("Client or brand name").fill("Second Client");
    await page.getByRole("button", { name: "Create workspace" }).click();
    await page.waitForURL(/\/brand$/);
    ws2 = page.url().split("/c/")[1].split("/")[0];
    await page.goto(`${BASE}/c/${ws2}/library`);
    await expectText("Nothing here yet");
    await page.getByLabel("Switch client").selectOption(ws);
    await page.waitForURL(new RegExp(`/c/${ws}/library`));
    await page.locator("main ul li button").first().waitFor();
    await page.goto(`${BASE}/clients`);
    await expectText("Second Client");
    await shot("14-clients");
  });

  await step("14. Phone layout has no sideways scroll", async () => {
    const m = await browser.newContext({ ...require("playwright").devices["iPhone 13"], storageState: await ctx.storageState() });
    const mp = await m.newPage();
    for (const p of ["", "/studio", "/calendar", "/reports", "/brand"]) {
      await mp.goto(`${BASE}/c/${ws}${p}`);
      await mp.waitForLoadState("networkidle");
      const over = await mp.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
      if (over > 1) throw new Error(`${p || "/"} overflows by ${over}px`);
    }
    await mp.goto(`${BASE}/c/${ws}`);
    await mp.waitForLoadState("networkidle");
    await mp.screenshot({ path: path.join(OUT, "15-mobile-dashboard.png") }); // viewport: full-page capture under device emulation widens the canvas
    await m.close();
  });

  await step("15. Sign out ends the session", async () => {
    await page.goto(`${BASE}/c/${ws}`);
    await page.getByRole("button", { name: "Sign out" }).click();
    await page.waitForURL(/\/login/);
    await page.goto(`${BASE}/c/${ws}`);
    await page.waitForURL(/\/login/);
    const r = await page.request.get(`${BASE}/api/proxy/v1/creator/clients`);
    if (r.status() !== 401) throw new Error(`expected 401 after sign-out, got ${r.status()}`);
  });

  await step("16. No secrets or API address in browser bundles", async () => {
    const dir = path.resolve(".next/static");
    const bad = [];
    const walk = (d) => fs.readdirSync(d, { withFileTypes: true }).forEach((e) => {
      const p = path.join(d, e.name);
      if (e.isDirectory()) return walk(p);
      if (!p.endsWith(".js")) return;
      const s = fs.readFileSync(p, "utf8");
      for (const needle of ["127.0.0.1:8000", "API_URL", "JWT_SECRET", "OPENAI_API_KEY", "sk-"]) if (s.includes(needle)) bad.push(`${e.name}: ${needle}`);
    });
    walk(dir);
    if (bad.length) throw new Error(bad.join(", "));
  });
}

main().catch(() => {}).finally(async () => {
  await browser?.close();
  const ok = results.filter((r) => r.ok).length;
  fs.writeFileSync(path.join(OUT, "results.json"), JSON.stringify(results, null, 2));
  console.log(`\n${ok}/${results.length} workflow steps passed${results.length < 16 ? " (stopped at first failure)" : ""}`);
  process.exit(ok === 16 ? 0 : 1);
});
