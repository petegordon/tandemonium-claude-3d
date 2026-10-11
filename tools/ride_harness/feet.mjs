// Foot-on-pedal check in three.js (the game's interpolation): for crank angles in 1-degree steps, the distance
// from each goose's ball of the foot (ToeBase) to its pedal pin raised by the ball height above the sole
// (ride_fit.py's contact target), in bike metres.
//   node tools/ride_harness/serve.mjs 8191 &   node tools/ride_harness/feet.mjs "http://127.0.0.1:8191/"
import { createRequire } from "module";
import path from "node:path";

const here = path.dirname(new URL(import.meta.url).pathname.replace(/^\/([A-Z]:)/, "$1"));
const require = createRequire(path.resolve(here, "../../../tandemonium/package.json"));
const puppeteer = require("puppeteer");
const url = process.argv[2];
const b = await puppeteer.launch({ headless: "new", args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader"] });
const p = await b.newPage();
await p.goto(url, { waitUntil: "networkidle0", timeout: 120000 });
await p.waitForFunction(() => window.__harness && window.__harness.bike && Object.keys(window.__harness.riders).length === 2, { timeout: 120000 });
const res = await p.evaluate(async () => {
  const h = window.__harness, THREE_V = (o) => { const v = o.getWorldPosition(o.position.clone()); return v; };
  const BALL = { Captain: 0.0244, Stoker: 0.028 };
  const pins = { Captain: { L: "PedalPin_FL", R: "PedalPin_FR" }, Stoker: { L: "PedalPin_RL", R: "PedalPin_RR" } };
  const out = {};
  for (const seat of ["Captain", "Stoker"]) out[seat] = { max: 0, at: 0, mean: 0, onKey: 0 };
  let n = 0;
  for (let deg = 0; deg < 360; deg += 1) {
    h.state.crank = h.state.crankTarget = deg * Math.PI / 180;
    await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
    n++;
    for (const seat of ["Captain", "Stoker"]) {
      const root = h.riders[seat].mixer.getRoot();
      const kroot = h.bike.root.parent;            // kNode: world units -> bike metres (k = 1 by default)
      for (const side of ["L", "R"]) {
        const toe = THREE_V(root.getObjectByName(side === "L" ? "LeftToeBase" : "RightToeBase"));
        const pin = THREE_V(h.bike.root.getObjectByName(pins[seat][side]));
        const up = h.bike.root.getObjectByName("Bike_root");
        const d = Math.hypot(toe.x - pin.x, toe.y - (pin.y + BALL[seat] * kroot.scale.y), toe.z - pin.z) / kroot.scale.y;
        const o = out[seat];
        o.mean += d / 720;
        if (d > o.max) { o.max = d; o.at = deg; }
        if (deg % 15 === 0) o.onKey = Math.max(o.onKey, d);
      }
    }
  }
  for (const s in out) for (const k of ["max", "mean", "onKey"]) out[s][k] = +(out[s][k] * 1000).toFixed(1);
  return out;
});
console.log(JSON.stringify({ mm: res }, null, 1));
await b.close();
