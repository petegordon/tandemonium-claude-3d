// Riding test harness: static server for tools/ride_harness/index.html + the local out/ GLBs.
//
//   node tools/ride_harness/serve.mjs [port]      -> http://127.0.0.1:8190/
//
// three.js r161 comes from the CDN (same version as the game); nothing from the game repo is used.
import http from "node:http";
import fs from "node:fs";
import path from "node:path";

const ROOT = path.resolve(path.dirname(new URL(import.meta.url).pathname.replace(/^\/([A-Z]:)/, "$1")), "../..");
const port = +(process.argv[2] || 8190);
const types = { ".html": "text/html", ".js": "text/javascript", ".mjs": "text/javascript", ".json": "application/json",
  ".glb": "model/gltf-binary", ".png": "image/png" };
http.createServer((req, res) => {
  let u = decodeURIComponent(req.url.split("?")[0]);
  if (u === "/") u = "/tools/ride_harness/index.html";
  const file = path.resolve(ROOT, "." + u);
  if (!file.startsWith(ROOT) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) { res.writeHead(404); return res.end(); }
  res.writeHead(200, { "Content-Type": types[path.extname(file)] || "application/octet-stream", "Cache-Control": "no-store" });
  fs.createReadStream(file).pipe(res);
}).listen(port, "127.0.0.1", () => console.log(`ride harness: http://127.0.0.1:${port}/`));
