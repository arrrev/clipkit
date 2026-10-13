'use strict';
const T = window.ClipKitTransforms;

const inputEl = document.getElementById('input');
const outputEl = document.getElementById('output');
const selectEl = document.getElementById('select');
const applyBtn = document.getElementById('apply');
const swapBtn = document.getElementById('swap');
const pasteBtn = document.getElementById('paste');
const outBadge = document.getElementById('outBadge');
const statsEl = document.getElementById('stats');
const saveBtn = document.getElementById('save');

let settings = { hiddenTransforms: [], transformOrder: [] };

function refreshSelect() {
  const text = inputEl.value;
  const list = T.applicableTransforms(text, {
    hidden: settings.hiddenTransforms,
    order: settings.transformOrder
  });
  const prev = selectEl.value;
  selectEl.innerHTML = '';
  if (list.length === 0) {
    const opt = document.createElement('option');
    opt.textContent = text.trim() ? 'No applicable transforms' : 'Enter input first';
    opt.disabled = true;
    selectEl.appendChild(opt);
    applyBtn.disabled = true;
    return;
  }
  applyBtn.disabled = false;
  list.forEach(t => {
    const opt = document.createElement('option');
    opt.value = t.name; opt.textContent = t.name;
    selectEl.appendChild(opt);
  });
  if (list.some(t => t.name === prev)) selectEl.value = prev;
}

function setOutput(text) {
  outputEl.value = text;
  const type = T.primaryType(text);
  outBadge.className = 'badge ' + type;
  outBadge.textContent = type;
  const lines = text === '' ? 0 : text.split(/\r?\n/).length;
  statsEl.textContent = text ? `${text.length} chars · ${lines} line${lines === 1 ? '' : 's'}` : '';
  saveBtn.disabled = !text || text.startsWith('⚠ ');
}

async function apply() {
  const name = selectEl.value;
  if (!name) return;
  try {
    const result = T.applyByName(name, inputEl.value);
    setOutput(result);
    await window.clipkit.writeClipboard(result);
    applyBtn.textContent = 'Copied ✓';
    setTimeout(() => { applyBtn.textContent = 'Apply'; }, 900);
  } catch (e) {
    setOutput('⚠ ' + e.message);
  }
}

saveBtn.addEventListener('click', async () => {
  const text = outputEl.value;
  if (!text || text.startsWith('⚠ ')) return;
  const type = T.primaryType(text);
  const ext = type === 'JSON' ? 'json' : type === 'SQL' ? 'sql' : 'txt';
  const ok = await window.clipkit.saveOutput(text, ext);
  if (ok) {
    saveBtn.textContent = 'Saved ✓';
    setTimeout(() => { saveBtn.textContent = 'Save to file'; }, 1200);
  }
});

applyBtn.addEventListener('click', apply);

swapBtn.addEventListener('click', () => {
  const out = outputEl.value;
  if (!out || out.startsWith('⚠ ')) return;
  const prevSelect = selectEl.value;
  inputEl.value = out;
  setOutput('');
  refreshSelect();
  if (selectEl.querySelector(`option[value="${prevSelect}"]`)) selectEl.value = prevSelect;
  swapBtn.textContent = 'Swapped ✓';
  setTimeout(() => { swapBtn.textContent = '⇅ Swap'; }, 900);
});

pasteBtn.addEventListener('click', async () => {
  const text = await window.clipkit.readClipboard();
  inputEl.value = text || '';
  refreshSelect();
});

inputEl.addEventListener('input', () => {
  if (outputEl.value.startsWith('⚠ ')) setOutput('');
  refreshSelect();
});

document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') window.clipkit.hideWindow();
  if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') apply();
});

window.clipkit.onTransformSeed((text) => {
  inputEl.value = text || '';
  setOutput('');
  refreshSelect();
  inputEl.focus();
});

(async function init() {
  settings = await window.clipkit.getSettings();
  setOutput('');
  refreshSelect();
})();
