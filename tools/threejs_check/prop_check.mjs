// Static prop GLB in headless Chrome with the GAME's three.js: studio environment (RoomEnvironment PMREM), ACES,
// sRGB, a key light; one row of turntable views stitched into a PNG + basic stats (tris, materials, extensions).
//
//   node tools/threejs_check/prop_check.mjs out/props/ketchup/ketchup_lod0.glb [renders/x.png] [yaws=0,35,90,180]
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
const shot = path.resolve(ROOT, process.argv[3] || "renders/prop_threejs.png");
const yaws = (process.argv[4] || "0,35,90,180").split(",").map(Number);

const html = `<!doctype html><html><body style="margin:0;background:#888">
<script type="importmap">{"imports":{"three":"/three/build/three.module.js","three/addons/":"/three/examples/jsm/"}}</script>
<script type="module">
import * as THREE from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { RoomEnvironment } from "three/addons/environments/RoomEnvironment.js";
const out = { three: THREE.REVISION };
try {
  const gltf = await new GLTFLoader().loadAsync("/model.glb");
  const W = 400, H = 560;
  const renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true });
  renderer.setSize(W, H); renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.outputColorSpace = THREE.SRGBColorSpace; document.body.appendChild(renderer.domElement);
  const scene = new THREE.Scene(); scene.background = new THREE.Color(0x9a9ea6);
  scene.environment = new THREE.PMREMGenerator(renderer).fromScene(new RoomEnvironment(), 0.04).texture;
  const key = new THREE.DirectionalLight(0xffffff, 1.6); key.position.set(1, 2, 2); scene.add(key);
  scene.add(gltf.scene);
  const box = new THREE.Box3().setFromObject(gltf.scene), c = box.getCenter(new THREE.Vector3()), s = box.getSize(new THREE.Vector3());
  let tris = 0; const mats = new Set();
  gltf.scene.traverse(o => { if (o.isMesh) { tris += (o.geometry.index ? o.geometry.index.count : o.geometry.attributes.position.count) / 3; mats.add(o.material.name); } });
  Object.assign(out, { tris, materials: [...mats], size_m: s.toArray().map(v => +v.toFixed(4)),
    extensions: gltf.parser.json.extensionsUsed || [] });
  const cam = new THREE.PerspectiveCamera(30, W / H, 0.01, 10);
  const dist = s.y * 1.05 / (2 * Math.tan(Math.PI * 15 / 180)) + s.z;
  const frames = [];
  for (const y of ${JSON.stringify(yaws)}) {
    const a = y * Math.PI / 180;           // glTF: front = +Z (Blender -Y)
    cam.position.set(c.x + Math.sin(a) * dist, c.y + s.y * 0.12, c.z + Math.cos(a) * dist); cam.lookAt(c);
    renderer.render(scene, cam); frames.push(renderer.domElement.toDataURL("image/png"));
  }
  const cv = document.createElement("canvas"); cv.width = W * frames.length; cv.height = H;
  const ctx = cv.getContext("2d");
  for (let i = 0; i < frames.length; i++) { const im = new Image(); im.src = frames[i]; await im.decode(); ctx.drawImage(im, i * W, 0); }
  out.png = cv.toDataURL("image/png");
} catch (e) { out.error = String(e.stack || e); }
window.__result = out;
</script></body></html>`;

const types = { ".js": "text/javascript", ".mjs": "text/javascript", ".glb": "model/gltf-binary", ".html": "text/html" };
const server = http.createServer((req, res) => {
  const u = decodeURIComponent(req.url.split("?")[0]);
  let f = null;
  if (u === "/") { res.writeHead(200, { "content-type": "text/html" }); return res.end(html); }
  if (u === "/model.glb") f = glb;
  else if (u.startsWith("/three/")) f = path.join(GAME, u);
  if (!f || !fs.existsSync(f)) { res.writeHead(404); return res.end(); }
  res.writeHead(200, { "content-type": types[path.extname(f)] || "application/octet-stream" });
  fs.createReadStream(f).pipe(res);
});
await new Promise(r => server.listen(0, "127.0.0.1", r));
const browser = await puppeteer.launch({ headless: true, args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader"] });
const page = await browser.newPage();
await page.goto(`http://127.0.0.1:${server.address().port}/`);
await page.waitForFunction(() => window.__result, { timeout: 120000 });
const result = await page.evaluate(() => window.__result);
if (result.png) { fs.mkdirSync(path.dirname(shot), { recursive: true }); fs.writeFileSync(shot, Buffer.from(result.png.split(",")[1], "base64")); delete result.png; result.screenshot = shot; }
console.log(JSON.stringify(result, null, 1));
await browser.close();
server.close();
