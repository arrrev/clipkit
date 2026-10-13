'use strict';

const {
  app, BrowserWindow, Tray, Menu, globalShortcut,
  clipboard, ipcMain, nativeImage, shell, dialog, protocol, net
} = require('electron');
const path = require('path');
const fs = require('fs');
const os = require('os');
const crypto = require('crypto');

// Register privileged scheme before app is ready
protocol.registerSchemesAsPrivileged([
  { scheme: 'clipkit', privileges: { secure: true, standard: true, supportFetchAPI: true } }
]);

const T = require('./src/transforms');

// ── paths ──────────────────────────────────────────────────────────────────
const DATA_DIR = path.join(os.homedir(), '.clipkit');
const SETTINGS_FILE = path.join(DATA_DIR, 'settings.json');
const HISTORY_FILE = path.join(DATA_DIR, 'history.json');
const BOUNDS_FILE = path.join(DATA_DIR, 'bounds.json');
const IMAGES_DIR = path.join(DATA_DIR, 'images');

function loadBounds() {
  try { return JSON.parse(fs.readFileSync(BOUNDS_FILE, 'utf8')); } catch (e) { return {}; }
}
function saveBounds(key, win) {
  if (!win || win.isDestroyed() || win.isMinimized()) return;
  const all = loadBounds();
  all[key] = win.getBounds();
  try { fs.writeFileSync(BOUNDS_FILE, JSON.stringify(all, null, 2)); } catch (e) {}
}
function applyBounds(key, win, defaults) {
  const all = loadBounds();
  const b = all[key];
  if (b) win.setBounds(b);
}

function ensureDir() {
  try { fs.mkdirSync(DATA_DIR, { recursive: true }); } catch (e) {}
  try { fs.mkdirSync(IMAGES_DIR, { recursive: true }); } catch (e) {}
}

// ── settings ────────────────────────────────────────────────────────────────
const DEFAULT_SETTINGS = {
  maxItems: 200,
  maxBufferMB: 50,
  launchAtLogin: false,
  hotkeyOpen: 'CmdOrCtrl+Alt+V',
  hotkeyTransform: 'CmdOrCtrl+Alt+T',
  hotkeyPastePrev: 'Command+Control+V',
  hiddenTransforms: [],
  transformOrder: [],
  transformHotkeys: {}
};

let settings = Object.assign({}, DEFAULT_SETTINGS);

function loadSettings() {
  ensureDir();
  try {
    const data = JSON.parse(fs.readFileSync(SETTINGS_FILE, 'utf8'));
    settings = Object.assign({}, DEFAULT_SETTINGS, data);
  } catch (e) {
    settings = Object.assign({}, DEFAULT_SETTINGS);
  }
  return settings;
}

function saveSettings() {
  ensureDir();
  try { fs.writeFileSync(SETTINGS_FILE, JSON.stringify(settings, null, 2)); } catch (e) {}
}

// ── history ─────────────────────────────────────────────────────────────────
// Text item:  { text, pinnedAt: number|null, createdAt: number }
// Image item: { type: 'image', imageHash, imagePath, pinnedAt, createdAt }
let history = [];

function loadHistory() {
  ensureDir();
  try {
    const data = JSON.parse(fs.readFileSync(HISTORY_FILE, 'utf8'));
    if (Array.isArray(data)) {
      history = data.filter(it => {
        if (!it) return false;
        if (it.type === 'image') return it.imageHash && fs.existsSync(it.imagePath);
        return typeof it.text === 'string';
      });
    }
  } catch (e) { history = []; }
}

function saveHistory() {
  ensureDir();
  try { fs.writeFileSync(HISTORY_FILE, JSON.stringify(history, null, 2)); } catch (e) {}
}

// Sort: pinned first (newest pin first), then unpinned newest-first.
function sortedHistory() {
  const pinned = history.filter(i => i.pinnedAt).sort((a, b) => b.pinnedAt - a.pinnedAt);
  const rest = history.filter(i => !i.pinnedAt).sort((a, b) => b.createdAt - a.createdAt);
  return pinned.concat(rest);
}

function enforceLimits() {
  const pinned = history.filter(i => i.pinnedAt);
  let rest = history.filter(i => !i.pinnedAt).sort((a, b) => b.createdAt - a.createdAt);

  const maxUnpinned = Math.max(0, settings.maxItems - pinned.length);
  const evicted = rest.splice(maxUnpinned);
  evicted.forEach(i => { if (i.type === 'image') deleteImageFile(i.imagePath); });

  const maxBytes = settings.maxBufferMB * 1024 * 1024;
  let total = rest.reduce((s, i) => s + (i.type === 'image' ? 0 : Buffer.byteLength(i.text, 'utf8')), 0);
  while (total > maxBytes && rest.length > 0) {
    const removed = rest.pop();
    if (removed.type === 'image') deleteImageFile(removed.imagePath);
    else total -= Buffer.byteLength(removed.text, 'utf8');
  }
  history = pinned.concat(rest);
}

function deleteImageFile(filePath) {
  try { fs.unlinkSync(filePath); } catch (e) {}
}

function addClip(text) {
  if (!text || !text.trim()) return false;
  // dedupe against most recent (any position) — move existing to top
  const existingIdx = history.findIndex(i => i.text === text);
  if (existingIdx !== -1) {
    const it = history[existingIdx];
    it.createdAt = Date.now();
    enforceLimits();
    saveHistory();
    pushHistoryToWindows();
    return true;
  }
  history.unshift({ text, pinnedAt: null, createdAt: Date.now() });
  enforceLimits();
  saveHistory();
  pushHistoryToWindows();
  return true;
}

// ── windows ──────────────────────────────────────────────────────────────────
let tray = null;
let historyWin = null;
let transformWin = null;
let settingsWin = null;

const COMMON = {
  show: false,
  frame: true,
  fullscreenable: false,
  resizable: true,
  webPreferences: {
    preload: path.join(__dirname, 'preload.js'),
    contextIsolation: true,
    nodeIntegration: false
  }
};

function attachCrashRecovery(win, file) {
  win.webContents.on('render-process-gone', (_e, details) => {
    if (!app.isQuitting) win.loadFile(file);
  });
  win.webContents.on('did-fail-load', (_e, code) => {
    if (!app.isQuitting && code !== -3) win.loadFile(file); // -3 = aborted (normal hide)
  });
}

// Hide a window when it loses focus, but only if no other ClipKit window gained focus.
function attachBlurHide(win) {
  win.on('blur', () => {
    if (app.isQuitting) return;
    // Small delay so focus can transfer to another ClipKit window first.
    setTimeout(() => {
      const wins = [historyWin, transformWin, settingsWin];
      const anyFocused = wins.some(w => w && !w.isDestroyed() && w.isFocused());
      if (!anyFocused) wins.forEach(w => { if (w && !w.isDestroyed()) w.hide(); });
    }, 100);
  });
}

function createHistoryWindow() {
  historyWin = new BrowserWindow(Object.assign({
    width: 500, height: 600, minWidth: 380, minHeight: 400, title: 'ClipKit — History'
  }, COMMON));
  const histFile = path.join(__dirname, 'src', 'history.html');
  historyWin.loadFile(histFile);
  attachCrashRecovery(historyWin, histFile);
  applyBounds('history', historyWin);
  historyWin.on('resize', () => saveBounds('history', historyWin));
  historyWin.on('moved', () => saveBounds('history', historyWin));
  historyWin.on('close', (e) => { if (!app.isQuitting) { e.preventDefault(); historyWin.hide(); } });
  attachBlurHide(historyWin);
}

function createTransformWindow() {
  transformWin = new BrowserWindow(Object.assign({
    width: 600, height: 500, minWidth: 460, minHeight: 380, title: 'ClipKit — Transform'
  }, COMMON));
  const transFile = path.join(__dirname, 'src', 'transform.html');
  transformWin.loadFile(transFile);
  attachCrashRecovery(transformWin, transFile);
  applyBounds('transform', transformWin);
  transformWin.on('resize', () => saveBounds('transform', transformWin));
  transformWin.on('moved', () => saveBounds('transform', transformWin));
  transformWin.on('close', (e) => { if (!app.isQuitting) { e.preventDefault(); transformWin.hide(); } });
  attachBlurHide(transformWin);
}

function createSettingsWindow() {
  settingsWin = new BrowserWindow(Object.assign({
    width: 620, height: 520, minWidth: 560, minHeight: 440, title: 'ClipKit — Settings'
  }, COMMON));
  const settFile = path.join(__dirname, 'src', 'settings.html');
  settingsWin.loadFile(settFile);
  attachCrashRecovery(settingsWin, settFile);
  applyBounds('settings', settingsWin);
  settingsWin.on('resize', () => saveBounds('settings', settingsWin));
  settingsWin.on('moved', () => saveBounds('settings', settingsWin));
  settingsWin.on('close', (e) => { if (!app.isQuitting) { e.preventDefault(); settingsWin.hide(); } });
  attachBlurHide(settingsWin);
}

function showWindow(win, boundsKey) {
  if (!win) return;
  const savedBounds = boundsKey && loadBounds()[boundsKey];
  if (!savedBounds) win.center();
  win.show();
  win.focus();
}

function showHistory() {
  if (!historyWin) createHistoryWindow();
  showWindow(historyWin, 'history');
  pushHistoryToWindows();
}

function showTransform(seedText) {
  if (!transformWin) createTransformWindow();
  showWindow(transformWin, 'transform');
  const seed = (seedText !== undefined && seedText !== null) ? seedText : clipboard.readText();
  transformWin.webContents.send('transform:seed', seed || '');
}

function showSettings() {
  if (!settingsWin) createSettingsWindow();
  showWindow(settingsWin, 'settings');
  settingsWin.webContents.send('settings:load', settings);
}

function pushHistoryToWindows() {
  if (historyWin && !historyWin.isDestroyed()) {
    historyWin.webContents.send('history:update', sortedHistory());
  }
}

// ── clipboard monitor ─────────────────────────────────────────────────────────
let lastClipText = null;
let lastClipImageHash = null;
let monitorTimer = null;

function imageHash(img) {
  const buf = img.toPNG();
  if (!buf || buf.length === 0) return null;
  return crypto.createHash('sha256').update(buf).digest('hex').slice(0, 24);
}

function addClipImage(img, hash) {
  const existing = history.find(i => i.type === 'image' && i.imageHash === hash);
  if (existing) {
    existing.createdAt = Date.now();
  } else {
    ensureDir();
    const fname = hash + '.png';
    const fpath = path.join(IMAGES_DIR, fname);
    try { fs.writeFileSync(fpath, img.toPNG()); } catch (e) { return; }
    history.unshift({ type: 'image', imageHash: hash, imagePath: fpath, pinnedAt: null, createdAt: Date.now() });
  }
  enforceLimits();
  saveHistory();
  pushHistoryToWindows();
}

// Pasteboard types that tell clipboard managers to stay away (password managers,
// auto-generated content). See nspasteboard.org.
const SKIP_TYPES = [
  'org.nspasteboard.TransientType',
  'org.nspasteboard.ConcealedType',
  'org.nspasteboard.AutoGeneratedType'
];
const IMAGE_TYPES = ['public.png', 'public.tiff', 'public.jpeg', 'public.heic'];

// Read the clipboard contents ONCE, only after macOS reports a change.
// Reading the contents on a timer forces Universal Clipboard (iPhone <-> Mac)
// items to be resolved over and over, which breaks Handoff copy/paste.
function readClipboardChange(types) {
  if (types && types.some(t => SKIP_TYPES.includes(t))) return;

  let text = '';
  try { text = clipboard.readText(); } catch (e) { return; }

  if (text) {
    if (text === lastClipText) return;
    lastClipText = text;
    lastClipImageHash = null;
    if (text.trim()) addClip(text);
    return;
  }

  // No text — check for image (skip the read entirely if no image type is on the board)
  if (types && !types.some(t => IMAGE_TYPES.includes(t))) return;
  let img;
  try { img = clipboard.readImage(); } catch (e) { return; }
  if (!img || img.isEmpty()) return;
  const hash = imageHash(img);
  if (!hash || hash === lastClipImageHash) return;
  lastClipImageHash = hash;
  lastClipText = null;
  addClipImage(img, hash);
}

// A tiny JXA helper that watches NSPasteboard.changeCount (cheap, never touches
// the clipboard data) and prints "<changeCount>\t<types>" whenever it changes.
// It exits by itself if ClipKit dies (parent pid becomes 1).
const PB_WATCHER_JXA = `
ObjC.import('AppKit');
ObjC.import('unistd');
var pb = $.NSPasteboard.generalPasteboard;
var last = pb.changeCount;
while ($.getppid() !== 1) {
  var c = pb.changeCount;
  if (c !== last) {
    last = c;
    var types = ObjC.deepUnwrap(pb.types) || [];
    console.log(c + '\\t' + types.join(','));
  }
  delay(0.3);
}
`;

let pbWatcher = null;
let pbWatcherRestarts = 0;
let pendingReadTimer = null;

function startPasteboardWatcher() {
  const { spawn } = require('child_process');
  let proc;
  try {
    proc = spawn('/usr/bin/osascript', ['-l', 'JavaScript', '-e', PB_WATCHER_JXA], { stdio: ['ignore', 'ignore', 'pipe'] });
  } catch (e) { return false; }
  pbWatcher = proc;

  let buf = '';
  proc.stderr.setEncoding('utf8');
  proc.stderr.on('data', (chunk) => {
    buf += chunk;
    let nl;
    while ((nl = buf.indexOf('\n')) !== -1) {
      const line = buf.slice(0, nl);
      buf = buf.slice(nl + 1);
      const tab = line.indexOf('\t');
      if (tab === -1) continue;
      pbWatcherRestarts = 0;
      const types = line.slice(tab + 1).split(',').filter(Boolean);
      // Small delay so the copying app / Universal Clipboard finishes writing first.
      clearTimeout(pendingReadTimer);
      pendingReadTimer = setTimeout(() => readClipboardChange(types), 150);
    }
  });

  proc.on('exit', () => {
    if (pbWatcher !== proc) return;
    pbWatcher = null;
    if (app.isQuitting) return;
    if (++pbWatcherRestarts <= 5) {
      setTimeout(startPasteboardWatcher, 1000);
    } else {
      startFallbackPolling();
    }
  });
  proc.on('error', () => {});
  return true;
}

// Fallback only if the watcher can't run: poll, but slowly.
function startFallbackPolling() {
  if (monitorTimer) return;
  monitorTimer = setInterval(() => readClipboardChange(null), 1500);
}

function stopMonitor() {
  if (monitorTimer) { clearInterval(monitorTimer); monitorTimer = null; }
  clearTimeout(pendingReadTimer);
  if (pbWatcher) { const p = pbWatcher; pbWatcher = null; try { p.kill(); } catch (e) {} }
}

function startMonitor() {
  try { lastClipText = clipboard.readText(); } catch (e) {}
  if (process.platform !== 'darwin' || !startPasteboardWatcher()) startFallbackPolling();
}

// copy without re-recording it as a "new" external clip (it's already in history)
function copyToClipboard(text) {
  clipboard.writeText(text);
  lastClipText = text;
}

// ── tray ──────────────────────────────────────────────────────────────────────
function scissorsImage() {
  // Generate a 22x22 PNG for the tray using raw pixel data
  // Simple scissors shape encoded as a 1x1 transparent placeholder — we use setTitle instead
  return nativeImage.createEmpty();
}

function buildTrayImage() {
  const file = path.join(__dirname, 'assets', 'trayTemplate.png');
  let img = nativeImage.createFromPath(file);
  if (img.isEmpty()) {
    img = scissorsImage(); // built-in fallback so the menu-bar icon always renders
  }
  if (!img.isEmpty()) {
    img = img.resize({ width: 18, height: 18 });
    img.setTemplateImage(true);
  }
  return img;
}

function fmtAccel(a) {
  return (a || '').replace('CmdOrCtrl', '⌘').replace('Command', '⌘').replace('Control', '⌃').replace('Ctrl', '⌃').replace('Alt', '⌥').replace('Shift', '⇧').replace(/\+/g, '');
}

function buildTrayMenu() {
  const hkOpen = fmtAccel(settings.hotkeyOpen);
  const hkTrans = fmtAccel(settings.hotkeyTransform);
  const hkPrev = fmtAccel(settings.hotkeyPastePrev);
  return Menu.buildFromTemplate([
    { label: 'Show History   ' + hkOpen, click: () => showHistory() },
    { label: 'Transform Text   ' + hkTrans, click: () => showTransform() },
    { label: 'Paste Previous   ' + hkPrev, click: () => {
      const sorted = sortedHistory();
      const current = sorted[0];
      const prev = sorted[1];
      if (!prev) return;
      clipboard.writeText(prev.text);
      lastClipText = prev.text;
      setTimeout(() => {
        const { exec } = require('child_process');
        exec(`osascript -e 'tell application "System Events" to keystroke "v" using command down'`, () => {
          if (current) setTimeout(() => { clipboard.writeText(current.text); lastClipText = current.text; }, 100);
        });
      }, 150);
    }},
    { type: 'separator' },
    { label: 'Settings…', click: () => showSettings() },
    { type: 'separator' },
    { label: 'Clear History', click: () => { clearHistory(); } },
    { type: 'separator' },
    { label: 'Quit ClipKit', click: () => { app.isQuitting = true; app.quit(); } }
  ]);
}

function refreshTray() {
  if (tray) tray.setContextMenu(buildTrayMenu());
}

function clearHistory() {
  history.forEach(i => { if (!i.pinnedAt && i.type === 'image') deleteImageFile(i.imagePath); });
  history = history.filter(i => i.pinnedAt); // keep pinned
  saveHistory();
  pushHistoryToWindows();
}

function createTray() {
  // Use a 1x1 transparent PNG as base image; setTitle provides the visible ✂ text
  const img = nativeImage.createFromDataURL(
    'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=='
  );
  tray = new Tray(img);
  tray.setTitle('✂');
  tray.setToolTip('ClipKit');
  refreshTray();
}

// ── hotkeys ─────────────────────────────────────────────────────────────────
function registerHotkeys() {
  globalShortcut.unregisterAll();

  try { globalShortcut.register(settings.hotkeyOpen, () => showHistory()); } catch (e) {}
  try { globalShortcut.register(settings.hotkeyTransform, () => showTransform()); } catch (e) {}
  if (settings.hotkeyPastePrev) {
    try {
      globalShortcut.register(settings.hotkeyPastePrev, () => {
        const sorted = sortedHistory();
        const current = sorted[0]; // save current clipboard
        const prev = sorted[1];    // the one to paste
        if (!prev) return;
        // Write prev to clipboard temporarily for the paste
        clipboard.writeText(prev.text);
        lastClipText = prev.text; // prevent monitor from recording it
        setTimeout(() => {
          const { exec } = require('child_process');
          exec(`osascript -e 'tell application "System Events" to keystroke "v" using command down'`, () => {
            // Restore original clipboard so history order is unchanged
            if (current) {
              setTimeout(() => {
                clipboard.writeText(current.text);
                lastClipText = current.text;
              }, 100);
            }
          });
        }, 150);
      });
    } catch (e) {}
  }

  // per-transform hotkeys: apply transform directly to clipboard
  Object.keys(settings.transformHotkeys || {}).forEach(name => {
    const accel = settings.transformHotkeys[name];
    if (!accel) return;
    try {
      globalShortcut.register(accel, () => {
        const text = clipboard.readText();
        if (!text || !text.trim()) return;
        try {
          const result = T.applyByName(name, text);
          copyToClipboard(result);
        } catch (e) { /* ignore failed transform */ }
      });
    } catch (e) {}
  });
}

// ── launch at login ───────────────────────────────────────────────────────────
function applyLoginItem() {
  try {
    app.setLoginItemSettings({ openAtLogin: !!settings.launchAtLogin, openAsHidden: true });
  } catch (e) {}
}

// ── IPC ─────────────────────────────────────────────────────────────────────
ipcMain.handle('history:get', () => sortedHistory());

ipcMain.handle('history:copy', (_e, text) => { copyToClipboard(text); return true; });

ipcMain.handle('history:copyImage', (_e, hash) => {
  const img = nativeImage.createFromPath(path.join(IMAGES_DIR, hash + '.png'));
  if (!img.isEmpty()) {
    clipboard.writeImage(img);
    lastClipImageHash = hash;
    lastClipText = null;
  }
  return true;
});

ipcMain.handle('history:togglePin', (_e, text) => {
  const it = history.find(i => i.text === text);
  if (it) it.pinnedAt = it.pinnedAt ? null : Date.now();
  saveHistory();
  pushHistoryToWindows();
  return sortedHistory();
});

ipcMain.handle('history:togglePinImage', (_e, hash) => {
  const it = history.find(i => i.type === 'image' && i.imageHash === hash);
  if (it) it.pinnedAt = it.pinnedAt ? null : Date.now();
  saveHistory();
  pushHistoryToWindows();
  return sortedHistory();
});

ipcMain.handle('history:delete', (_e, text) => {
  history = history.filter(i => i.text !== text);
  saveHistory();
  pushHistoryToWindows();
  return sortedHistory();
});

ipcMain.handle('history:deleteImage', (_e, hash) => {
  const idx = history.findIndex(i => i.type === 'image' && i.imageHash === hash);
  if (idx !== -1) {
    deleteImageFile(history[idx].imagePath);
    history.splice(idx, 1);
  }
  saveHistory();
  pushHistoryToWindows();
  return sortedHistory();
});

ipcMain.handle('history:clear', () => { clearHistory(); return sortedHistory(); });

ipcMain.handle('history:transform', (_e, text) => { showTransform(text); return true; });

ipcMain.handle('clipboard:read', () => clipboard.readText());
ipcMain.handle('clipboard:write', (_e, text) => { copyToClipboard(text); return true; });

ipcMain.handle('settings:get', () => settings);

ipcMain.handle('settings:set', (_e, patch) => {
  const p = patch || {};
  if ('maxItems' in p) p.maxItems = Math.max(10, Math.min(2000, parseInt(p.maxItems, 10) || 200));
  if ('maxBufferMB' in p) p.maxBufferMB = Math.max(1, Math.min(500, parseInt(p.maxBufferMB, 10) || 50));
  settings = Object.assign({}, settings, p);
  saveSettings();
  applyLoginItem();
  registerHotkeys();
  refreshTray();
  enforceLimits();
  saveHistory();
  pushHistoryToWindows();
  return settings;
});

ipcMain.handle('settings:transforms', () => T.TRANSFORMS.map(t => ({ name: t.name })));

ipcMain.handle('output:save', async (e, text, ext) => {
  const win = BrowserWindow.fromWebContents(e.sender);
  const { filePath } = await dialog.showSaveDialog(win, {
    defaultPath: `output.${ext}`,
    filters: [
      ext === 'json' ? { name: 'JSON', extensions: ['json'] } :
      ext === 'sql'  ? { name: 'SQL',  extensions: ['sql']  } :
                       { name: 'Text', extensions: ['txt']  }
    ]
  });
  if (!filePath) return false;
  fs.writeFileSync(filePath, text, 'utf8');
  return true;
});

ipcMain.handle('window:hide', (e) => {
  const win = BrowserWindow.fromWebContents(e.sender);
  if (win) win.hide();
});

// ── app lifecycle ──────────────────────────────────────────────────────────────
const gotLock = app.requestSingleInstanceLock();
if (!gotLock) {
  app.quit();
} else {
  app.on('second-instance', () => { showHistory(); });

  app.whenReady().then(() => {
    // Serve local image files for the history renderer
    protocol.handle('clipkit', (request) => {
      const url = new URL(request.url);
      const fname = path.basename(url.pathname);
      const filePath = path.join(IMAGES_DIR, fname);
      try {
        const data = fs.readFileSync(filePath);
        return new Response(data, { headers: { 'Content-Type': 'image/png' } });
      } catch (e) {
        return new Response('Not found', { status: 404 });
      }
    });

    if (process.platform === 'darwin' && app.dock) {
      const dockIcon = nativeImage.createFromPath(path.join(__dirname, 'assets', 'icon.icns'));
      if (!dockIcon.isEmpty()) app.dock.setIcon(dockIcon);
      app.dock.hide();
    }

    loadSettings();
    loadHistory();
    enforceLimits();

    createTray();
    createHistoryWindow();
    createTransformWindow();
    createSettingsWindow();

    registerHotkeys();
    applyLoginItem();
    startMonitor();
  });

  app.on('window-all-closed', (e) => { /* keep running as menu-bar app */ });
  app.on('before-quit', () => { app.isQuitting = true; });
  app.on('will-quit', () => { globalShortcut.unregisterAll(); stopMonitor(); });
}
