// Drives the card through a full shop against a live HA. Usage: node drive.js BASE TOKEN OUTDIR CARD_JS
const { chromium } = require("playwright");
const fs = require("fs");
const path = require("path");
const [base, token, out, cardJs] = process.argv.slice(2);

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 400, height: 860 }, deviceScaleFactor: 2, hasTouch: true });
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  page.on("console", (m) => m.type() === "error" && !/Failed to load resource/.test(m.text()) && errors.push(m.text()));
  // Report failed requests by URL (the browser's own favicon probe is expected).
  page.on("response", (r) => r.status() >= 400 && !/favicon\.ico|\/api\/$/.test(r.url()) && errors.push(`${r.status()} ${r.url()}`));
  await page.goto(base + "/api/"); // adopt HA's origin so relative image URLs work
  await page.setContent(`<!doctype html><html><head><meta name="viewport" content="width=device-width">
    <style>body{margin:0;padding:8px;background:#f3f4f6;font-family:Roboto,system-ui,sans-serif;
      --primary-color:#03a9f4;--card-background-color:#fff;--secondary-background-color:#eef1f4;
      --primary-text-color:#212121;--secondary-text-color:#727272;--divider-color:#e0e0e0;--success-color:#43a047;--error-color:#db4437}
      ha-card{display:block;background:var(--card-background-color);border-radius:12px;box-shadow:0 1px 3px rgba(0,0,0,.15)}</style>
    </head><body></body></html>`);
  await page.addScriptTag({ content: fs.readFileSync(path.join(__dirname, "hass_shim.js"), "utf8") });
  await page.addScriptTag({ content: fs.readFileSync(cardJs, "utf8") });
  await page.evaluate(async ([b, t]) => {
    const card = document.createElement("household-shopping-card");
    card.setConfig({});
    card.hass = await window.makeHass(b, t);
    document.body.appendChild(card);
  }, [base, token]);

  const card = page.locator("household-shopping-card");
  const shot = async (name) => {
    await page.waitForTimeout(250);
    await page.screenshot({ path: path.join(out, name + ".png"), fullPage: true });
  };
  const text = () => card.evaluate((el) => el.shadowRoot.textContent);
  const click = async (sel) => {
    await card.locator(sel).first().click();
    await page.waitForTimeout(200);
  };
  const expect = async (re, label) => {
    for (let i = 0; i < 20; i++) {
      if (re.test(await text())) return;
      await page.waitForTimeout(100);
    }
    const toast = await card.evaluate((el) => el.shadowRoot.getElementById("toast").textContent);
    throw new Error(`Expected ${re} (${label}); toast: ${toast}`);
  };

  await expect(/No shop open/, "no shop");
  await expect(/Last shop/, "last summary shows");
  await shot("1-no-shop");

  await click("[data-action=new-shop]");
  await expect(/On this shop \(0\)/, "planning");
  for (const name of ["Full cream milk", "Wholemeal bread", "Broccoli", "Bananas", "Tasty cheese", "Dishwasher tablets"]) {
    await card.locator(`[data-action=toggle]:has-text("${name}")`).click();
    await page.waitForTimeout(150);
  }
  await card.locator("#add").fill("Birthday candles");
  await card.locator("#add").press("Enter");
  await expect(/On this shop \(7\)/, "7 on list");
  await shot("2-planning");

  await click("[data-action=store]");
  await card.locator("#f-store").fill("Woolworths Woden");
  await click("[data-action=save-store-real]");
  await expect(/Woolworths Woden/, "store set");

  await click("[data-action=start]");
  await expect(/left/, "shopping view");
  await shot("3-shopping");

  const row = (name) => card.locator(`[data-press]:has-text("${name}")`);
  await row("Full cream milk").locator("[data-state=got]").click();
  await row("Bananas").locator("[data-state=got]").click();
  await row("Tasty cheese").locator("[data-state=missing]").click();
  await page.waitForTimeout(300);
  await shot("4-ticked");

  // Long press opens the item menu.
  const box = await row("Broccoli").locator(".txt").boundingBox();
  await page.mouse.move(box.x + 10, box.y + 10);
  await page.mouse.down();
  await page.waitForTimeout(700);
  await page.mouse.up();
  await expect(/Change aisle/, "long-press menu");
  await shot("5-long-press");
  await click("[data-action=sheet-state][data-state=missing]");
  await expect(/missing/, "broccoli missing");

  await click("[data-action=finish]");
  await expect(/Finish this shop\?/, "confirm");
  await click("[data-action=confirm]");
  await expect(/Shop finished/, "summary");
  await shot("6-summary");
  await click("[data-action=close]");

  await click("[data-action=tab][data-tab=catalogue]");
  await expect(/Paste list/, "catalogue");
  await shot("7-catalogue");
  // Item names and notes are user/AI supplied: they must render as text, never HTML.
  const injected = await card.evaluate((el) => !!el.shadowRoot.querySelector('#body b, img[src="x"]'));
  if (injected) throw new Error("HTML injection: item name/note rendered as markup");
  await expect(/<b>Hacker<\/b> & co/, "hostile name shown literally");
  await card.locator(`[data-action=edit]:has-text("Full cream milk")`).click();
  await expect(/Home location/, "edit sheet");
  await shot("8-edit");
  await card.locator("#f-note").fill("Dairy Farmers 3L, blue cap");
  await click("[data-action=save-item]");
  await expect(/blue cap/, "note saved");

  await click("[data-action=groups]");
  await click("[data-action=group-type][data-type=aisles]");
  await expect(/order you walk/, "groups");
  await shot("9-aisles");

  await card.locator("[data-action=close]").click();
  console.log(JSON.stringify({ ok: true, errors, calls: await page.evaluate(() => window.__calls) }));
  await browser.close();
})().catch((e) => {
  console.log(JSON.stringify({ ok: false, error: String(e && e.stack || e) }));
  process.exit(1);
});
