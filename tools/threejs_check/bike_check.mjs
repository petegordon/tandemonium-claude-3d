// P4.1: check the rigged bike in headless Chrome with the GAME's three.js, against the game's own bike.
//
//   node tools/threejs_check/bike_check.mjs out/bike/bike_rigged.glb [renders/bike_p41_threejs.png] [preset]
//
// 1. mesh names: every mesh of ../tandemonium/tandem-3d/tandem_bicycle.glb exists in the new GLB (three.js names);
// 2. presets: every key of every preset in tandem-3d/bike-presets*.json resolves to a mesh;
// 3. applies a preset (default bike_orange) with the same rules as js/bike-model.js applyPreset(), on both bikes,
//    each scaled to 4.4 m like the game -> rows: original / new, columns: default, preset, 3/4, crank close-up;
// 4. clips: Pedal keeps every pedal level, stoker crank = captain + pi, pins circle the axle; WheelSpin turns
//    the wheels; sockets have identity rest rotation relative to the bike.
// Uses ../tandemonium/node_modules/{three,puppeteer}; nothing in that repo is modified.
import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";

const ROOT = path.resolve(path.dirname(new URL(import.meta.url).pathname.replace(/^\/([A-Z]:)/, "$1")), "../..");
const GAMEROOT = path.resolve(ROOT, "../tandemonium");
const GAME = path.join(GAMEROOT, "node_modules");
const require = createRequire(path.join(GAME, "puppeteer", "package.json"));
const puppeteer = require("puppeteer");
const glb = path.resolve(ROOT, process.argv[2] || "out/bike/bike_rigged.glb");
const shot = path.resolve(ROOT, process.argv[3] || "renders/bike_p41_threejs.png");
const presetName = process.argv[4] || "bike_orange";
const origGlb = path.join(GAMEROOT, "tandem-3d", "tandem_bicycle.glb");
const presets = {};
for (const f of fs.readdirSync(path.join(GAMEROOT, "tandem-3d")).filter(f => /^bike-presets.*\.json$/.test(f)))
  presets[f] = JSON.parse(fs.readFileSync(path.join(GAMEROOT, "tandem-3d", f), "utf8"));

const types = { ".js": "text/javascript", ".mjs": "text/javascript", ".glb": "model/gltf-binary", ".html": "text/html",
  ".json": "application/json" };
const page_html = `<!doctype html><html><body style="margin:0;background:#888">
<script type="importmap">{"imports":{"three":"/three/build/three.module.js","three/addons/":"/three/examples/jsm/"}}</script>
<script type="module">
import * as THREE from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
const out = { three: THREE.REVISION, problems: [] };
const W = 480, H = 300;
try {
  const presets = await fetch("/presets.json").then(r => r.json());
  const PRESET = ${JSON.stringify(presetName)};
  const load = async (u) => (await new GLTFLoader().loadAsync(u));
  const orig = await load("/orig.glb"), neu = await load("/model.glb");
  const meshNames = (g) => { const s = []; g.scene.traverse(o => { if (o.isMesh) s.push(o.name); }); return s; };
  const on = meshNames(orig), nn = new Set(meshNames(neu));
  out.meshes = { original: on.length, new: nn.size, missing: on.filter(n => !nn.has(n)) };
  if (out.meshes.missing.length) out.problems.push("missing meshes");
  out.presets = {};
  for (const [file, set] of Object.entries(presets)) for (const [pname, p] of Object.entries(set)) {
    const keys = Object.keys(p).filter(k => typeof p[k] === "object");
    const miss = keys.filter(k => !nn.has(k));
    out.presets[file + ":" + pname] = keys.length - miss.length + "/" + keys.length;
    if (miss.length) out.problems.push(file + ":" + pname + " misses " + miss.join(","));
  }
  const tris = (g) => { let t = 0; g.scene.traverse(o => { if (o.isMesh) t += (o.geometry.index ? o.geometry.index.count : o.geometry.attributes.position.count) / 3; }); return t; };
  out.tris = { original: tris(orig), new: tris(neu) };

  // ---- same rules as bike-model.js applyPreset()
  const originals = new Map();
  const applyPreset = (model, preset) => {
    if (!originals.has(model)) { const m = new Map(); model.traverse(c => { if (c.isMesh) m.set(c.name, c.material.clone()); }); originals.set(model, m); }
    model.traverse(c => { if (c.isMesh) { const o = originals.get(model).get(c.name); if (o) c.material = o.clone(); } });
    if (!preset) return;
    model.traverse(child => {
      if (!child.isMesh) return; const e = preset[child.name]; if (!e) return; const mat = child.material;
      if (e.color && mat.color) mat.color.set(e.color);
      if (e.emissive && mat.emissive) mat.emissive.set(e.emissive);
      if (e.metalness !== undefined) mat.metalness = e.metalness;
      if (e.roughness !== undefined) mat.roughness = e.roughness;
      if (e.opacity !== undefined) { mat.opacity = e.opacity; mat.transparent = e.opacity < 1; }
      if (e.wireframe !== undefined) mat.wireframe = e.wireframe;
      if (e.side !== undefined) mat.side = e.side;
      if (e.disabledTextures) { for (const tk of e.disabledTextures) mat[tk] = null; mat.needsUpdate = true; }
    });
  };
  const preset = Object.values(presets).map(s => s[PRESET]).find(Boolean);
  if (!preset) out.problems.push("preset " + PRESET + " not found");

  // ---- clips (on the new bike, before scaling)
  const sc = neu.scene; const mixer = new THREE.AnimationMixer(sc);
  const get = n => sc.getObjectByName(n);
  const clip = n => neu.animations.find(c => c.name === n);
  out.clips = neu.animations.map(c => ({ name: c.name, duration: +c.duration.toFixed(3), tracks: c.tracks.length }));
  sc.updateMatrixWorld(true);
  const root = get("Bike_root");
  const rel = (o) => root.getWorldQuaternion(new THREE.Quaternion()).invert().multiply(o.getWorldQuaternion(new THREE.Quaternion()));
  const sockets = ["Seat_Captain", "Seat_Stoker", "Grip_C_L", "Grip_C_R", "Grip_S_L", "Grip_S_R", "PedalPin_FL", "PedalPin_FR", "PedalPin_RL", "PedalPin_RR"];
  out.sockets = {};
  for (const s of sockets) {
    const o = get(s); if (!o) { out.problems.push("no socket " + s); continue; }
    const p = o.getWorldPosition(new THREE.Vector3());
    const ang = rel(o).angleTo(new THREE.Quaternion());
    out.sockets[s] = { pos: p.toArray().map(v => +v.toFixed(4)), rest_rot_deg: +(ang * 180 / Math.PI).toFixed(2) };
    if (ang > 0.01) out.problems.push(s + " rest rotation " + ang);
  }
  const restQ = {}; for (const n of ["Pedal_FL", "Pedal_FR", "Pedal_RL", "Pedal_RR", "Wheel_F", "Wheel_R"]) restQ[n] = rel(get(n));
  const pedal = clip("Pedal"), wheels = clip("WheelSpin");
  if (!pedal || !wheels) out.problems.push("missing clip");
  const act = mixer.clipAction(pedal); act.play();
  const cF = get("Crank_F").getWorldPosition(new THREE.Vector3()), cR = get("Crank_R").getWorldPosition(new THREE.Vector3());
  let maxTilt = 0; const radii = []; const phase = [];
  for (let k = 0; k < 24; k++) {
    mixer.setTime(pedal.duration * k / 24); sc.updateMatrixWorld(true);
    for (const p of ["Pedal_FL", "Pedal_FR", "Pedal_RL", "Pedal_RR"]) maxTilt = Math.max(maxTilt, rel(get(p)).angleTo(restQ[p]));
    const fl = get("Pedal_FL").getWorldPosition(new THREE.Vector3()), rl = get("Pedal_RL").getWorldPosition(new THREE.Vector3());
    radii.push(Math.hypot(fl.y - cF.y, fl.z - cF.z));
    const a = Math.atan2(fl.y - cF.y, fl.z - cF.z), b = Math.atan2(rl.y - cR.y, rl.z - cR.z);
    phase.push(Math.abs(((b - a) * 180 / Math.PI + 540) % 360 - 180));
  }
  act.stop();
  out.pedal = { max_pedal_tilt_deg: +(maxTilt * 180 / Math.PI).toFixed(3), spindle_radius_m: [Math.min(...radii), Math.max(...radii)].map(v => +v.toFixed(4)),
                stoker_minus_captain_deg: [Math.min(...phase), Math.max(...phase)].map(v => +v.toFixed(2)) };
  if (maxTilt > 0.01) out.problems.push("pedals tilt");
  if (Math.min(...phase) < 179) out.problems.push("phase not 180");
  const wa = mixer.clipAction(wheels); wa.play(); mixer.setTime(wheels.duration * 0.25); sc.updateMatrixWorld(true);
  out.wheels_quarter_turn_deg = ["Wheel_F", "Wheel_R"].map(w => +(rel(get(w)).angleTo(restQ[w]) * 180 / Math.PI).toFixed(1));
  wa.stop(); mixer.setTime(0); act.stop(); mixer.stopAllAction();
  sc.traverse(o => { if (o.isBone) o.updateMatrixWorld(true); });

  // ---- renders: game scaling (4.4 m), side by side
  const scene = new THREE.Scene(); scene.background = new THREE.Color(0xd8d8d8);
  scene.add(new THREE.HemisphereLight(0xffffff, 0x444444, 2.0));
  const sun = new THREE.DirectionalLight(0xffffff, 2.0); sun.position.set(3, 4, 2); scene.add(sun);
  const renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true });
  renderer.setSize(W, H); document.body.appendChild(renderer.domElement);
  const cam = new THREE.PerspectiveCamera(30, W / H, 0.05, 100);
  const frames = [];
  const place = (g) => {
    const m = g.scene; m.scale.setScalar(1); m.position.set(0, 0, 0); m.updateMatrixWorld(true);
    const b = new THREE.Box3().setFromObject(m), sz = b.getSize(new THREE.Vector3());
    m.scale.setScalar(4.4 / Math.max(sz.x, sz.y, sz.z)); m.updateMatrixWorld(true);
    const b2 = new THREE.Box3().setFromObject(m), c = b2.getCenter(new THREE.Vector3());
    m.position.set(-c.x, -b2.min.y, -c.z); m.updateMatrixWorld(true);
    return new THREE.Box3().setFromObject(m).getSize(new THREE.Vector3());
  };
  out.game_size = {};
  for (const [label, g] of [["original", orig], ["new", neu]]) {
    place(g);   // the game's scale (non-precise Box3, max dim -> 4.4); then the TRUE size it ends up at
    out.game_size[label] = { scale: +g.scene.scale.x.toFixed(4),
      true_size_m: new THREE.Box3().setFromObject(g.scene, true).getSize(new THREE.Vector3()).toArray().map(v => +v.toFixed(3)) };
    scene.add(g.scene);
    const views = [["default", null, [9, 1.4, 0], [0, 1.0, 0]], [PRESET, preset, [9, 1.4, 0], [0, 1.0, 0]],
                   [PRESET + " 3/4", preset, [5.5, 2.6, -5.5], [0, 1.0, 0]], [PRESET + " cranks", preset, [3.2, 0.8, -0.6], [0, 0.6, -0.4]]];
    for (const [vl, p, cp, la] of views) {
      applyPreset(g.scene, p);
      cam.position.set(...cp); cam.lookAt(...la); renderer.render(scene, cam);
      frames.push({ label: label + ": " + vl, url: renderer.domElement.toDataURL("image/png") });
    }
    scene.remove(g.scene);
  }
  window.__frames = frames;
  out.ok = out.problems.length === 0;
} catch (e) { out.error = String(e && e.stack || e); }
window.__result = out;
</script></body></html>`;

const server = http.createServer((req, res) => {
  const u = decodeURIComponent(req.url.split("?")[0]);
  let file = null;
  if (u === "/" || u === "/index.html") { res.writeHead(200, { "Content-Type": "text/html" }); return res.end(page_html); }
  if (u === "/presets.json") { res.writeHead(200, { "Content-Type": "application/json" }); return res.end(JSON.stringify(presets)); }
  if (u === "/model.glb") file = glb;
  else if (u === "/orig.glb") file = origGlb;
  else if (u.startsWith("/three/")) file = path.join(GAME, u.slice(1));
  if (!file || !fs.existsSync(file)) { res.writeHead(404); return res.end(); }
  res.writeHead(200, { "Content-Type": types[path.extname(file)] || "application/octet-stream" });
  fs.createReadStream(file).pipe(res);
});
await new Promise(r => server.listen(0, "127.0.0.1", r));
const port = server.address().port;
const browser = await puppeteer.launch({ headless: true, args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader"] });
const page = await browser.newPage();
page.on("console", m => { if (m.type() === "error") console.log("[page]", m.text()); });
await page.goto(`http://127.0.0.1:${port}/`);
await page.waitForFunction("window.__result", { timeout: 180000 });
const result = await page.evaluate(() => window.__result);
const frames = await page.evaluate(() => window.__frames || []);
if (frames.length) {
  const per = frames.length / 2;
  const sheet = await page.evaluate(async (fr, per) => {
    const imgs = await Promise.all(fr.map(f => new Promise(r => { const i = new Image(); i.onload = () => r(i); i.src = f.url; })));
    const c = document.createElement("canvas"); c.width = 480 * per; c.height = 300 * 2;
    const g = c.getContext("2d"); imgs.forEach((im, k) => { const col = k % per, row = Math.floor(k / per);
      g.drawImage(im, col * 480, row * 300); g.fillStyle = "#000"; g.font = "18px sans-serif";
      g.fillText(fr[k].label, col * 480 + 10, row * 300 + 24); });
    return c.toDataURL("image/png");
  }, frames, per);
  fs.writeFileSync(shot, Buffer.from(sheet.split(",")[1], "base64"));
  result.screenshot = shot;
}
console.log("BIKECHECK", JSON.stringify(result, null, 1));
await browser.close();
server.close();
process.exit(result.ok ? 0 : 1);
