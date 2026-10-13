'use strict';

let settings = null;
let transformNames = [];

// ── tab nav ─────────────────────────────────────────────────────────────────
document.querySelector('.sidebar').addEventListener('click', (e) => {
  const btn = e.target.closest('.nav');
  if (!btn) return;
  document.querySelectorAll('.nav').forEach(n => n.classList.remove('active'));
  document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
  btn.classList.add('active');
  document.querySelector(`.tab-panel[data-panel="${btn.dataset.tab}"]`).classList.add('active');
});

// ── accelerator recording ───────────────────────────────────────────────────
// Convert a keydown event to an Electron accelerator string.
function eventToAccelerator(e) {
  const mods = [];
  if (e.metaKey) mods.push('Command');
  if (e.ctrlKey) mods.push('Control');
  if (e.altKey) mods.push('Alt');
  if (e.shiftKey) mods.push('Shift');

  let key = e.key;
  if (['Meta', 'Control', 'Alt', 'Shift'].includes(key)) return null; // modifier alone

  if (key === ' ') key = 'Space';
  else if (key.length === 1) key = key.toUpperCase();
  else if (/^F\d+$/.test(key)) { /* keep */ }
  else if (key === 'ArrowUp') key = 'Up';
  else if (key === 'ArrowDown') key = 'Down';
  else if (key === 'ArrowLeft') key = 'Left';
  else if (key === 'ArrowRight') key = 'Right';
  else if (key === 'Escape') return null;

  if (mods.length === 0) return null; // require at least one modifier
  return mods.concat(key).join('+');
}

function acceleratorToDisplay(accel) {
  if (!accel) return 'None';
  return accel
    .replace('CmdOrCtrl', '⌘')
    .replace('CommandOrControl', '⌘')
    .replace('Command', '⌘')
    .replace('Cmd', '⌘')
    .replace('Control', '⌃')
    .replace('Ctrl', '⌃')
    .replace('Alt', '⌥')
    .replace('Shift', '⇧')
    .replace(/\+/g, '');
}

function allUsedHotkeys(excludeKey, excludeTransform) {
  const used = [];
  ['hotkeyOpen', 'hotkeyTransform', 'hotkeyPastePrev'].forEach(k => {
    if (settings[k] && excludeKey !== k) used.push(settings[k]);
  });
  const hks = settings.transformHotkeys || {};
  Object.entries(hks).forEach(([n, v]) => { if (n !== excludeTransform && v) used.push(v); });
  return used;
}

function recordInto(button, onDone, conflictExcludeKey, conflictExcludeTransform) {
  if (button._recording) return;
  button._recording = true;
  button.classList.add('recording');
  const original = button.textContent;
  button.textContent = 'Press keys…';

  function handler(e) {
    e.preventDefault();
    e.stopPropagation();
    if (e.key === 'Escape') { cleanup(); button.textContent = original; return; }
    const accel = eventToAccelerator(e);
    if (!accel) return; // wait for a full combo
    const used = allUsedHotkeys(conflictExcludeKey, conflictExcludeTransform);
    if (used.includes(accel)) {
      button.textContent = '⚠ Already used!';
      setTimeout(() => { button.textContent = 'Press keys…'; }, 1200);
      return;
    }
    cleanup();
    onDone(accel);
  }
  function cleanup() {
    button._recording = false;
    button.classList.remove('recording');
    window.removeEventListener('keydown', handler, true);
  }
  window.addEventListener('keydown', handler, true);
}

// ── general ─────────────────────────────────────────────────────────────────
function bindGeneral() {
  const launch = document.getElementById('launch');
  const maxItems = document.getElementById('maxItems');
  const maxBuffer = document.getElementById('maxBuffer');
  const maxItemsVal = document.getElementById('maxItemsVal');
  const maxBufferVal = document.getElementById('maxBufferVal');

  launch.checked = !!settings.launchAtLogin;
  maxItems.value = settings.maxItems;
  maxBuffer.value = settings.maxBufferMB;
  maxItemsVal.textContent = settings.maxItems;
  maxBufferVal.textContent = settings.maxBufferMB + ' MB';

  launch.addEventListener('change', () => save({ launchAtLogin: launch.checked }));
  maxItems.addEventListener('input', () => { maxItemsVal.textContent = maxItems.value; });
  maxItems.addEventListener('change', () => save({ maxItems: parseInt(maxItems.value, 10) }));
  maxBuffer.addEventListener('input', () => { maxBufferVal.textContent = maxBuffer.value + ' MB'; });
  maxBuffer.addEventListener('change', () => save({ maxBufferMB: parseInt(maxBuffer.value, 10) }));
}

// ── transforms (reorder + enable + per-transform hotkey) ─────────────────────
function orderedNames() {
  const order = settings.transformOrder || [];
  const seen = new Set();
  const out = [];
  order.forEach(n => { if (transformNames.includes(n) && !seen.has(n)) { out.push(n); seen.add(n); } });
  transformNames.forEach(n => { if (!seen.has(n)) out.push(n); });
  return out;
}

function renderTransforms() {
  const ul = document.getElementById('transformList');
  ul.innerHTML = '';
  const hidden = new Set(settings.hiddenTransforms || []);
  const hotkeys = settings.transformHotkeys || {};

  orderedNames().forEach(name => {
    const li = document.createElement('li');
    li.className = 'titem';
    li.draggable = true;
    li.dataset.name = name;

    const grip = document.createElement('span');
    grip.className = 'grip'; grip.textContent = '⋮⋮';
    li.appendChild(grip);

    const cb = document.createElement('input');
    cb.type = 'checkbox';
    cb.checked = !hidden.has(name);
    cb.addEventListener('change', () => {
      const h = new Set(settings.hiddenTransforms || []);
      if (cb.checked) h.delete(name); else h.add(name);
      save({ hiddenTransforms: Array.from(h) });
    });
    li.appendChild(cb);

    const label = document.createElement('span');
    label.className = 'tname'; label.textContent = name;
    li.appendChild(label);

    const hk = document.createElement('button');
    hk.className = 'thk';
    hk.textContent = hotkeys[name] ? acceleratorToDisplay(hotkeys[name]) : 'Set';
    hk.addEventListener('click', (e) => {
      e.stopPropagation();
      recordInto(hk, (accel) => {
        const map = Object.assign({}, settings.transformHotkeys);
        map[name] = accel;
        save({ transformHotkeys: map });
      }, null, name);
    });
    // right-click clears
    hk.addEventListener('contextmenu', (e) => {
      e.preventDefault();
      const map = Object.assign({}, settings.transformHotkeys);
      delete map[name];
      save({ transformHotkeys: map });
    });
    li.appendChild(hk);

    ul.appendChild(li);
  });

  setupDragReorder(ul);
}

function setupDragReorder(ul) {
  let dragging = null;
  ul.querySelectorAll('.titem').forEach(li => {
    li.addEventListener('dragstart', () => { dragging = li; li.classList.add('dragging'); });
    li.addEventListener('dragend', () => {
      li.classList.remove('dragging');
      dragging = null;
      const newOrder = Array.from(ul.querySelectorAll('.titem')).map(x => x.dataset.name);
      save({ transformOrder: newOrder });
    });
    li.addEventListener('dragover', (e) => {
      e.preventDefault();
      if (!dragging || dragging === li) return;
      const rect = li.getBoundingClientRect();
      const after = (e.clientY - rect.top) > rect.height / 2;
      ul.insertBefore(dragging, after ? li.nextSibling : li);
    });
  });
}

// ── hotkeys tab ──────────────────────────────────────────────────────────────
function renderHotkeys() {
  document.querySelectorAll('.hk-record').forEach(btn => {
    const key = btn.dataset.key;
    btn.textContent = acceleratorToDisplay(settings[key]);
    btn.onclick = () => {
      recordInto(btn, (accel) => {
        const patch = {}; patch[key] = accel;
        save(patch);
      }, key, null);
    };
    btn.oncontextmenu = (e) => {
      e.preventDefault();
      const patch = {}; patch[key] = '';
      save(patch);
    };
  });
}

// ── persistence ──────────────────────────────────────────────────────────────
async function save(patch) {
  settings = await window.clipkit.setSettings(patch);
  // re-render dependent views
  renderHotkeys();
  renderTransforms();
}

document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape' && !document.querySelector('.recording')) window.clipkit.hideWindow();
});

window.clipkit.onSettingsLoad((s) => { settings = s; renderAll(); });

function renderAll() {
  bindGeneral();
  renderTransforms();
  renderHotkeys();
}

(async function init() {
  settings = await window.clipkit.getSettings();
  const list = await window.clipkit.getTransformList();
  transformNames = list.map(t => t.name);
  renderAll();
})();
