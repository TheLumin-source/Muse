// Board state, selection, undo history and autosave.

import { api } from './api.js';

export const S = {
  project: null,      // { id, name, folder, ... } - the open project
  projects: [],       // every project on disk, most recent first
  board: null,        // the open board, exactly as stored on disk
  trail: [],          // breadcrumbs, root first
  sel: new Set(),     // selected element ids
  selWire: null,      // selected connector id
  view: { x: 0, y: 0, zoom: 1 },
  undo: [],
  redo: [],
  saving: false,
  dirty: false,
};

const listeners = new Map();

export function on(event, fn) {
  if (!listeners.has(event)) listeners.set(event, new Set());
  listeners.get(event).add(fn);
}

export function emit(event, detail) {
  (listeners.get(event) || []).forEach((fn) => fn(detail));
}

export const uid = (p = 'el') =>
  `${p}_${Math.random().toString(36).slice(2, 8)}${Date.now().toString(36).slice(-3)}`;

// --- element access --------------------------------------------------------

export const els = () => (S.board ? S.board.elements : []);
export const wires = () => (S.board ? S.board.connectors : []);
export const byId = (id) => els().find((e) => e.id === id);

export function selected() {
  return [...S.sel].map(byId).filter(Boolean);
}

/** Selected elements minus any whose column parent is also selected (avoids double-moves). */
export function selectedRoots() {
  return selected().filter((e) => !(e.parent && S.sel.has(e.parent)));
}

export function select(ids, additive = false) {
  if (!additive) S.sel.clear();
  (Array.isArray(ids) ? ids : [ids]).forEach((id) => id && S.sel.add(id));
  S.selWire = null;
  emit('selection');
}

export function deselect() {
  if (!S.sel.size && !S.selWire) return;
  S.sel.clear();
  S.selWire = null;
  emit('selection');
}

// --- history ---------------------------------------------------------------

const HISTORY_MAX = 60;
const snap = () => JSON.stringify({ e: S.board.elements, c: S.board.connectors });

let pending = null;

/** Record the current state so the next change is undoable. */
export function checkpoint() {
  if (!S.board) return;
  S.undo.push(snap());
  if (S.undo.length > HISTORY_MAX) S.undo.shift();
  S.redo.length = 0;
  emit('history');
}

/** Checkpoint once for a burst of edits (typing, dragging) rather than per keystroke. */
export function checkpointOnce(key) {
  if (pending === key) return;
  pending = key;
  checkpoint();
}

export function endBurst() {
  pending = null;
}

function restore(json) {
  const data = JSON.parse(json);
  S.board.elements = data.e;
  S.board.connectors = data.c;
  S.sel.clear();
  S.selWire = null;
  emit('render');
  emit('selection');
  save();
}

export function undo() {
  if (!S.undo.length) return;
  S.redo.push(snap());
  restore(S.undo.pop());
  emit('history');
}

export function redo() {
  if (!S.redo.length) return;
  S.undo.push(snap());
  restore(S.redo.pop());
  emit('history');
}

// --- persistence -----------------------------------------------------------

let timer = null;

export function save() {
  if (!S.board) return;
  S.dirty = true;
  emit('save-state');
  clearTimeout(timer);
  timer = setTimeout(flush, 300);
}

export async function flush() {
  clearTimeout(timer);
  if (!S.board || !S.dirty || !S.project) return;
  const board = S.board;
  const projectId = S.project.id;
  S.saving = true;
  emit('save-state');
  try {
    board.view = { ...S.view };
    await api.saveBoard(projectId, board);
    if (S.board === board) S.dirty = false;
  } catch (err) {
    console.error('save failed', err);
  } finally {
    S.saving = false;
    emit('save-state');
  }
}

/** Explicit Save (button / Ctrl+S). Unlike flush(), this always writes the
 *  current board to disk even when nothing is marked dirty, so pressing Save is
 *  never a silent no-op. Returns true on a confirmed write. */
export async function forceSave() {
  clearTimeout(timer);
  if (!S.board || !S.project) return false;
  const board = S.board;
  const projectId = S.project.id;
  S.saving = true;
  emit('save-state');
  try {
    board.view = { ...S.view };
    await api.saveBoard(projectId, board);
    if (S.board === board) S.dirty = false;
    return true;
  } catch (err) {
    console.error('save failed', err);
    return false;
  } finally {
    S.saving = false;
    emit('save-state');
  }
}

/** Fire-and-forget save that survives the page being torn down. */
export function flushOnExit() {
  if (!S.board || !S.dirty || !S.project) return;
  S.board.view = { ...S.view };
  api.flush(S.project.id, S.board);
}

// Belt and braces: if anything ever swallows the debounce, this still lands.
setInterval(() => { if (S.dirty && !S.saving) flush(); }, 3000);
window.addEventListener('pagehide', flushOnExit);
window.addEventListener('blur', () => { if (S.dirty) flush(); });
document.addEventListener('visibilitychange', () => {
  if (document.visibilityState === 'hidden') flush();
});

/** Snapshot + mutate + persist + redraw, in the right order. */
export function mutate(fn, { render = true } = {}) {
  checkpoint();
  fn();
  save();
  if (render) emit('render');
}

/** Switch projects. Returns the board to open. */
export async function loadProject(project) {
  await flush();
  S.project = project;
  S.board = null;
  const { home } = await api.openProject(project.id);
  emit('project-loaded');
  return home;
}

export async function refreshProjects() {
  const data = await api.projects();
  S.projects = data.projects;
  if (S.project) {
    const fresh = S.projects.find((p) => p.id === S.project.id);
    if (fresh) S.project = fresh;
  }
  emit('projects');
  return data;
}

export async function loadBoard(id) {
  await flush();
  const { board, trail } = await api.board(S.project.id, id);
  S.board = board;
  S.trail = trail;
  S.sel.clear();
  S.selWire = null;
  S.undo.length = 0;
  S.redo.length = 0;
  S.dirty = false;
  S.view = { x: 0, y: 0, zoom: 1, ...(board.view || {}) };
  location.hash = `${S.project.id}/${id}`;
  emit('board-loaded');
  emit('render');
  emit('view');
  emit('history');
  emit('save-state');
  return board;
}
