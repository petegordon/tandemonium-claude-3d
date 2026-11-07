// Animated GLB in headless Chrome with the GAME's three.js (RoomEnvironment, ACES, sRGB, key light): plays every clip
// at once (bike: Pedal + WheelSpin + TimeWarpFX), renders frames from a few camera views, writes an MP4 + GIF.
//
//   node tools/threejs_check/fx_anim.mjs out/time_warp/time_warp_tandem.glb renders/time_warp/fx [seconds=4] [fps=24]
//
// Views (glTF axes: +Y up, front = +Z): side (from the bike's left), rear 3/4 on the engines, clock close-up.
// Uses ../tandemonium/node_modules/{three,puppeteer} and ffmpeg on PATH; nothing in the game repo is modified.
import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import { execFileSync } from "node:child_process";
import { createRequire } from "node:module";

const ROOT = path.resolve(path.dirname(new URL(import.meta.url).pathname.replace(/^\/([A-Z]:)/, "$1")), "../..");
const GAME = path.resolve(ROOT, "../tandemonium/node_modules");
const require = createRequire(path.join(GAME, "puppeteer", "package.json"));
const puppeteer = require("puppeteer");
const glb = path.resolve(ROOT, process.argv[2]);
const outPrefix = path.resolve(ROOT, process.argv[3] || "renders/fx");
const SECS = +(process.argv[4] || 4), FPS = +(process.argv[5] || 24);
const W = 960, H = 540;

const html = `<!doctype html><html><body style="margin:0;background:#888">
<script type="importmap">{"imports":{"three":"/three/build/three.module.js","three/addons/":"/three/examples/jsm/"}}</script>
<script type="module">
import * as THREE from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { RoomEnvironment } from "three/addons/environments/RoomEnvironment.js";
const gltf = await new GLTFLoader().loadAsync("/model.glb");
const renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true });
renderer.setSize(${W}, ${H}); renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.outputColorSpace = THREE.SRGBColorSpace; document.body.appendChild(renderer.domElement);
const scene = new THREE.Scene(); scene.background = new THREE.Color(0xb8c4cf);
scene.environment = new THREE.PMREMGenerator(renderer).fromScene(new RoomEnvironment(), 0.04).texture;
const key = new THREE.DirectionalLight(0xffffff, 1.6); key.position.set(2, 3, 1); scene.add(key);
const ground = new THREE.Mesh(new THREE.PlaneGeometry(20, 20), new THREE.MeshStandardMaterial({ color: 0x9aa58a, roughness: 1 }));
ground.rotation.x = -Math.PI / 2; scene.add(ground);
scene.add(gltf.scene);
const mixer = new THREE.AnimationMixer(gltf.scene);
// like the game (goose-rider-clips.js): every clip carries every bone, so cut each one to the bones it owns
const OWN = { Pedal: /^(Crank|Pedal)_/, WheelSpin: /^Wheel_/, TimeWarpFX: /^(Clock|Flame)/ };
const actions = gltf.animations.map(c => {
  const cut = c.clone();
  const re = OWN[c.name];
  if (re) cut.tracks = cut.tracks.filter(t => re.test(t.name.slice(0, t.name.lastIndexOf("."))));
  const a = mixer.clipAction(cut); a.play(); return a;
});
const cam = new THREE.PerspectiveCamera(30, ${W} / ${H}, 0.01, 50);
const views = {
  side: { eye: [3.6, 0.75, 0.1], at: [0, 0.55, 0.1], fov: 34 },
  engines: { eye: [1.0, 0.95, -1.75], at: [0, 0.62, -0.95], fov: 34 },
  clock: { eye: [0.95, 0.75, -0.19], at: [0, 0.6, -0.19], fov: 28 },
};
window.__frame = (view, t) => {
  for (const a of actions) a.time = t % a.getClip().duration;
  mixer.update(0);
  const v = views[view];
  cam.fov = v.fov; cam.updateProjectionMatrix();
  cam.position.set(...v.eye); cam.lookAt(new THREE.Vector3(...v.at));
  renderer.render(scene, cam);
  return renderer.domElement.toDataURL("image/png");
};
window.__ready = gltf.animations.map(c => c.name + ":" + c.duration.toFixed(2));
</script></body></html>`;

const types = { ".js": "text/javascript", ".glb": "model/gltf-binary" };
const server = http.createServer((req, res) => {
  const u = decodeURIComponent(req.url.split("?")[0]);
  if (u === "/") { res.writeHead(200, { "content-type": "text/html" }); return res.end(html); }
  const f = u === "/model.glb" ? glb : u.startsWith("/three/") ? path.join(GAME, u) : null;
  if (!f || !fs.existsSync(f)) { res.writeHead(404); return res.end(); }
  res.writeHead(200, { "content-type": types[path.extname(f)] || "application/octet-stream" });
  fs.createReadStream(f).pipe(res);
});
await new Promise(r => server.listen(0, "127.0.0.1", r));
const browser = await puppeteer.launch({ headless: true, args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader"] });
const page = await browser.newPage();
page.on("pageerror", e => console.log("pageerror", String(e)));
await page.goto(`http://127.0.0.1:${server.address().port}/`);
await page.waitForFunction(() => window.__ready, { timeout: 120000 });
console.log("clips", await page.evaluate(() => window.__ready));
for (const view of ["side", "engines", "clock"]) {
  const dir = `${outPrefix}_${view}_frames`;
  fs.mkdirSync(dir, { recursive: true });
  for (let i = 0; i < SECS * FPS; i++) {
    const png = await page.evaluate((v, t) => window.__frame(v, t), view, i / FPS);
    fs.writeFileSync(path.join(dir, `f${String(i).padStart(4, "0")}.png`), Buffer.from(png.split(",")[1], "base64"));
  }
  execFileSync("ffmpeg", ["-y", "-loglevel", "error", "-framerate", String(FPS), "-i", path.join(dir, "f%04d.png"),
    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", `${outPrefix}_${view}.mp4`]);
  execFileSync("ffmpeg", ["-y", "-loglevel", "error", "-framerate", String(FPS), "-i", path.join(dir, "f%04d.png"),
    "-vf", "fps=15,scale=640:-1:flags=lanczos,split[a][b];[a]palettegen[p];[b][p]paletteuse", `${outPrefix}_${view}.gif`]);
  fs.copyFileSync(path.join(dir, "f0000.png"), `${outPrefix}_${view}.png`);
  console.log("wrote", `${outPrefix}_${view}.mp4`);
}
await browser.close();
server.close();
