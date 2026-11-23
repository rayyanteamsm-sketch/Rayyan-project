// Minimal Chrome DevTools Protocol driver for headless Edge (Node 22+ global WebSocket).
// usage: node tests/e2e/browser/cdp.mjs http://127.0.0.1:8000/#/dashboard 1440 1000 tests/e2e/browser/ui_flows.js
// (start the server first: run.bat --no-browser). BROWSER_PATH overrides the Edge/Chrome path. SHOT=file.png saves a screenshot.
// usage: node cdp.mjs <url> <width> <height> <script.js>   — script body is evaluated in the page (async allowed), result printed as JSON
import { spawn } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

const [url, w = "1440", h = "900", scriptFile] = process.argv.slice(2);
const edge = process.env.BROWSER_PATH || ["C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe", "C:/Program Files/Google/Chrome/Application/chrome.exe"].find((p) => fs.existsSync(p));
const port = 9300 + Math.floor(Math.random() * 500);
const prof = fs.mkdtempSync(path.join(os.tmpdir(), "edgecdp-"));
const proc = spawn(edge, ["--headless=new", "--disable-gpu", `--remote-debugging-port=${port}`, `--user-data-dir=${prof}`, `--window-size=${w},${h}`, "--force-prefers-reduced-motion", "about:blank"], { stdio: "ignore" });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let targets;
for (let i = 0; i < 60; i++) { try { targets = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json(); if (targets.find((t) => t.type === "page")) break; } catch { } await sleep(250); }
const page = targets.find((t) => t.type === "page");
const ws = new WebSocket(page.webSocketDebuggerUrl);
await new Promise((r) => ws.addEventListener("open", r));
let id = 0; const pending = new Map(); const logs = [];
ws.addEventListener("message", (ev) => {
  const m = JSON.parse(ev.data);
  if (m.id && pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id); }
  if (m.method === "Runtime.consoleAPICalled" && ["error", "warning"].includes(m.params.type)) logs.push(`${m.params.type}: ${m.params.args.map((a) => a.value ?? a.description).join(" ")}`);
  if (m.method === "Runtime.exceptionThrown") logs.push("exception: " + (m.params.exceptionDetails.exception?.description ?? m.params.exceptionDetails.text));
  if (m.method === "Network.responseReceived" && m.params.response.status >= 400) logs.push(`http ${m.params.response.status}: ${m.params.response.url}`);
});
const send = (method, params = {}) => new Promise((r) => { const i = ++id; pending.set(i, r); ws.send(JSON.stringify({ id: i, method, params })); });
await send("Runtime.enable"); await send("Network.enable"); await send("Page.enable");
// BLOCK="*fonts.googleapis.com*,*fonts.gstatic.com*" يحاكي عدم وجود إنترنت للموارد الخارجية
if (process.env.BLOCK) await send("Network.setBlockedURLs", { urls: process.env.BLOCK.split(",") });
if (+w < 600) await send("Emulation.setDeviceMetricsOverride", { width: +w, height: +h, deviceScaleFactor: 1, mobile: true });
await send("Page.navigate", { url });
await sleep(4000);
const body = fs.readFileSync(scriptFile, "utf8");
const res = await send("Runtime.evaluate", { expression: `(async () => { ${body} })()`, awaitPromise: true, returnByValue: true });
if (process.env.SHOT) {
  await sleep(800);
  const shot = await send("Page.captureScreenshot", { format: "png", captureBeyondViewport: true, clip: { x: 0, y: 0, width: +w, height: +h, scale: 1 } });
  fs.writeFileSync(process.env.SHOT, Buffer.from(shot.result.data, "base64"));
}
console.log(JSON.stringify({ result: res.result?.result?.value ?? res.result?.exceptionDetails?.exception?.description, logs }, null, 1));
ws.close(); proc.kill();
process.exit(0);
