// بناء واجهة ريّان: React + TypeScript (esbuild) و Tailwind CSS v4 (واجهة compile البرمجية).
// يعمل مع node_modules المحلي بعد `npm install`، أو مع حزم Node المثبتة عالميًا عبر NODE_PATH.
//   node frontend/build.mjs          بناء للإنتاج في frontend/dist
//   node frontend/build.mjs --watch  إعادة البناء عند التعديل
import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath, pathToFileURL } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const dist = path.join(here, "dist");
const assets = path.join(dist, "assets");
const searchPaths = [path.join(here, "node_modules"), ...(process.env.NODE_PATH || "").split(path.delimiter).filter(Boolean),
  "/opt/npm-tools/node_modules"];
const req = createRequire(path.join(here, "package.json"));
function resolvePkg(name) {
  for (const base of searchPaths) {
    const p = path.join(base, name);
    if (fs.existsSync(p)) return p;
  }
  try { return path.dirname(req.resolve(name + "/package.json")); } catch { /* */ }
  throw new Error(`الحزمة ${name} غير موجودة. شغّلي: cd frontend && npm install`);
}
const esbuild = await import(pathToFileURL(path.join(resolvePkg("esbuild"), "lib/main.js")).href);
const twDir = resolvePkg("tailwindcss");
const { compile } = await import(pathToFileURL(path.join(twDir, "dist/lib.mjs")).href);

const SRC_DIRS = ["src", "components", "pages", "services"].map((d) => path.join(here, d));
function walk(dir) {
  return fs.existsSync(dir) ? fs.readdirSync(dir, { withFileTypes: true }).flatMap((e) =>
    e.isDirectory() ? walk(path.join(dir, e.name)) : [path.join(dir, e.name)]) : [];
}

async function buildCss() {
  const input = fs.readFileSync(path.join(here, "src/styles.css"), "utf8");
  const compiler = await compile(input, {
    base: here,
    loadStylesheet: async (id, base) => {
      const p = id === "tailwindcss" ? path.join(twDir, "index.css") : path.resolve(base, id);
      return { path: p, base: path.dirname(p), content: fs.readFileSync(p, "utf8") };
    },
  });
  // استخراج المرشحين من ملفات المصدر (بديل الماسح الأصلي غير المتاح دون oxide)
  const candidates = new Set();
  for (const f of SRC_DIRS.flatMap(walk).filter((f) => /\.(tsx?|html)$/.test(f))) {
    for (const tok of fs.readFileSync(f, "utf8").split(/[\s"'`{}()<>,;=]+/)) {
      if (/^[!-]?[a-z@\[][a-zA-Z0-9:\-\[\]\/\.#%_!&>+*]*$/.test(tok) && tok.length < 80) candidates.add(tok);
    }
  }
  return compiler.build([...candidates]);
}

async function buildAll() {
  fs.mkdirSync(assets, { recursive: true });
  const t0 = Date.now();
  await esbuild.build({
    entryPoints: [path.join(here, "src/main.tsx")],
    bundle: true, minify: true, sourcemap: false, format: "esm", target: ["es2020"],
    outfile: path.join(assets, "app.js"), jsx: "automatic", nodePaths: searchPaths,
    define: { "process.env.NODE_ENV": '"production"' }, logLevel: "warning",
  });
  fs.writeFileSync(path.join(assets, "app.css"), await buildCss());
  fs.copyFileSync(path.join(here, "src/index.html"), path.join(dist, "index.html"));
  for (const f of walk(path.join(here, "assets"))) fs.copyFileSync(f, path.join(assets, path.basename(f)));
  const kb = (f) => (fs.statSync(path.join(assets, f)).size / 1024).toFixed(0);
  console.log(`✓ بُنيت الواجهة في ${Date.now() - t0}ms — app.js ${kb("app.js")}KB، app.css ${kb("app.css")}KB`);
}

await buildAll();
if (process.argv.includes("--watch")) {
  console.log("المراقبة مفعلة…");
  for (const d of SRC_DIRS) fs.watch(d, { recursive: true }, () => buildAll().catch((e) => console.error(e.message)));
}
