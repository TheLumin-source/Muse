// The canvas: view transform, pointer interactions, rendering, drops.

import { api, mediaUrl, fs } from './api.js';
import { ask } from './dialogs.js';
import { storage } from './storage.js';
import {
  S, on, emit, els, wires, byId, select, deselect, selectedRoots,
  mutate, save, flush, checkpoint, uid, loadBoard,
} from './state.js';
import {
  create, centreOn, renderElement, place, layoutAllColumns, layoutColumn,
  enterEdit, exitEdit, isEditing, editingElement, tickLiveCards, COL,
} from './elements.js';

const stage = document.getElementById('stage');
const world = document.getElementById('world');
const layer = document.getElementById('layer');
const wireLayer = document.getElementById('wire-layer');
const marquee = document.getElementById('marquee');
const dropHint = document.getElementById('drop-hint');
const emptyHint = document.getElementById('empty-hint');
const filePicker = document.getElementById('file-input');

const nodes = new Map();
const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));

// Pointer capture keeps a drag alive outside the stage; it is not worth an
// exception when the pointer id has already gone away.
function capture(ev) {
  try { stage.setPointerCapture(ev.pointerId); } catch { /* fine without it */ }
}

// --- view ------------------------------------------------------------------

export function applyView() {
  const { x, y, zoom } = S.view;
  world.style.transform = `translate(${x}px, ${y}px) scale(${zoom})`;
  stage.style.backgroundSize = `${22 * zoom}px ${22 * zoom}px`;
  stage.style.backgroundPosition = `${x}px ${y}px`;
  emit('view');
}

export function screenToWorld(clientX, clientY) {
  const rect = stage.getBoundingClientRect();
  return {
    x: (clientX - rect.left - S.view.x) / S.view.zoom,
    y: (clientY - rect.top - S.view.y) / S.view.zoom,
  };
}

export function worldToScreen(x, y) {
  const rect = stage.getBoundingClientRect();
  return {
    x: x * S.view.zoom + S.view.x + rect.left,
    y: y * S.view.zoom + S.view.y + rect.top,
  };
}

export function centreOfView() {
  const rect = stage.getBoundingClientRect();
  return screenToWorld(rect.left + rect.width / 2, rect.top + rect.height / 2);
}

export function zoomAt(clientX, clientY, factor) {
  const rect = stage.getBoundingClientRect();
  const px = clientX - rect.left;
  const py = clientY - rect.top;
  const before = { x: (px - S.view.x) / S.view.zoom, y: (py - S.view.y) / S.view.zoom };
  S.view.zoom = clamp(S.view.zoom * factor, 0.15, 3);
  S.view.x = px - before.x * S.view.zoom;
  S.view.y = py - before.y * S.view.zoom;
  applyView();
  save();
}

export function zoomBy(factor) {
  const rect = stage.getBoundingClientRect();
  zoomAt(rect.left + rect.width / 2, rect.top + rect.height / 2, factor);
}

export function resetZoom() {
  const centre = centreOfView();
  S.view.zoom = 1;
  const rect = stage.getBoundingClientRect();
  S.view.x = rect.width / 2 - centre.x;
  S.view.y = rect.height / 2 - centre.y;
  applyView();
  save();
}

export function fitBoard() {
  const list = els();
  const rect = stage.getBoundingClientRect();
  if (!list.length) {
    S.view = { x: rect.width / 2, y: rect.height / 2, zoom: 1 };
    return applyView();
  }
  const minX = Math.min(...list.map((e) => e.x));
  const minY = Math.min(...list.map((e) => e.y));
  const maxX = Math.max(...list.map((e) => e.x + e.w));
  const maxY = Math.max(...list.map((e) => e.y + e.h));
  const pad = 70;
  const zoom = clamp(
    Math.min((rect.width - pad * 2) / (maxX - minX), (rect.height - pad * 2) / (maxY - minY)),
    0.15, 1.6,
  );
  S.view.zoom = zoom;
  S.view.x = rect.width / 2 - ((minX + maxX) / 2) * zoom;
  S.view.y = rect.height / 2 - ((minY + maxY) / 2) * zoom;
  applyView();
  save();
}

/** Drop new cards where you can see them, not on top of each other. */
export function freeSpotNear(point) {
  const spot = { ...point };
  const taken = () => els().some((e) => Math.abs(e.x - spot.x) < 24 && Math.abs(e.y - spot.y) < 24);
  let guard = 0;
  while (taken() && guard < 40) { spot.x += 28; spot.y += 28; guard += 1; }
  return spot;
}

// --- rendering -------------------------------------------------------------

export function render(detail = {}) {
  if (!S.board) return;
  layoutAllColumns();
  exitEdit();
  layer.textContent = '';
  nodes.clear();

  // Columns paint first so their children sit above them.
  const ordered = [...els()].sort((a, b) => (a.type === 'column' ? 0 : 1) - (b.type === 'column' ? 0 : 1));
  ordered.forEach((el) => {
    const node = renderElement(el);
    nodes.set(el.id, node);
    layer.appendChild(node);
  });

  emptyHint.hidden = els().length > 0;
  drawWires();
  paintSelection();

  if (detail.focus) {
    const node = nodes.get(detail.focus.el);
    const field = node && node.querySelector(`[data-edit="${detail.focus.field}"]`);
    if (node) enterEdit(node, field);
  }
}

function nodeOf(id) {
  return nodes.get(id);
}

export function paintSelection() {
  nodes.forEach((node, id) => node.classList.toggle('sel', S.sel.has(id)));
  wireLayer.querySelectorAll('g').forEach((g) => g.classList.toggle('sel', g.dataset.id === S.selWire));
  emit('rails');   // the left rail swaps between add-tools and card actions
}

/** Float a toolbar above a card's top edge, flipping below the bottom edge when
 *  there is no room - so it never lands on top of the text you are editing. */
function floatToolbar(node, worldCX, worldTop, worldBottom) {
  const stageRect = stage.getBoundingClientRect();
  const topPt = worldToScreen(worldCX, worldTop);
  const botPt = worldToScreen(worldCX, worldBottom);
  node.hidden = false;
  const h = node.offsetHeight || 40;
  const gap = 12;
  const maxY = stageRect.height - h - 8;
  let y = topPt.y - stageRect.top - gap - h;      // sit above the card
  node.classList.remove('below');
  if (y < 8) {                                     // no room above: drop below
    y = botPt.y - stageRect.top + gap;
    node.classList.add('below');
  }
  // Keep it on screen even for cards taller than the viewport.
  y = clamp(y, 8, Math.max(8, maxY));
  node.style.left = `${clamp(topPt.x - stageRect.left, 120, stageRect.width - 120)}px`;
  node.style.top = `${y}px`;
}

on('selection', paintSelection);

// --- formatting toolbar ----------------------------------------------------

const fmtTools = document.getElementById('fmttools');
const FORMATTABLE = ['note', 'text', 'todo'];

function positionFmtTools() {
  const el = editingElement();
  if (!el || !FORMATTABLE.includes(el.type)) { fmtTools.hidden = true; return; }
  floatToolbar(fmtTools, el.x + el.w / 2, el.y, el.y + el.h);
}

on('edit-start', positionFmtTools);
on('edit-end', () => { fmtTools.hidden = true; });
on('view', () => { if (!fmtTools.hidden) positionFmtTools(); });

export async function applyFormat(command) {
  const field = document.activeElement;
  if (!field || !field.dataset.edit) return;
  // Emit semantic <b>/<i>/<u> tags instead of inline style spans: cleaner HTML
  // that survives save/reload and exports well.
  try { document.execCommand('styleWithCSS', false, false); } catch { /* older engines */ }
  if (command === 'color') {
    return openTextColors(field);
  }
  if (command === 'link') {
    // Keep the selection alive across the dialog: asking loses the caret.
    const selection = getSelection();
    const range = selection.rangeCount ? selection.getRangeAt(0).cloneRange() : null;
    const url = await ask('Link to', '', 'Add link');
    if (!url) return;
    field.focus();
    if (range) { selection.removeAllRanges(); selection.addRange(range); }
    const href = /^\w+:/.test(url) ? url : `https://${url}`;
    if (getSelection().isCollapsed) document.execCommand('insertText', false, url);
    document.execCommand('createLink', false, href);
  } else {
    document.execCommand(command, false, null);
  }
  field.dispatchEvent(new Event('input', { bubbles: true }));
}

// --- text colour -----------------------------------------------------------

const textColors = document.getElementById('textcolors');
const TEXT_COLORS = [
  ['Default', ''], ['#d64545', 'Red'], ['#e08a1e', 'Orange'], ['#c9a227', 'Gold'],
  ['#3aa657', 'Green'], ['#1899a3', 'Teal'], ['#2f6fd0', 'Blue'],
  ['#8a5cf6', 'Purple'], ['#d63b8f', 'Pink'], ['#7a7266', 'Grey'],
];

function applyTextColor(field, hex, range) {
  field.focus();
  if (range) { const s = getSelection(); s.removeAllRanges(); s.addRange(range); }
  if (hex) {
    document.execCommand('styleWithCSS', false, true);   // -> <span style="color">
    document.execCommand('foreColor', false, hex);
    document.execCommand('styleWithCSS', false, false);
  } else {
    document.execCommand('removeFormat', false, null);   // back to default colour
  }
  // foreColor only recolours the text spans; a bullet or number marker takes its
  // colour from the <li> itself, so recolour every list item the selection
  // touches too. Otherwise the dots stay grey while the words turn colour.
  colorListMarkers(field, hex);
  field.dispatchEvent(new Event('input', { bubbles: true }));
}

/** Match list markers to the text colour for every <li> the selection covers. */
function colorListMarkers(field, hex) {
  const sel = getSelection();
  if (!sel.rangeCount) return;
  const range = sel.getRangeAt(0);
  field.querySelectorAll('li').forEach((li) => {
    if (range.intersectsNode(li)) li.style.color = hex || '';
  });
}

function openTextColors(field) {
  const selection = getSelection();
  const range = selection.rangeCount ? selection.getRangeAt(0).cloneRange() : null;
  textColors.textContent = '';
  TEXT_COLORS.forEach(([hex, name]) => {
    const sw = document.createElement('button');
    sw.className = 'tcsw' + (hex ? '' : ' tcdefault');
    sw.title = name;
    if (hex) sw.style.background = hex; else sw.textContent = 'A';
    sw.addEventListener('pointerdown', (ev) => ev.preventDefault());
    sw.addEventListener('click', () => {
      applyTextColor(field, hex, range);
      textColors.hidden = true;
    });
    textColors.appendChild(sw);
  });
  const btn = fmtTools.querySelector('[data-fmt="color"]');
  const stageRect = stage.getBoundingClientRect();
  const br = btn.getBoundingClientRect();
  textColors.hidden = false;
  textColors.style.left = `${br.left - stageRect.left}px`;
  textColors.style.top = `${br.bottom - stageRect.top + 4}px`;
}

fmtTools.addEventListener('pointerdown', (ev) => ev.preventDefault());  // keep the caret
fmtTools.querySelectorAll('[data-fmt]').forEach((button) => {
  button.addEventListener('click', () => applyFormat(button.dataset.fmt));
});
textColors.addEventListener('pointerdown', (ev) => ev.preventDefault());
on('edit-end', () => { textColors.hidden = true; });

// Links inside a note open when you are not editing it.
layer.addEventListener('click', (ev) => {
  const anchor = ev.target.closest('a');
  if (!anchor || ev.target.closest('.el.editing')) return;
  ev.preventDefault();
  window.open(anchor.href, '_blank', 'noopener');
});

// --- connectors ------------------------------------------------------------

const SVG_NS = 'http://www.w3.org/2000/svg';

function rectOf(end) {
  if (typeof end === 'string') {
    const el = byId(end);
    return el ? { x: el.x, y: el.y, w: el.w, h: el.h, cx: el.x + el.w / 2, cy: el.y + el.h / 2 } : null;
  }
  return { x: end.x, y: end.y, w: 0, h: 0, cx: end.x, cy: end.y };
}

function sideBetween(a, b) {
  const dx = b.cx - a.cx;
  const dy = b.cy - a.cy;
  if (Math.abs(dx) * (a.h + 1) > Math.abs(dy) * (a.w + 1)) return dx > 0 ? 'e' : 'w';
  return dy > 0 ? 's' : 'n';
}

function anchorAt(rect, side) {
  switch (side) {
    case 'n': return { x: rect.cx, y: rect.y, nx: 0, ny: -1 };
    case 's': return { x: rect.cx, y: rect.y + rect.h, nx: 0, ny: 1 };
    case 'w': return { x: rect.x, y: rect.cy, nx: -1, ny: 0 };
    default: return { x: rect.x + rect.w, y: rect.cy, nx: 1, ny: 0 };
  }
}

function curve(from, to) {
  const distance = Math.hypot(to.x - from.x, to.y - from.y);
  const pull = clamp(distance * 0.42, 26, 150);
  return `M ${from.x} ${from.y} C ${from.x + from.nx * pull} ${from.y + from.ny * pull}, ` +
         `${to.x + to.nx * pull} ${to.y + to.ny * pull}, ${to.x} ${to.y}`;
}

export function wirePath(wire) {
  const a = rectOf(wire.from);
  const b = rectOf(wire.to);
  if (!a || !b) return null;
  const from = anchorAt(a, wire.fromSide || sideBetween(a, b));
  const to = anchorAt(b, wire.toSide || sideBetween(b, a));
  return curve(from, to);
}

export function drawWires() {
  wireLayer.textContent = '';
  wires().forEach((wire) => {
    const d = wirePath(wire);
    if (!d) return;
    const group = document.createElementNS(SVG_NS, 'g');
    group.dataset.id = wire.id;
    if (wire.id === S.selWire) group.classList.add('sel');

    const hit = document.createElementNS(SVG_NS, 'path');
    hit.setAttribute('d', d);
    hit.setAttribute('class', 'hitline');

    const line = document.createElementNS(SVG_NS, 'path');
    line.setAttribute('d', d);
    line.setAttribute('class', 'line');
    line.setAttribute('stroke', `var(--wire, #7a7266)`);
    line.setAttribute('stroke-width', '2');
    if (wire.arrow !== 'none') line.setAttribute('marker-end', 'url(#arrowhead)');

    group.append(hit, line);
    wireLayer.appendChild(group);
  });
}

/** Cheap redraw of only the wires touching these elements (used during a drag). */
function refreshWiresFor(ids) {
  const set = new Set(ids);
  wires().forEach((wire) => {
    if (!set.has(wire.from) && !set.has(wire.to)) return;
    const group = wireLayer.querySelector(`g[data-id="${wire.id}"]`);
    const d = wirePath(wire);
    if (group && d) group.querySelectorAll('path').forEach((p) => p.setAttribute('d', d));
  });
}

// --- adding elements -------------------------------------------------------

export function addElement(el, { edit = false } = {}) {
  mutate(() => els().push(el));
  select(el.id);
  if (edit) {
    const node = nodeOf(el.id);
    if (node) enterEdit(node);
  }
  return el;
}

export function removeSelected() {
  const doomed = new Set(S.sel);
  selectedRoots().forEach((el) => {
    if (el.type === 'column') (el.children || []).forEach((id) => doomed.add(id));
  });
  if (!doomed.size && !S.selWire) return;
  mutate(() => {
    if (S.selWire) {
      S.board.connectors = wires().filter((w) => w.id !== S.selWire);
      S.selWire = null;
    }
    if (doomed.size) {
      S.board.elements = els().filter((el) => !doomed.has(el.id));
      S.board.connectors = wires().filter(
        (w) => !doomed.has(w.from) && !doomed.has(w.to),
      );
      els().forEach((el) => {
        if (el.type === 'column') el.children = (el.children || []).filter((id) => !doomed.has(id));
      });
    }
  });
  S.sel.clear();
  emit('selection');
}

export function duplicateSelected() {
  const copies = selectedRoots().map((el) => {
    const copy = structuredClone(el);
    copy.id = uid('el');
    copy.parent = null;
    copy.x += 24;
    copy.y += 24;
    if (copy.type === 'column') copy.children = [];
    if (copy.items) copy.items = copy.items.map((i) => ({ ...i, id: uid('t') }));
    return copy;
  });
  if (!copies.length) return;
  mutate(() => copies.forEach((c) => els().push(c)));
  select(copies.map((c) => c.id));
}

// --- moving cards between boards -------------------------------------------

/** Selected cards plus the children of any selected column. */
function selectionWithChildren() {
  const ids = new Set();
  selectedRoots().forEach((el) => {
    ids.add(el.id);
    if (el.type === 'column') (el.children || []).forEach((id) => ids.add(id));
  });
  return {
    elements: els().filter((el) => ids.has(el.id)).map((el) => structuredClone(el)),
    connectors: wires().filter((w) => ids.has(w.from) && ids.has(w.to))
      .map((w) => structuredClone(w)),
    ids,
  };
}

/** Fresh ids throughout, so a copy never collides with its original. */
function reidentify(elements, connectors) {
  const map = new Map();
  const copies = elements.map((el) => {
    const copy = structuredClone(el);
    copy.id = uid('el');
    map.set(el.id, copy.id);
    return copy;
  });
  copies.forEach((copy) => {
    if (copy.parent) copy.parent = map.get(copy.parent) || null;
    if (copy.children) copy.children = copy.children.map((id) => map.get(id)).filter(Boolean);
    if (copy.items) copy.items = copy.items.map((item) => ({ ...item, id: uid('t') }));
  });
  const wired = connectors
    .filter((w) => map.has(w.from) && map.has(w.to))
    .map((w) => ({ ...w, id: uid('c'), from: map.get(w.from), to: map.get(w.to) }));
  return { copies, wired };
}

const CLIP_TAG = 'muse-cards:';

export function copySelection({ cut = false } = {}) {
  const picked = selectionWithChildren();
  if (!picked.elements.length) return;
  const payload = {
    project: S.project.id, board: S.board.id,
    elements: picked.elements, connectors: picked.connectors,
  };
  const serialised = JSON.stringify(payload);
  storage.setItem('muse.clipboard', serialised);
  // On the real clipboard too, so Ctrl+V works and carries between windows.
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(CLIP_TAG + serialised).catch(() => {});
  }
  if (cut) removeSelected();
  return payload;
}

export async function pasteClipboard(at, text = null) {
  let data = null;
  try {
    data = text && text.startsWith(CLIP_TAG)
      ? JSON.parse(text.slice(CLIP_TAG.length))
      : JSON.parse(storage.getItem('muse.clipboard') || 'null');
  } catch { data = null; }
  if (!data || !data.elements || !data.elements.length) return;

  const { copies, wired } = reidentify(data.elements, data.connectors || []);
  const minX = Math.min(...copies.map((c) => c.x));
  const minY = Math.min(...copies.map((c) => c.y));
  copies.forEach((copy) => { copy.x += at.x - minX; copy.y += at.y - minY; });

  // From another board, the server copies the images and files across too.
  if (data.board !== S.board.id) {
    await flush();
    await api.receive(S.project.id, S.board.id, data.board, copies, wired);
    await loadBoard(S.board.id);
    select(copies.map((c) => c.id));
    return;
  }
  mutate(() => {
    copies.forEach((copy) => els().push(copy));
    wired.forEach((wire) => wires().push(wire));
  });
  select(copies.filter((c) => !c.parent).map((c) => c.id));
}

/** Send the selection to another board, assets and all. */
export async function moveSelectionToBoard(targetBoardId) {
  const picked = selectionWithChildren();
  if (!picked.elements.length || targetBoardId === S.board.id) return;
  const { copies, wired } = reidentify(picked.elements, picked.connectors);
  const sourceBoard = S.board.id;

  mutate(() => {
    S.board.elements = els().filter((el) => !picked.ids.has(el.id));
    S.board.connectors = wires().filter(
      (w) => !picked.ids.has(w.from) && !picked.ids.has(w.to));
    els().forEach((el) => {
      if (el.type === 'column') el.children = (el.children || []).filter((id) => !picked.ids.has(id));
    });
  });
  S.sel.clear();
  emit('selection');
  await flush();
  await api.receive(S.project.id, targetBoardId, sourceBoard, copies, wired);
  emit('moved-away', { count: copies.length, board: targetBoardId });
}

export function colorSelected(color) {
  const list = selectedRoots();
  if (!list.length) return;
  mutate(() => list.forEach((el) => { el.color = color; }));
}

// --- pointer interaction ---------------------------------------------------

let drag = null;
let spaceDown = false;

stage.addEventListener('pointerdown', (ev) => {
  if (ev.button === 2) return;
  // Floating UI lives inside the stage. Without this, clicking any of it bubbles
  // here and exits edit / clears selection before the control's own click runs -
  // which is why the formatting toolbar buttons (bold, colour) "did nothing" or
  // "closed themselves". Must include every in-stage popover.
  if (ev.target.closest('#selrail, #fmttools, #textcolors, #colorpop, #rail, .ctxmenu, .iconpop')) return;
  // While editing, only the text field itself swallows the pointer - the rest
  // of the card still drags, so you never have to click away to move it.
  if (ev.target.closest('.el.editing') && ev.target.closest('[data-edit]')) return;

  const start = screenToWorld(ev.clientX, ev.clientY);

  // Presenting: every drag is a pan, nothing is editable.
  if (present.on) {
    drag = { mode: 'pan', sx: ev.clientX, sy: ev.clientY, vx: S.view.x, vy: S.view.y };
    stage.classList.add('panning');
    capture(ev);
    ev.preventDefault();
    return;
  }

  if (ev.button === 1 || spaceDown) {
    drag = { mode: 'pan', sx: ev.clientX, sy: ev.clientY, vx: S.view.x, vy: S.view.y };
    stage.classList.add('panning');
    capture(ev);
    ev.preventDefault();
    return;
  }

  const node = ev.target.closest('.el');
  const wireGroup = ev.target.closest('#wire-layer g');

  if (!node && wireGroup) {
    exitEdit();
    S.sel.clear();
    S.selWire = wireGroup.dataset.id;
    emit('selection');
    return;
  }

  if (!node) {
    exitEdit();
    if (!ev.shiftKey) deselect();
    drag = {
      mode: 'marquee', sx: ev.clientX, sy: ev.clientY,
      additive: ev.shiftKey, keep: new Set(S.sel),
    };
    capture(ev);
    marquee.hidden = false;
    sizeMarquee(ev.clientX, ev.clientY);
    return;
  }

  const el = byId(node.dataset.id);
  if (!el) return;
  exitEdit();

  if (ev.target.dataset.nub) {
    drag = { mode: 'wire', from: el.id, side: ev.target.dataset.nub, to: start };
    capture(ev);
    const temp = document.createElementNS(SVG_NS, 'path');
    temp.setAttribute('class', 'line');
    temp.setAttribute('stroke', '#4c8dff');
    temp.setAttribute('stroke-width', '2');
    temp.setAttribute('stroke-dasharray', '5 4');
    temp.setAttribute('marker-end', 'url(#arrowhead)');
    wireLayer.appendChild(temp);
    drag.temp = temp;
    updateTempWire(start);
    return;
  }

  const wasSelected = S.sel.has(el.id);
  if (ev.shiftKey) {
    if (wasSelected) S.sel.delete(el.id); else S.sel.add(el.id);
    S.selWire = null;
    emit('selection');
  } else if (!wasSelected) {
    select(el.id);
  }

  if (ev.target.dataset.grip) {
    drag = {
      mode: 'resize', el, start,
      w0: el.w, h0: el.h,
      ratio: el.type === 'image' && el.nw ? el.nh / el.nw : null,
      moved: false,
    };
  } else {
    drag = {
      mode: 'move', start, moved: false, wasSelected,
      node, elId: el.id,
      items: selectedRoots().map((e) => ({ el: e, x0: e.x, y0: e.y })),
    };
  }
  capture(ev);
  ev.preventDefault();
});

stage.addEventListener('pointermove', (ev) => {
  if (!drag) return;
  const point = screenToWorld(ev.clientX, ev.clientY);

  if (drag.mode === 'pan') {
    S.view.x = drag.vx + (ev.clientX - drag.sx);
    S.view.y = drag.vy + (ev.clientY - drag.sy);
    applyView();
    return;
  }

  if (drag.mode === 'marquee') { sizeMarquee(ev.clientX, ev.clientY); return; }

  if (drag.mode === 'wire') { updateTempWire(point); return; }

  const dx = point.x - drag.start.x;
  const dy = point.y - drag.start.y;

  if (drag.mode === 'resize') {
    if (!drag.moved && Math.hypot(dx, dy) < 2) return;
    if (!drag.moved) { checkpoint(); drag.moved = true; }
    const el = drag.el;
    el.w = Math.max(70, Math.round(drag.w0 + dx));
    el.h = drag.ratio && !ev.shiftKey
      ? Math.round(el.w * drag.ratio)
      : Math.max(44, Math.round(drag.h0 + dy));
    // Snap the size to line up with, or match, the cards already placed. Hold
    // Alt to resize freely, the same key that frees a move from snapping.
    if (!ev.altKey) drawGuides(snapResize(el, !!drag.ratio && !ev.shiftKey));
    else clearGuides();
    if (el.parent) layoutColumn(byId(el.parent));
    reflow();
    return;
  }

  // move
  if (!drag.moved && Math.hypot(dx, dy) < 3) return;
  drag.alt = ev.altKey;
  if (!drag.moved) {
    checkpoint();
    drag.moved = true;
    drag.node.classList.add('dragging');
    // Pulling a card out of a column frees it from the stack.
    drag.items.forEach(({ el }) => {
      if (!el.parent) return;
      const column = byId(el.parent);
      if (column) column.children = column.children.filter((id) => id !== el.id);
      el.parent = null;
    });
    drag.items.forEach((item) => { item.x0 = item.el.x; item.y0 = item.el.y; });
    reflow();
  }

  const snap = drag.alt ? { dx, dy, guides: [] } : snapDelta(drag, dx, dy);
  drag.items.forEach(({ el, x0, y0 }) => {
    el.x = Math.round(x0 + snap.dx);
    el.y = Math.round(y0 + snap.dy);
    if (el.type === 'column') layoutColumn(el);
  });
  drawGuides(snap.guides);
  reflow();
  highlightColumnUnder(ev, drag);
  highlightBoardRow(ev);
});

/** Dragging cards over a board in the sidebar offers to move them there. */
function boardRowUnder(ev) {
  const node = document.elementFromPoint(ev.clientX, ev.clientY);
  const row = node && node.closest('#tree .row');
  return row && row.dataset.id !== (S.board && S.board.id) ? row : null;
}

function highlightBoardRow(ev) {
  document.querySelectorAll('#tree .row.drop').forEach((r) => r.classList.remove('drop'));
  const row = boardRowUnder(ev);
  if (row) row.classList.add('drop');
}

// --- snapping --------------------------------------------------------------

const SNAP = 6;          // world pixels
const guideBox = document.getElementById('guides');

/** Nudge a drag so edges and centres line up with the cards already placed. */
function snapDelta(session, dx, dy) {
  const moving = new Set(session.items.map((i) => i.el.id));
  const others = els().filter((el) => !moving.has(el.id) && !el.parent);
  if (!others.length) return { dx, dy, guides: [] };

  const box = session.items.reduce((acc, { el, x0, y0 }) => ({
    x1: Math.min(acc.x1, x0 + dx), y1: Math.min(acc.y1, y0 + dy),
    x2: Math.max(acc.x2, x0 + dx + el.w), y2: Math.max(acc.y2, y0 + dy + el.h),
  }), { x1: Infinity, y1: Infinity, x2: -Infinity, y2: -Infinity });

  const mine = {
    x: [box.x1, (box.x1 + box.x2) / 2, box.x2],
    y: [box.y1, (box.y1 + box.y2) / 2, box.y2],
  };

  const best = { x: null, y: null };
  others.forEach((el) => {
    const theirs = {
      x: [el.x, el.x + el.w / 2, el.x + el.w],
      y: [el.y, el.y + el.h / 2, el.y + el.h],
    };
    ['x', 'y'].forEach((axis) => {
      mine[axis].forEach((value) => {
        theirs[axis].forEach((target) => {
          const gap = target - value;
          if (Math.abs(gap) <= SNAP && (!best[axis] || Math.abs(gap) < Math.abs(best[axis].gap))) {
            best[axis] = { gap, at: target, el };
          }
        });
      });
    });
  });

  const guides = [];
  if (best.x) guides.push({ axis: 'x', at: best.x.at, el: best.x.el, box });
  if (best.y) guides.push({ axis: 'y', at: best.y.at, el: best.y.el, box });
  return {
    dx: dx + (best.x ? best.x.gap : 0),
    dy: dy + (best.y ? best.y.gap : 0),
    guides,
  };
}

/** Snap a resize so the card's right/bottom edges line up with other cards, or
 *  so its width/height matches one of them. Mutates el.w/el.h, returns guides. */
function snapResize(el, keepRatio) {
  const others = els().filter((o) => o.id !== el.id && !o.parent && o.type !== 'column');
  if (!others.length) return [];

  const right = el.x + el.w;
  const bottom = el.y + el.h;
  let bestW = null;   // adjustment to width
  let bestH = null;   // adjustment to height

  const consider = (best, gap) =>
    Math.abs(gap) <= SNAP && (!best || Math.abs(gap) < Math.abs(best.gap));

  others.forEach((o) => {
    // Right edge to another card's left / centre / right edge.
    [o.x, o.x + o.w / 2, o.x + o.w].forEach((t) => {
      const gap = t - right;
      if (consider(bestW, gap)) bestW = { gap };
    });
    // Equal width: match this card's width to the other's.
    const gw = o.w - el.w;
    if (consider(bestW, gw)) bestW = { gap: gw };

    // Bottom edge to another card's top / centre / bottom edge.
    [o.y, o.y + o.h / 2, o.y + o.h].forEach((t) => {
      const gap = t - bottom;
      if (consider(bestH, gap)) bestH = { gap };
    });
    // Equal height.
    const gh = o.h - el.h;
    if (consider(bestH, gh)) bestH = { gap: gh };
  });

  if (bestW) el.w = Math.max(70, Math.round(el.w + bestW.gap));
  // A fixed-ratio image drives its height from the width, so only snap height
  // when the card is free to size on its own.
  if (bestH && !keepRatio) el.h = Math.max(44, Math.round(el.h + bestH.gap));
  else if (keepRatio && bestW) el.h = Math.round(el.w * (el.h / (el.w - bestW.gap)));

  const box = { x1: el.x, y1: el.y, x2: el.x + el.w, y2: el.y + el.h };
  const guides = [];
  if (bestW) guides.push({ axis: 'x', at: el.x + el.w, el, box });
  if (bestH && !keepRatio) guides.push({ axis: 'y', at: el.y + el.h, el, box });
  return guides;
}

function drawGuides(guides) {
  guideBox.textContent = '';
  guides.forEach(({ axis, at, el, box }) => {
    const line = document.createElement('div');
    line.className = `guide ${axis}`;
    if (axis === 'x') {
      const y1 = Math.min(box.y1, el.y);
      const y2 = Math.max(box.y2, el.y + el.h);
      const a = worldToScreen(at, y1);
      line.style.left = `${a.x - stage.getBoundingClientRect().left}px`;
      line.style.top = `${a.y - stage.getBoundingClientRect().top}px`;
      line.style.height = `${(y2 - y1) * S.view.zoom}px`;
    } else {
      const x1 = Math.min(box.x1, el.x);
      const x2 = Math.max(box.x2, el.x + el.w);
      const a = worldToScreen(x1, at);
      line.style.left = `${a.x - stage.getBoundingClientRect().left}px`;
      line.style.top = `${a.y - stage.getBoundingClientRect().top}px`;
      line.style.width = `${(x2 - x1) * S.view.zoom}px`;
    }
    guideBox.appendChild(line);
  });
}

const clearGuides = () => { guideBox.textContent = ''; };

stage.addEventListener('pointerup', (ev) => {
  if (!drag) return;
  const finished = drag;
  drag = null;
  stage.classList.remove('panning');
  try { stage.releasePointerCapture(ev.pointerId); } catch { /* already gone */ }

  if (finished.mode === 'pan') { save(); return; }

  if (finished.mode === 'marquee') {
    marquee.hidden = true;
    const box = marqueeWorldBox(finished, ev.clientX, ev.clientY);
    const hits = els().filter((el) =>
      el.x < box.x2 && el.x + el.w > box.x1 && el.y < box.y2 && el.y + el.h > box.y1);
    select(hits.map((e) => e.id), finished.additive);
    return;
  }

  if (finished.mode === 'wire') {
    finished.temp.remove();
    finishWire(finished, ev);
    return;
  }

  if (finished.mode === 'resize') {
    clearGuides();
    if (finished.moved) { save(); render(); }
    return;
  }

  // move
  finished.node.classList.remove('dragging');
  clearGuides();
  if (!finished.moved) {
    if (finished.wasSelected && S.sel.size === 1) {
      enterEdit(finished.node, ev.target.closest('[data-edit]'));
    }
    return;
  }
  const row = boardRowUnder(ev);
  document.querySelectorAll('#tree .row.drop').forEach((r) => r.classList.remove('drop'));
  if (row) {
    // Put the cards back where they started, then hand them to the other board.
    finished.items.forEach(({ el, x0, y0 }) => { el.x = x0; el.y = y0; });
    moveSelectionToBoard(row.dataset.id);
    return;
  }

  const column = columnUnder(ev, finished);
  clearColumnHighlight();
  if (column) dropIntoColumn(finished, column, ev);
  save();
  render();
  emit('selection');
});

stage.addEventListener('dblclick', (ev) => {
  if (present.on) return;    // walking into boards is fine; editing is not
  // Use the element actually under the cursor, not ev.target. Selecting a card on
  // the first click re-renders it, and the browser can retarget the second click
  // to the canvas behind the card even though the card is under the pointer -
  // that mis-target is what spawned a stray note on top of a board card.
  const hit = document.elementFromPoint(ev.clientX, ev.clientY);
  const node = (hit && hit.closest('.el')) || ev.target.closest('.el');
  const onEditable = (hit && hit.closest('[data-edit]')) || ev.target.closest('[data-edit]');
  if (node) {
    const el = byId(node.dataset.id);
    if (!el) return;
    // Double-click opens a board; double-click on its title edits the name.
    if (el.type === 'board' && !onEditable) {
      if (el.board_id) loadBoard(el.board_id);
      return;
    }
    enterEdit(node, onEditable);
    return;
  }
  // Truly empty canvas: make a note where the cursor is.
  const at = screenToWorld(ev.clientX, ev.clientY);
  addElement(centreOn(create('note', 0, 0), at.x, at.y), { edit: true });
});

// Following a board card while presenting keeps presenting on the new board.
on('board-loaded', () => {
  if (!present.on) return;
  present.order = presentOrder();
  present.index = -1;
  fitBoard();
  updateHud();
});

/** Reposition existing nodes without rebuilding them (keeps drags smooth). */
function reflow() {
  els().forEach((el) => {
    const node = nodeOf(el.id);
    if (node) place(node, el);
  });
  refreshWiresFor(els().map((e) => e.id));
}

function sizeMarquee(clientX, clientY) {
  const rect = stage.getBoundingClientRect();
  const x1 = Math.min(drag.sx, clientX) - rect.left;
  const y1 = Math.min(drag.sy, clientY) - rect.top;
  marquee.style.left = `${x1}px`;
  marquee.style.top = `${y1}px`;
  marquee.style.width = `${Math.abs(clientX - drag.sx)}px`;
  marquee.style.height = `${Math.abs(clientY - drag.sy)}px`;
}

function marqueeWorldBox(session, clientX, clientY) {
  const a = screenToWorld(session.sx, session.sy);
  const b = screenToWorld(clientX, clientY);
  return {
    x1: Math.min(a.x, b.x), y1: Math.min(a.y, b.y),
    x2: Math.max(a.x, b.x), y2: Math.max(a.y, b.y),
  };
}

// --- columns ---------------------------------------------------------------

function columnUnder(ev, session) {
  const point = screenToWorld(ev.clientX, ev.clientY);
  const moving = new Set(session.items ? session.items.map((i) => i.el.id) : []);
  return els().find((el) =>
    el.type === 'column' && !moving.has(el.id) &&
    point.x >= el.x && point.x <= el.x + el.w &&
    point.y >= el.y && point.y <= el.y + el.h);
}

function highlightColumnUnder(ev, session) {
  clearColumnHighlight();
  const column = columnUnder(ev, session);
  if (column) nodeOf(column.id)?.classList.add('over');
}

function clearColumnHighlight() {
  layer.querySelectorAll('.el.column.over').forEach((n) => n.classList.remove('over'));
}

function dropIntoColumn(session, column, ev) {
  const point = screenToWorld(ev.clientX, ev.clientY);
  let index = column.children.length;
  column.children.forEach((id, i) => {
    const child = byId(id);
    if (child && point.y < child.y + child.h / 2) index = Math.min(index, i);
  });
  session.items
    .filter(({ el }) => el.type !== 'column' && el.id !== column.id)
    .forEach(({ el }, offset) => {
      el.parent = column.id;
      column.children.splice(index + offset, 0, el.id);
    });
  layoutColumn(column);
}

// --- connector creation ----------------------------------------------------

function updateTempWire(point) {
  const a = rectOf(drag.from);
  if (!a) return;
  const from = anchorAt(a, drag.side);
  const to = { x: point.x, y: point.y, nx: 0, ny: 0 };
  drag.temp.setAttribute('d', curve(from, to));
}

function finishWire(session, ev) {
  const node = document.elementFromPoint(ev.clientX, ev.clientY)?.closest('.el');
  const targetId = node && node.dataset.id !== session.from ? node.dataset.id : null;
  const point = screenToWorld(ev.clientX, ev.clientY);
  const to = targetId || { x: Math.round(point.x), y: Math.round(point.y) };
  if (!targetId && Math.hypot(point.x - session.to.x, point.y - session.to.y) < 12) return;
  mutate(() => {
    wires().push({ id: uid('c'), from: session.from, to, arrow: 'end', color: 'slate' });
  });
}

// --- keyboard --------------------------------------------------------------

const typingTarget = (t) => !!(t && t.matches && t.matches('input, textarea, [contenteditable="true"]'));

window.addEventListener('keydown', (ev) => {
  if (ev.code === 'Space' && !isEditing() && !typingTarget(ev.target)) {
    spaceDown = true;
    stage.classList.add('space');
  }
});
window.addEventListener('keyup', (ev) => {
  if (ev.code === 'Space') { spaceDown = false; stage.classList.remove('space'); }
});
window.addEventListener('blur', () => { spaceDown = false; stage.classList.remove('space'); });

// --- wheel -----------------------------------------------------------------

/** A scrollable region inside a card that still has room to scroll this way. */
function scrollableUnder(node, deltaY) {
  let el = node;
  while (el && el !== layer && el !== stage) {
    if (el.classList && el.classList.contains('el')) return null;  // card root: pan
    const style = getComputedStyle(el);
    if (/(auto|scroll)/.test(style.overflowY) && el.scrollHeight > el.clientHeight + 1) {
      const atTop = el.scrollTop <= 0;
      const atBottom = el.scrollTop + el.clientHeight >= el.scrollHeight - 1;
      if (!(deltaY < 0 && atTop) && !(deltaY > 0 && atBottom)) return el;
    }
    el = el.parentElement;
  }
  return null;
}

stage.addEventListener('wheel', (ev) => {
  // Ctrl+wheel always zooms; otherwise a scrollable card region wins over panning.
  if (!(ev.ctrlKey || ev.metaKey) && scrollableUnder(ev.target, ev.deltaY)) return;
  ev.preventDefault();
  if (ev.ctrlKey || ev.metaKey) {
    zoomAt(ev.clientX, ev.clientY, Math.exp(-ev.deltaY * 0.0022));
  } else {
    S.view.x -= ev.deltaX;
    S.view.y -= ev.deltaY;
    applyView();
    save();
  }
}, { passive: false });

// --- drops and pastes ------------------------------------------------------

let dropDepth = 0;

stage.addEventListener('dragenter', (ev) => {
  ev.preventDefault();
  dropDepth += 1;
  dropHint.hidden = false;
});
stage.addEventListener('dragover', (ev) => { ev.preventDefault(); });
stage.addEventListener('dragleave', () => {
  dropDepth = Math.max(0, dropDepth - 1);
  if (!dropDepth) dropHint.hidden = true;
});

stage.addEventListener('drop', async (ev) => {
  ev.preventDefault();
  dropDepth = 0;
  dropHint.hidden = true;
  const at = screenToWorld(ev.clientX, ev.clientY);
  const files = [...(ev.dataTransfer.files || [])];
  if (files.length) return dropFiles(files, at);

  const uri = ev.dataTransfer.getData('text/uri-list');
  const text = ev.dataTransfer.getData('text/plain');
  await dropText(uri || text, at);
});

window.addEventListener('paste', async (ev) => {
  if (isEditing() || ev.target.matches('input, textarea')) return;
  const at = freeSpotNear(centreOfView());
  // Files first; then image blobs that only appear under items (screenshots,
  // "copy image" from a browser), which clipboardData.files often misses.
  let files = [...(ev.clipboardData.files || [])];
  if (!files.length && ev.clipboardData.items) {
    files = [...ev.clipboardData.items]
      .filter((it) => it.kind === 'file' && it.type.startsWith('image/'))
      .map((it) => it.getAsFile())
      .filter(Boolean);
  }
  if (files.length) { ev.preventDefault(); return dropFiles(files, at); }
  const text = ev.clipboardData.getData('text/plain');
  if (text.startsWith(CLIP_TAG)) { ev.preventDefault(); return pasteClipboard(at, text); }
  if (text) { ev.preventDefault(); await dropText(text, at); }
});

/** An empty image card under this point, ready to be filled. */
function placeholderAt(point) {
  return els().find((el) =>
    el.type === 'image' && !el.src &&
    point.x >= el.x && point.x <= el.x + el.w &&
    point.y >= el.y && point.y <= el.y + el.h);
}

export async function dropFiles(files, at) {
  let offset = 0;
  for (const file of files) {
    try {
      const info = await api.upload(S.project.id, S.board.id, file);
      const spot = { x: at.x + offset, y: at.y + offset };

      // First image dropped onto a template placeholder fills it in place.
      const slot = offset === 0 && info.kind === 'image' ? placeholderAt(at) : null;
      if (slot) {
        mutate(() => Object.assign(slot, { src: info.src, nw: info.nw, nh: info.nh }));
        select(slot.id);
        offset += 26;
        continue;
      }

      if (info.kind === 'image') {
        const width = 300;
        const el = create('image', 0, 0, {
          src: info.src, nw: info.nw, nh: info.nh,
          w: width, h: Math.round((width * info.nh) / info.nw) || 220,
        });
        addElement(centreOn(el, spot.x, spot.y));
      } else {
        // A PDF comes back with a rendered preview thumbnail; show it larger.
        const hasThumb = !!info.thumb;
        addElement(centreOn(create('file', 0, 0, {
          src: info.src, name: info.name, size: info.size, ext: info.ext,
          thumb: info.thumb || null,
          ...(hasThumb ? { w: 240, h: 300 } : {}),
        }), spot.x, spot.y));
      }
      offset += 26;
    } catch (err) {
      console.error('drop failed', err);
    }
  }
}

const URL_RE = /^(https?:\/\/|www\.)\S+$/i;
// C:\folder\file.png, D:\renders, \\server\share\thing
const PATH_RE = /^(?:[a-zA-Z]:[\\/]|\\\\)[^\r\n<>|?*"]+$/;

export async function dropText(text, at) {
  const value = (text || '').trim().replace(/^"|"$/g, '');
  if (!value) return;

  // A pasted Windows path becomes a live card, not a note about a path.
  if (PATH_RE.test(value)) {
    const info = await fs.info(value).catch(() => null);
    if (info && info.exists) return addLiveCards([value], at);
  }

  if (URL_RE.test(value)) {
    const el = addElement(centreOn(create('link', 0, 0, { url: value, title: value }), at.x, at.y));
    try {
      const preview = await api.linkPreview(value, S.project.id, S.board.id);
      Object.assign(el, preview);
      save();
      render();
    } catch { /* keep the bare link card */ }
    return;
  }
  const lines = value.split('\n').filter(Boolean);
  const el = create('note', 0, 0, {
    text: lines.map((line) => escapeHtml(line)).join('<br>'),
    h: clamp(60 + lines.length * 20, 110, 380),
  });
  addElement(centreOn(el, at.x, at.y));
}

function escapeHtml(text) {
  const node = document.createElement('div');
  node.textContent = text;
  return node.innerHTML;
}

/** Used by the rail's image/file tools. */
export function pickFiles(at) {
  filePicker.value = '';
  filePicker.onchange = () => {
    if (filePicker.files.length) dropFiles([...filePicker.files], at);
  };
  filePicker.click();
}

// text cards grow to fit what you type
on('measure', (el) => {
  if (!el || el.type !== 'text') return;
  const node = nodeOf(el.id);
  const rich = node && node.querySelector('.rich');
  if (!rich) return;
  const height = rich.scrollHeight + 18;
  if (Math.abs(height - el.h) > 3) { el.h = height; place(node, el); refreshWiresFor([el.id]); }
});

// --- live cards ------------------------------------------------------------

// Cheap enough to run often: each card is one stat call on a local disk.
setInterval(() => {
  if (document.hidden || !S.board) return;
  tickLiveCards();
}, 4000);

// --- present mode ------------------------------------------------------------

const hud = document.getElementById('present-hud');
const hudStep = document.getElementById('present-step');

export const present = { on: false, order: [], index: -1 };

/** Reading order: rows top to bottom, left to right within a row. */
function presentOrder() {
  const cards = els().filter((el) => !el.parent && el.type !== 'text');
  const rows = [];
  [...cards].sort((a, b) => a.y - b.y).forEach((el) => {
    const row = rows.find((r) => Math.abs(r.y - (el.y + el.h / 2)) < Math.max(80, el.h / 2));
    if (row) { row.items.push(el); row.y = (row.y + el.y + el.h / 2) / 2; }
    else rows.push({ y: el.y + el.h / 2, items: [el] });
  });
  return rows.flatMap((row) => row.items.sort((a, b) => a.x - b.x)).map((el) => el.id);
}

export function startPresent() {
  if (!S.board || present.on) return;
  exitEdit();
  deselect();
  present.on = true;
  present.order = presentOrder();
  present.index = -1;
  document.body.classList.add('presenting');
  hud.hidden = false;
  fitBoard();
  updateHud();
}

export function stopPresent() {
  if (!present.on) return;
  present.on = false;
  document.body.classList.remove('presenting');
  hud.hidden = true;
}

function updateHud() {
  hudStep.textContent = present.index < 0
    ? `${S.board.title}`
    : `${present.index + 1} / ${present.order.length}`;
}

export function presentStep(direction) {
  if (!present.on || !present.order.length) return;
  present.index = Math.max(-1, Math.min(present.order.length - 1, present.index + direction));
  if (present.index < 0) { fitBoard(); updateHud(); return; }
  const el = byId(present.order[present.index]);
  if (!el) { present.order = presentOrder(); return; }
  const rect = stage.getBoundingClientRect();
  const zoom = clamp(Math.min(
    (rect.width * 0.7) / el.w, (rect.height * 0.7) / el.h), 0.4, 1.4);
  S.view.zoom = zoom;
  S.view.x = rect.width / 2 - (el.x + el.w / 2) * zoom;
  S.view.y = rect.height / 2 - (el.y + el.h / 2) * zoom;
  applyView();
  save();
  updateHud();
}

// --- quick capture inbox -----------------------------------------------------

// Snips taken with the global hotkey land in an inbox on disk; whichever board
// is open pins them. Claiming is first-come, so two open pages cannot double-pin.
let draining = false;

export async function drainCaptures() {
  if (draining || !S.board || !S.project) return;
  draining = true;
  try {
    const { captures } = await api.captures();
    for (const item of captures) {
      const info = await api.claimCapture(item.name, S.project.id, S.board.id)
        .catch(() => null);
      if (!info || !info.nw) continue;
      const width = Math.min(360, info.nw);
      const el = create('image', 0, 0, {
        src: info.src, nw: info.nw, nh: info.nh,
        w: width, h: Math.round((width * info.nh) / info.nw) || 220,
        caption: '',
      });
      const at = freeSpotNear(centreOfView());
      addElement(centreOn(el, at.x, at.y));
    }
  } catch { /* server busy; the inbox keeps them safe */ }
  draining = false;
}

setInterval(() => {
  if (document.hidden) return;
  drainCaptures();
}, 2500);
on('board-loaded', drainCaptures);

/** A watch card set to "add new files" drops them onto the board as they appear. */
on('watch-files', ({ el, files }) => {
  if (!el.auto || !files.length) return;
  const seen = new Set(el.seen || []);
  const fresh = files.filter((file) => !seen.has(file.path)).slice(0, 12);
  if (!fresh.length) {
    if (!el.seen || el.seen.length !== files.length) {
      el.seen = files.map((f) => f.path);
      save();
    }
    return;
  }
  // First sight of a folder just records what is in it; nothing gets dumped
  // on the board retrospectively.
  if (!el.seen || !el.seen.length) {
    el.seen = files.map((f) => f.path);
    save();
    return;
  }
  mutate(() => {
    fresh.reverse().forEach((file, index) => {
      const card = create('live', el.x + el.w + 30, el.y + index * 30, {
        path: file.path, name: file.name, kind: file.kind, mtime: file.mtime,
        w: 240, h: 210,
      });
      els().push(card);
      el.seen.push(file.path);
    });
  });
});

export async function addLiveCards(paths, at) {
  let offset = 0;
  for (const path of paths) {
    try {
      const info = await fs.info(path);
      const card = info.kind === 'folder'
        ? create('watch', 0, 0, { path: info.path, title: info.name })
        : create('live', 0, 0, {
            path: info.path, name: info.name, kind: info.kind, mtime: info.mtime,
          });
      addElement(centreOn(card, at.x + offset, at.y + offset));
      offset += 28;
    } catch (err) {
      console.error('could not link', path, err);
    }
  }
}

on('render', render);
on('theme', render);   // repaint so code cards re-highlight for the new palette
on('board-loaded', () => { applyView(); });
