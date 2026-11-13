// End-to-end run of the implemented integrations in a real browser against the real web app, API and database.
// The providers themselves are fakes inside the test API server (no internet here). Google's consent page is
// stood in for by intercepting accounts.google.com and redirecting back with code "e2e:<code_challenge>";
// the API still runs the full state + PKCE + token exchange against that.
// Prereqs: API on :8000 (`python -m tests.e2e_server`), web on :3000. Run: node e2e/integrations.mjs
import { createRequire } from "node:module";
import fs from "node:fs";
import path from "node:path";

const require = createRequire(import.meta.url);
const { chromium } = require("playwright");
const BASE = process.env.WEB_URL || "http://localhost:3000";
const OUT = path.resolve("e2e/out/integrations");
fs.mkdirSync(OUT, { recursive: true });
const TOTAL = 9;
const CSRF = { "x-eco-csrf": "1", "content-type": "application/json" };

const results = [];
let page, browser;
const shot = (name) => page.screenshot({ path: path.join(OUT, `${name}.png`), fullPage: true });
async function step(name, fn) {
  try { await fn(); results.push({ name, ok: true }); console.log(`  ✓ ${name}`); }
  catch (e) {
    results.push({ name, ok: false, error: String(e).split("\n")[0] });
    console.log(`  ✗ ${name}\n    ${String(e).split("\n").slice(0, 3).join("\n    ")}`);
    await shot(`FAIL-${name.replace(/\W+/g, "-")}`).catch(() => {});
    throw e;
  }
}
const expectText = (t, o) => page.getByText(t, o).first().waitFor({ timeout: 15000 });
const toast = (t) => page.locator("[aria-live=polite]").getByText(t).first().waitFor({ timeout: 15000 });
const apiGet = async (p) => (await page.request.get(`${BASE}/api/proxy${p}`)).json();
const apiPost = async (p, body) => {
  const r = await page.request.post(`${BASE}/api/proxy${p}`, { headers: CSRF, data: body });
  if (!r.ok()) throw new Error(`${p} -> ${r.status()} ${await r.text()}`);
  return r.json();
};

async function signup(name) {
  await page.goto(`${BASE}/signup`);
  await page.getByLabel("Your name").fill(name);
  await page.getByLabel("Email").fill(`${name.split(" ")[0].toLowerCase()}-${Date.now()}@example.com`);
  await page.getByLabel("Password").fill("correct-horse-battery");
  await page.getByRole("checkbox", { name: /I agree to the Terms/ }).check();
  await page.getByRole("button", { name: "Create account" }).click();
  await page.waitForURL(/\/start/);
}

let googleMode = "allow";
async function fakeGoogle(ctx) {
  await ctx.route("https://accounts.google.com/**", async (route) => {
    const u = new URL(route.request().url());
    const back = new URL(u.searchParams.get("redirect_uri"));
    back.searchParams.set("state", u.searchParams.get("state"));
    if (googleMode === "allow") back.searchParams.set("code", `e2e:${u.searchParams.get("code_challenge")}`);
    else back.searchParams.set("error", "access_denied");
    await route.fulfill({ status: 302, headers: { location: back.toString() } });
  });
}

async function main() {
  browser = await chromium.launch();
  let ctx = await browser.newContext({ viewport: { width: 1360, height: 900 }, deviceScaleFactor: 2 });
  await fakeGoogle(ctx);
  page = await ctx.newPage();
  page.setDefaultTimeout(15000);
  let ws;

  await step("1. Settings shows implemented vs planned integrations", async () => {
    await signup("Ada Obi");
    const orgs = await apiGet("/v1/orgs");
    await apiPost(`/v1/orgs/${orgs[0].id}/products`, { product: "creator" });
    ws = (await apiPost(`/v1/orgs/${orgs[0].id}/workspaces`, { name: "Ada Cooks", product: "creator" })).id;
    await page.goto(`${BASE}/c/${ws}/settings`);
    await expectText("Working now");
    await expectText("YouTube channel analytics");
    await page.getByRole("button", { name: /Connect YouTube|Connect Google/ }).waitFor();
    await expectText("Planned (not available yet)");
    const planned = page.locator("#integrations").getByRole("button", { name: /Instagram/ }).first();
    await planned.click();
    await expectText("Until then:");
    await shot("01-settings");
  });

  await step("2. Connect YouTube: consent, PKCE exchange, back to settings, code removed from history", async () => {
    await page.getByRole("button", { name: /Connect YouTube|Connect Google/ }).click();
    await page.waitForURL(/\/integrations\/callback$/);
    await expectText("Connected Ada Cooks");
    await page.waitForURL(new RegExp(`/c/${ws}/settings`));
    await page.locator("#integrations").getByText("Connected", { exact: true }).waitFor();
    const conns = await apiGet(`/v1/workspaces/${ws}/integrations`);
    if (JSON.stringify(conns).includes("ya29")) throw new Error("token leaked to the browser");
    await shot("02-connected");
  });

  await step("3. Sync now pulls YouTube figures", async () => {
    await page.locator("#integrations").getByRole("button", { name: "Sync now" }).click();
    await toast("Synced 2 videos from YouTube");
    await expectText("Last sync:");
  });

  await step("4. Reports show the YouTube connection and labelled rows", async () => {
    await page.goto(`${BASE}/c/${ws}/reports`);
    await expectText("YouTube: Ada Cooks");
    await page.getByRole("tab", { name: "Last month" }).click().catch(() => page.getByRole("button", { name: "Last month" }).click());
    await expectText("Jollof in 10 minutes");
    await page.getByRole("cell", { name: "YouTube", exact: true }).first().waitFor();
    await shot("04-reports");
  });

  await step("5. Disconnect revokes at the provider and deletes our copy", async () => {
    await page.goto(`${BASE}/c/${ws}/settings`);
    await page.locator("#integrations").getByRole("button", { name: "Disconnect" }).click();
    await page.getByRole("button", { name: "Yes" }).click();
    await toast("The provider confirmed access was removed");
    await page.getByRole("button", { name: /Connect YouTube|Connect Google/ }).waitFor();
  });

  await step("6. Declining at the provider connects nothing and says so", async () => {
    googleMode = "deny";
    await page.getByRole("button", { name: /Connect YouTube|Connect Google/ }).click();
    await expectText("Access wasn't granted, so nothing was connected.");
    await shot("06-denied");
    const conns = await apiGet(`/v1/workspaces/${ws}/integrations`);
    if (conns.connections.length !== 0) throw new Error("a connection appeared after deny");
    googleMode = "allow";
  });

  await ctx.close();
  ctx = await browser.newContext({ viewport: { width: 1360, height: 900 }, deviceScaleFactor: 2, timezoneId: "Africa/Lagos" });
  page = await ctx.newPage();
  page.setDefaultTimeout(15000);
  let fws;

  await step("7. Freelancer: find and save a Remotive job (credited, unverified)", async () => {
    await signup("Chiamaka Obi");
    const profile = JSON.parse(fs.readFileSync(path.resolve("e2e/profile.json"), "utf8"));
    fws = (await apiPost("/v1/freelancer/onboarding", { profile })).workspace_id;
    await page.goto(`${BASE}/f/${fws}/opportunities`);
    await page.getByRole("button", { name: "Find on Remotive" }).click();
    await page.getByRole("link", { name: "Jobs from Remotive" }).waitFor();
    await expectText("Listings are delayed 24 hours");
    await page.getByLabel("Search title, company or skills").fill("backend");
    await page.getByRole("button", { name: "Search" }).click();
    await expectText("Backend Engineer");
    await page.getByLabel("Search title, company or skills").fill("designer");
    await page.getByRole("button", { name: "Search" }).click();
    await expectText("Salary as listed: $50k - $70k");
    await shot("07-remotive");
    await page.getByRole("dialog").getByRole("button", { name: "Save" }).first().click();
    await toast("Check it's still open before applying");
    await expectText("Imported from Remotive's public feed");
    await page.getByRole("link", { name: /Open the original posting/ }).waitFor();
    await shot("07-imported");
  });

  await step("8. Pay shown with an attributed, indicative conversion", async () => {
    const o = await apiPost(`/v1/workspaces/${fws}/freelancer/opportunities`, { title: "Product Designer (contract)",
      organisation: "PayCo", source_name: "A friend", remote_type: "remote_global", pay_min: "2000", pay_max: "3000",
      pay_currency: "USD", pay_period: "month" });
    await page.goto(`${BASE}/f/${fws}/opportunities?open=${o.id}`);
    await expectText("≈ NGN 3,001,000–4,501,500");
    await page.getByRole("link", { name: "Rates By Exchange Rate API" }).waitFor();
    await expectText("not what a bank or payment provider will pay out");
    await shot("08-fx");
  });

  await step("9. Remotive finder works at phone width without sideways scroll", async () => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto(`${BASE}/f/${fws}/opportunities`);
    await page.getByRole("button", { name: "Find on Remotive" }).click();
    await expectText("Product Designer");
    const wide = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1);
    if (wide) throw new Error("page scrolls sideways at 390px");
    await shot("09-mobile");
  });

  await browser.close();
}

main().then(() => {
  console.log(`\n${results.filter((r) => r.ok).length}/${TOTAL} passed`);
  fs.writeFileSync(path.join(OUT, "results.json"), JSON.stringify(results, null, 2));
}).catch(async () => {
  console.log(`\n${results.filter((r) => r.ok).length}/${TOTAL} passed`);
  fs.writeFileSync(path.join(OUT, "results.json"), JSON.stringify(results, null, 2));
  await browser?.close();
  process.exit(1);
});
