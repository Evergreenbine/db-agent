// electron/main.cjs — Electron bootstrap for 小e (数据库执行智能体) web frontend.
// Loads the Next.js dev server at http://localhost:3000. If the dev server is
// not already running, spawns `npm run dev`, waits for it, then loads it.
// On window close the spawned dev server is cleaned up.
const { app, BrowserWindow, Menu } = require("electron");
const { spawn } = require("child_process");
const path = require("path");

const DEV_URL = "http://localhost:3000";
const WEB_DIR = path.join(__dirname, "..");
const PROXY = "http://127.0.0.1:7892";

let mainWindow = null;
let serverProc = null;

async function isDevUp() {
  try { await fetch(DEV_URL); return true; } catch { return false; }
}

async function waitForDev(maxMs = 60000) {
  const start = Date.now();
  while (Date.now() - start < maxMs) {
    if (await isDevUp()) return true;
    await new Promise((r) => setTimeout(r, 800));
  }
  return false;
}

function startDevServer() {
  const npm = process.platform === "win32" ? "npm.cmd" : "npm";
  serverProc = spawn(npm, ["run", "dev"], {
    cwd: WEB_DIR,
    shell: true,
    stdio: "inherit",
    env: { ...process.env, HTTPS_PROXY: PROXY, HTTP_PROXY: PROXY },
  });
  serverProc.on("exit", () => { serverProc = null; });
}

function killServer() {
  if (!serverProc) return;
  try {
    if (process.platform === "win32") {
      spawn("taskkill", ["/PID", String(serverProc.pid), "/T", "/F"], { shell: true });
    } else {
      serverProc.kill();
    }
  } catch (e) {
    console.error("[electron] stop dev server failed:", e);
  }
  serverProc = null;
}

app.whenReady().then(async () => {
  Menu.setApplicationMenu(null);
  if (!(await isDevUp())) {
    console.log("[electron] dev server not up, starting Next.js dev...");
    startDevServer();
    const ok = await waitForDev();
    if (!ok) console.error("[electron] dev server not ready within 60s");
  }
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 800,
    title: "小e · 数据库执行智能体",
    autoHideMenuBar: true,
    backgroundColor: "#0a0a0a",
    webPreferences: { contextIsolation: true, nodeIntegration: false },
  });
  mainWindow.loadURL(DEV_URL);
  mainWindow.on("closed", () => { mainWindow = null; });
});

app.on("window-all-closed", () => { killServer(); app.quit(); });
app.on("before-quit", () => killServer());
