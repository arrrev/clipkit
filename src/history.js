'use strict';
const T = window.ClipKitTransforms;

let items = [];
let filter = 'all';
let query = '';

const listEl = document.getElementById('list');
const emptyEl = document.getElementById('empty');
const searchEl = document.getElementById('search');

function matchesFilter(it) {
  if (filter === 'all') return true;
  if (filter === 'image') return it.type === 'image';
  if (it.type === 'image') return false;
  const types = T.detectType(it.text);
  if (filter === 'json') return types.has('json') || types.has('json_string');
  if (filter === 'sql') return types.has('sql') || types.has('sql_in');
  if (filter === 'csv') return types.has('csv');
  if (filter === 'text') {
    return !(types.has('json') || types.has('json_string') ||
             types.has('sql') || types.has('sql_in') || types.has('csv'));
  }
  return true;
}

function fuzzyMatch(text, q) {
  if (!q) return true;
  const t = text.toLowerCase();
  let ti = 0;
  for (let qi = 0; qi < q.length; qi++) {
    ti = t.indexOf(q[qi], ti);
    if (ti === -1) return false;
    ti++;
  }
  return true;
}

function render() {
  listEl.innerHTML = '';
  const q = query.trim().toLowerCase();
  const visible = items.filter(it =>
    matchesFilter(it) && (it.type === 'image' ? !q : fuzzyMatch(it.text, q))
  );

  if (visible.length === 0) {
    emptyEl.style.display = 'block';
    emptyEl.textContent = items.length === 0 ? 'No clipboard items yet.' : 'No matches.';
    return;
  }
  emptyEl.style.display = 'none';

  for (const it of visible) {
    listEl.appendChild(makeRow(it));
  }
}

function selectedRow() { return listEl.querySelector('.row.selected'); }

function selectRow(row) {
  const prev = selectedRow();
  if (prev) prev.classList.remove('selected');
  if (row) { row.classList.add('selected'); row.scrollIntoView({ block: 'nearest' }); }
}

function makeRow(it) {
  const isImage = it.type === 'image';
  const row = document.createElement('div');
  row.className = 'row';
  row.tabIndex = -1;
  row.addEventListener('click', () => selectRow(row));

  const head = document.createElement('div');
  head.className = 'row-head';

  const badgeType = isImage ? 'Image' : T.primaryType(it.text);
  const badge = document.createElement('span');
  badge.className = 'badge ' + badgeType;
  badge.textContent = badgeType;
  head.appendChild(badge);

  const pin = document.createElement('button');
  pin.className = 'pin-btn' + (it.pinnedAt ? ' pinned' : '');
  pin.title = it.pinnedAt ? 'Unpin' : 'Pin';
  pin.textContent = it.pinnedAt ? '📌' : '📍';
  pin.addEventListener('click', async () => {
    if (isImage) items = await window.clipkit.togglePinImage(it.imageHash);
    else items = await window.clipkit.togglePin(it.text);
    render();
  });
  head.appendChild(pin);
  row.appendChild(head);

  if (isImage) {
    const img = document.createElement('img');
    img.className = 'img-thumb';
    img.src = `clipkit://images/${it.imageHash}.png`;
    img.alt = 'Clipboard image';
    row.appendChild(img);
  } else {
    const preview = document.createElement('div');
    preview.className = 'preview';
    const truncated = it.text.length > 400;
    preview.textContent = truncated ? it.text.slice(0, 400) + '…' : it.text;
    if (truncated) preview.title = it.text.slice(0, 1000) + (it.text.length > 1000 ? '…' : '');
    row.appendChild(preview);
  }

  const actions = document.createElement('div');
  actions.className = 'actions';

  const copyBtn = document.createElement('button');
  copyBtn.className = 'act primary';
  copyBtn.textContent = 'Copy';
  copyBtn.addEventListener('click', async () => {
    if (isImage) await window.clipkit.copyImage(it.imageHash);
    else await window.clipkit.copy(it.text);
    copyBtn.textContent = 'Copied ✓';
    setTimeout(() => { copyBtn.textContent = 'Copy'; }, 900);
  });
  actions.appendChild(copyBtn);

  if (!isImage) {
    const transformBtn = document.createElement('button');
    transformBtn.className = 'act';
    transformBtn.textContent = 'Transform';
    transformBtn.addEventListener('click', () => window.clipkit.transformFrom(it.text));
    actions.appendChild(transformBtn);
  }

  const delBtn = document.createElement('button');
  delBtn.className = 'act danger';
  delBtn.textContent = 'Delete';
  delBtn.addEventListener('click', async () => {
    if (isImage) items = await window.clipkit.deleteImage(it.imageHash);
    else items = await window.clipkit.deleteItem(it.text);
    render();
  });
  actions.appendChild(delBtn);

  row.appendChild(actions);
  return row;
}

// tabs
document.getElementById('tabs').addEventListener('click', (e) => {
  const btn = e.target.closest('.tab');
  if (!btn) return;
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  btn.classList.add('active');
  filter = btn.dataset.filter;
  query = '';
  searchEl.value = '';
  render();
});

searchEl.addEventListener('input', () => { query = searchEl.value; render(); });

document.addEventListener('keydown', async (e) => {
  if (e.key === 'Escape') { window.clipkit.hideWindow(); return; }

  const rows = Array.from(listEl.querySelectorAll('.row'));
  if (rows.length === 0) return;
  const cur = selectedRow();
  const idx = rows.indexOf(cur);

  if (e.key === 'ArrowDown') {
    e.preventDefault();
    selectRow(rows[idx + 1] || rows[0]);
  } else if (e.key === 'ArrowUp') {
    e.preventDefault();
    selectRow(idx <= 0 ? rows[rows.length - 1] : rows[idx - 1]);
  } else if (e.key === 'Enter' && cur) {
    e.preventDefault();
    const copyBtn = cur.querySelector('.act.primary');
    if (copyBtn) copyBtn.click();
  } else if (e.key === 'Delete' || e.key === 'Backspace' && e.metaKey) {
    if (cur && document.activeElement === document.body || document.activeElement === listEl) {
      e.preventDefault();
      const delBtn = cur.querySelector('.act.danger');
      if (delBtn) delBtn.click();
    }
  }
});

window.clipkit.onHistoryUpdate((newItems) => { items = newItems; render(); });

(async function init() {
  items = await window.clipkit.getHistory();
  render();
  searchEl.focus();
})();
