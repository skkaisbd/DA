/**
 * static_server.js — zero-dependency SPA static file server.
 *
 * Serves the production build in ./build on 0.0.0.0:$PORT (default 3000).
 * Used INSTEAD of the CRA/webpack dev server because this container is capped
 * at 1 CPU core / 2GB RAM, where the ~5-minute dev compile of 567 files
 * saturates the CPU and gets the whole pod restarted by the platform health
 * probe (see /app/memory/PREVIEW_STABLE_MODE.md).
 *
 * This server starts in <1s, uses ~30MB RAM, and never compiles anything, so
 * the health probe always passes and the preview stays up (even after wake).
 *
 * SPA fallback: unknown non-file routes return build/index.html (the app uses
 * client-side, state-based navigation).
 *
 * ROBUSTNESS: headers are only written once (on stream "open"), so a read
 * error never triggers a double writeHead (which previously crashed the
 * process with ERR_HTTP_HEADERS_SENT and caused a supervisor restart loop
 * whenever build/ was missing).
 */
const http = require("http");
const fs = require("fs");
const path = require("path");
const { spawn } = require("child_process");

const PORT = parseInt(process.env.PORT || "3000", 10);
const HOST = process.env.HOST || "0.0.0.0";
const ROOT = path.join(__dirname, "build");

// ─── AUTO-BUILD (self-heal) ───────────────────────────────────────────────────
// TEMUAN 2026-08-10: di container ini `frontend/build/` **TIDAK bertahan** melewati
// restart/wake pod (ia gitignored; hanya berkas terlacak + node_modules yang
// dipulihkan). Akibatnya setiap kali pod bangun, preview hanya menampilkan
// "Preparing preview…" sampai ada agen yang menjalankan `yarn build` MANUAL —
// dari sisi pemilik aplikasi itu sama dengan preview RUSAK.
// Karena itu server ini sekarang MENYEMBUHKAN DIRI: kalau `build/index.html`
// tidak ada, `yarn build` dijalankan otomatis di latar belakang (prioritas
// rendah supaya health-probe backend tetap terjawab), sementara halaman
// "Preparing preview…" me-refresh sendiri tiap 10 detik sampai bundel siap.
const BUILD_LOCK = path.join(__dirname, ".autobuild.lock");
const BUILD_LOG = path.join(__dirname, "autobuild.log");
const LOCK_STALE_MS = 15 * 60 * 1000;
let autoBuilding = false;

function ensureBuild(reason) {
  if (autoBuilding) return;
  if (fs.existsSync(path.join(ROOT, "index.html"))) return;
  // Lock: jangan pernah menjalankan dua build sekaligus (1 build sudah berat).
  try {
    const st = fs.statSync(BUILD_LOCK);
    if (Date.now() - st.mtimeMs < LOCK_STALE_MS) {
      autoBuilding = true;
      return;
    }
  } catch (_) {
    /* tidak ada lock — lanjut */
  }
  autoBuilding = true;
  try { fs.writeFileSync(BUILD_LOCK, String(process.pid)); } catch (_) {}
  console.log(`[static_server] build/ tidak ada (${reason}) → auto-build dimulai…`);
  let out;
  try { out = fs.openSync(BUILD_LOG, "a"); } catch (_) { out = "ignore"; }
  try {
    const child = spawn("nice", ["-n", "19", "yarn", "build"], {
      cwd: __dirname,
      detached: true,
      stdio: ["ignore", out, out],
    });
    child.on("exit", (code) => {
      autoBuilding = false;
      try { fs.unlinkSync(BUILD_LOCK); } catch (_) {}
      console.log(`[static_server] auto-build selesai (exit ${code}).`);
    });
    child.on("error", (e) => {
      autoBuilding = false;
      try { fs.unlinkSync(BUILD_LOCK); } catch (_) {}
      console.error("[static_server] auto-build gagal dijalankan:", e && e.message);
    });
    child.unref();
  } catch (e) {
    autoBuilding = false;
    try { fs.unlinkSync(BUILD_LOCK); } catch (_) {}
    console.error("[static_server] auto-build gagal:", e && e.message);
  }
}

const MIME = {
  ".html": "text/html; charset=utf-8",
  ".js": "application/javascript; charset=utf-8",
  ".mjs": "application/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".map": "application/json; charset=utf-8",
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".gif": "image/gif",
  ".webp": "image/webp",
  ".ico": "image/x-icon",
  ".woff": "font/woff",
  ".woff2": "font/woff2",
  ".ttf": "font/ttf",
  ".eot": "application/vnd.ms-fontobject",
  ".txt": "text/plain; charset=utf-8",
  ".webmanifest": "application/manifest+json",
};

// Minimal HTML shown when build/ is missing (fresh clone before first build).
// Auto-refreshes so the preview lights up the moment the build lands.
const BUILDING_HTML =
  "<!doctype html><html><head><meta charset='utf-8'>" +
  "<meta http-equiv='refresh' content='10'>" +
  "<title>Preparing preview…</title>" +
  "<style>body{font-family:system-ui,sans-serif;background:#0f172a;color:#e2e8f0;" +
  "display:flex;align-items:center;justify-content:center;height:100vh;margin:0}" +
  ".c{text-align:center}.s{width:36px;height:36px;border:4px solid #334155;" +
  "border-top-color:#38bdf8;border-radius:50%;margin:0 auto 16px;animation:r 1s linear infinite}" +
  "@keyframes r{to{transform:rotate(360deg)}}</style></head>" +
  "<body><div class='c'><div class='s'></div>" +
  "<h2>Preparing preview…</h2><p>The static bundle is being built. This page refreshes automatically.</p>" +
  "</div></body></html>";

function endPlain(res, status, body) {
  if (res.headersSent) {
    try { res.destroy(); } catch (_) {}
    return;
  }
  res.writeHead(status, { "Content-Type": "text/plain; charset=utf-8", "Cache-Control": "no-cache" });
  res.end(body);
}

function endHtml(res, status, body) {
  if (res.headersSent) {
    try { res.destroy(); } catch (_) {}
    return;
  }
  res.writeHead(status, { "Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-cache" });
  res.end(body);
}

// Stream a file. Headers are written ONLY after the stream opens successfully,
// so any error results in a clean fallback (no double writeHead).
function serveFile(res, filePath, status = 200) {
  const ext = path.extname(filePath).toLowerCase();
  const type = MIME[ext] || "application/octet-stream";
  const stream = fs.createReadStream(filePath);

  stream.on("open", () => {
    res.writeHead(status, { "Content-Type": type, "Cache-Control": "no-cache" });
    stream.pipe(res);
  });

  stream.on("error", () => {
    // File missing or unreadable → SPA fallback / friendly page.
    if (res.headersSent) {
      try { res.destroy(); } catch (_) {}
      return;
    }
    const indexPath = path.join(ROOT, "index.html");
    if (filePath !== indexPath) {
      // Try index.html as SPA fallback.
      return serveIndexOrBuilding(res, 200);
    }
    // index.html itself missing → build not ready yet.
    endHtml(res, 200, BUILDING_HTML);
  });
}

function serveIndexOrBuilding(res, status) {
  const indexPath = path.join(ROOT, "index.html");
  fs.stat(indexPath, (err, stat) => {
    if (!err && stat.isFile()) return serveFile(res, indexPath, status);
    // Bundel belum ada → pastikan build berjalan, lalu tampilkan halaman tunggu
    // yang me-refresh sendiri (preview menyembuhkan diri tanpa campur tangan).
    ensureBuild("permintaan halaman saat bundel belum ada");
    endHtml(res, 200, BUILDING_HTML);
  });
}

const server = http.createServer((req, res) => {
  try {
    let urlPath = decodeURIComponent((req.url || "/").split("?")[0]);
    if (urlPath.includes("..")) urlPath = "/"; // path traversal guard

    // Root or directory → index.html (or building page).
    if (urlPath === "/" || urlPath.endsWith("/")) {
      return serveIndexOrBuilding(res, 200);
    }

    const filePath = path.join(ROOT, urlPath);
    fs.stat(filePath, (err, stat) => {
      if (!err && stat.isFile()) return serveFile(res, filePath);
      // No such file: routes without extension → SPA fallback (client routing).
      if (!path.extname(urlPath)) return serveIndexOrBuilding(res, 200);
      // Missing asset with extension → 404 (still index as ultimate fallback).
      serveIndexOrBuilding(res, 200);
    });
  } catch (e) {
    endPlain(res, 500, "Server error");
  }
});

// Never let an unexpected error take the whole process down.
server.on("clientError", (err, socket) => {
  try { socket.end("HTTP/1.1 400 Bad Request\r\n\r\n"); } catch (_) {}
});
process.on("uncaughtException", (err) => {
  console.error("[static_server] uncaughtException:", err && err.message);
});

// EADDRINUSE hardening (2026-07-25): saat `supervisorctl restart frontend`
// (dipakai `scripts/rebuild_frontend.sh`) proses LAMA kadang belum melepas port
// 3000 ketika proses BARU mencoba listen. Dulu itu memicu uncaughtException →
// proses mati → supervisor restart lagi → preview 502 beberapa detik dan log
// penuh "EADDRINUSE". Sekarang: tunggu & coba lagi (maks ~30 detik) sehingga
// preview kembali melayani begitu port bebas, tanpa restart-loop.
let listenRetries = 0;
const MAX_LISTEN_RETRIES = 30;
server.on("error", (err) => {
  if (err && err.code === "EADDRINUSE" && listenRetries < MAX_LISTEN_RETRIES) {
    listenRetries += 1;
    console.warn(
      `[static_server] port ${PORT} masih dipakai proses lama — coba lagi ${listenRetries}/${MAX_LISTEN_RETRIES} dalam 1s`
    );
    setTimeout(() => server.listen(PORT, HOST), 1000);
    return;
  }
  console.error("[static_server] server error:", err && err.message);
});

server.listen(PORT, HOST, () => {
  console.log(`[static_server] serving ${ROOT} at http://${HOST}:${PORT}`);
  // Pod baru bangun & bundel hilang? Bangun ulang SEKARANG, jangan tunggu
  // seseorang membuka halaman (preview harus siap saat pemilik membukanya).
  ensureBuild("startup");
});
