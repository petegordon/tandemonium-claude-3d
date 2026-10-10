// P2.5: load a rigged goose GLB in headless Chrome with the GAME's three.js (from the
// tandemonium repo's node_modules), play every clip, verify bones move, screenshot each clip.
//
//   node tools/threejs_check/check.mjs out/base-goose/base_goose_rigged.glb [renders/threejs_check.png]
//
// Uses ../tandemonium/node_modules/{three,puppeteer}; nothing in that repo is modified.
import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";

const ROOT = path.resolve(path.dirname(new URL(import.meta.url).pathname.replace(/^\/([A-Z]:)/, "$1")), "../..");
const GAME = path.resolve(ROOT, "../tandemonium/node_modules");
const require = createRequire(path.join(GAME, "puppeteer", "package.json"));
const puppeteer = require("puppeteer");
const glb = path.resolve(ROOT, process.argv[2]);
const shot = path.resolve(ROOT, process.argv[3] || "renders/threejs_check.png");

const types = { ".js": "text/javascript", ".mjs": "text/javascript", ".glb": "model/gltf-binary", ".html": "text/html" };
const page_html = `<!doctype html><html><body style="margin:0;background:#888">
<script type="importmap">{"imports":{"three":"/three/build/three.module.js","three/addons/":"/three/examples/jsm/"}}</script>
<script type="module">
import * as THREE from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
const out = { three: THREE.REVISION };
try {
  const gltf = await new GLTFLoader().loadAsync("/model.glb");
  const scene = new THREE.Scene(); scene.background = new THREE.Color(0x888888);
  scene.add(new THREE.HemisphereLight(0xffffff, 0x444444, 2.0));
  const sun = new THREE.DirectionalLight(0xffffff, 2.0); sun.position.set(1, 2, 3); scene.add(sun);
  scene.add(gltf.scene);
  let skinned = 0, meshes = 0; const bones = new Set();
  gltf.scene.traverse(o => { if (o.isMesh) meshes++; if (o.isSkinnedMesh) { skinned++; o.skeleton.bones.forEach(b => bones.add(b.name)); } });
  out.meshes = meshes; out.skinned = skinned; out.bones = bones.size;
  out.clips = gltf.animations.map(c => ({ name: c.name, duration: +c.duration.toFixed(2), tracks: c.tracks.length }));
  const box = new THREE.Box3().setFromObject(gltf.scene); const size = box.getSize(new THREE.Vector3());
  out.height_m = +size.y.toFixed(3);
  const cam = new THREE.PerspectiveCamera(30, 1, 0.01, 50);
  const head = gltf.scene.getObjectByName("Head");
  const renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true });
  renderer.setSize(360, 480); document.body.appendChild(renderer.domElement);
  const mixer = new THREE.AnimationMixer(gltf.scene);
  out.motion = {};
  const frames = [];
  const snap = (label) => { renderer.render(scene, cam); frames.push({ label, url: renderer.domElement.toDataURL("image/png") }); };
  const hp = new THREE.Vector3(); head.getWorldPosition(hp);
  cam.position.set(hp.x + 0.55, hp.y + 0.05, hp.z + 0.75); cam.lookAt(hp.x, hp.y - 0.05, hp.z);
  mixer.update(0); snap("rest");
  for (const clip of gltf.animations) {
    mixer.stopAllAction();
    const act = mixer.clipAction(clip); act.reset().play();
    const before = {}; gltf.scene.traverse(o => { if (o.isBone) before[o.name] = o.quaternion.clone(); });
    mixer.setTime(clip.duration * (clip.name === "blink" ? 0.3 : 0.4));
    let moved = [];
    gltf.scene.traverse(o => { if (o.isBone && before[o.name] && before[o.name].angleTo(o.quaternion) > 0.01) moved.push(o.name); });
    out.motion[clip.name] = moved;
    snap(clip.name);
    act.stop();
  }
  out.ok = skinned > 0 && out.clips.length > 0 && Object.values(out.motion).every(m => m.length > 0);
  window.__frames = frames;
} catch (e) { out.error = String(e && e.stack || e); }
window.__result = out;
</script></body></html>`;

const server = http.createServer((req, res) => {
  const u = decodeURIComponent(req.url.split("?")[0]);
  let file = null;
  if (u === "/" || u === "/index.html") { res.writeHead(200, { "Content-Type": "text/html" }); return res.end(page_html); }
  if (u === "/model.glb") file = glb;
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
await page.waitForFunction("window.__result", { timeout: 120000 });
const result = await page.evaluate(() => window.__result);
const frames = await page.evaluate(() => window.__frames || []);
// stitch frames side by side via a canvas in the page
if (frames.length) {
  const stitched = await page.evaluate(async (fr) => {
    const imgs = await Promise.all(fr.map(f => new Promise(r => { const i = new Image(); i.onload = () => r(i); i.src = f.url; })));
    const c = document.createElement("canvas"); c.width = 360 * imgs.length; c.height = 480;
    const g = c.getContext("2d"); imgs.forEach((im, k) => { g.drawImage(im, k * 360, 0); g.fillStyle = "#fff";
      g.font = "20px sans-serif"; g.fillText(fr[k].label, k * 360 + 10, 26); });
    return c.toDataURL("image/png");
  }, frames);
  fs.writeFileSync(shot, Buffer.from(stitched.split(",")[1], "base64"));
  result.screenshot = shot;
}
console.log("THREEJS", JSON.stringify(result, null, 1));
await browser.close();
server.close();
process.exit(result.ok ? 0 : 1);
