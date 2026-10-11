// Headless screenshots of the riding harness (gate sheets): a crank cycle from the side and the lean poses.
//
//   node tools/ride_harness/serve.mjs 8191 &   then
//   node tools/ride_harness/shots.mjs "http://127.0.0.1:8191/?bike=goosefit26" renders/_tmp/harness
//
// Writes <prefix>_crank<deg>.png (camera 2, side) and <prefix>_lean_{L,0,R}_{front,chase}.png; prints the page notes
// and any errors. Uses ../tandemonium/node_modules/puppeteer (nothing in that repo is modified).
import { createRequire } from "module";
import path from "node:path";

const here = path.dirname(new URL(import.meta.url).pathname.replace(/^\/([A-Z]:)/, "$1"));
const require = createRequire(path.resolve(here, "../../../tandemonium/package.json"));
const puppeteer = require("puppeteer");
const [url, prefix] = process.argv.slice(2);
const wait = ms => new Promise(r => setTimeout(r, ms));
const b = await puppeteer.launch({ headless: "new", args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader"] });
const p = await b.newPage();
await p.setViewport({ width: 1000, height: 700 });
const errs = [];
p.on("pageerror", e => errs.push(String(e)));
p.on("console", m => { if (m.type() === "error" && !m.text().includes("404")) errs.push(m.text()); });
await p.goto(url, { waitUntil: "networkidle0", timeout: 120000 });
await wait(4000);
const press = async k => { await p.keyboard.press(k); await wait(1200); };
await press("2");
for (const deg of [0, 45, 90, 135, 180, 225, 270, 315]) {
  await p.evaluate(d => { const s = window.__harness.state; s.crank = s.crankTarget = d * Math.PI / 180; }, deg);
  await wait(400);
  await p.screenshot({ path: `${prefix}_crank${deg}.png` });
}
for (const [tag, keys] of [["L", ["q", "u"]], ["0", []], ["R", ["e", "o"]]]) {
  await p.evaluate(ks => { const h = window.__harness; h.keys.clear(); ks.forEach(k => h.keys.add(k)); }, keys);
  await wait(1500);
  for (const [cam, name] of [["3", "front"], ["1", "chase"]]) {
    await press(cam);
    await p.screenshot({ path: `${prefix}_lean_${tag}_${name}.png` });
  }
}
console.log(JSON.stringify({ msgs: await p.$eval("#msgs", e => e.innerText), errs }, null, 1));
await b.close();
