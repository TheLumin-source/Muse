// Chrome around the canvas: sidebar tree, breadcrumbs, search, rail, shortcuts.

import { api, fs, mediaUrl } from './api.js';
import {
  S, on, emit, els, byId, select, deselect, selected, loadBoard, undo, redo,
  save, flush, forceSave, flushOnExit, mutate, loadProject, refreshProjects,
} from './state.js';
import {
  create, centreOn, COLORS, isEditing, exitEdit, enterEdit, forgetMiniature,
  renderBoardIcon,
} from './elements.js';
import { ask, confirmBox } from './dialogs.js';
import { storage } from './storage.js';
import {
  applyView, screenToWorld, centreOfView, freeSpotNear, zoomBy, resetZoom, fitBoard,
  addElement, removeSelected, duplicateSelected, colorSelected, pickFiles, dropText, render,
  copySelection, pasteClipboard, addLiveCards,
  present, startPresent, stopPresent, presentStep,
} from './board.js';

const $ = (sel) => document.querySelector(sel);
const stage = $('#stage');
const treeBox = $('#tree');
const resultsBox = $('#results');
const crumbs = $('#crumbs');
const searchInput = $('#search');
const saveState = $('#save-state');

let tree = [];
const expanded = new Set(JSON.parse(storage.getItem('muse.expanded') || '[]'));

// --- sidebar ---------------------------------------------------------------

export async function refreshTree() {
  const data = await api.tree(S.project.id);
  tree = data.tree;
  drawTree();
  return data;
}

function drawTree() {
  treeBox.textContent = '';
  treeBox.appendChild(branch(tree));
}

function branch(boards) {
  const wrap = document.createElement('div');
  boards.forEach((board) => {
    const row = document.createElement('div');
    row.className = 'row' + (S.board && board.id === S.board.id ? ' active' : '');
    row.dataset.id = board.id;

    const twist = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    twist.setAttribute('class', `ic twist${expanded.has(board.id) ? ' open' : ''}`);
    twist.innerHTML = '<use href="#i-chev"/>';
    if (!board.children.length) twist.style.visibility = 'hidden';
    twist.addEventListener('click', (ev) => {
      ev.stopPropagation();
      if (expanded.has(board.id)) expanded.delete(board.id); else expanded.add(board.id);
      storage.setItem('muse.expanded', JSON.stringify([...expanded]));
      drawTree();
    });

    const label = document.createElement('span');
    label.className = 'label';
    if (board.icon) {
      const ic = document.createElement('span');
      ic.className = 'ticon';
      renderBoardIcon(ic, board.icon, { fallback: false });
      label.appendChild(ic);
    }
    label.appendChild(document.createTextNode(board.title));

    const count = document.createElement('span');
    count.className = 'count';
    count.textContent = board.count || '';

    const add = document.createElement('button');
    add.className = 'add';
    add.title = 'New board inside';
    add.innerHTML = '<svg class="ic"><use href="#i-plus"/></svg>';
    add.addEventListener('click', async (ev) => {
      ev.stopPropagation();
      const child = await api.createBoard(S.project.id, 'Untitled board', board.id);
      expanded.add(board.id);
      await refreshTree();
      await loadBoard(child.id);
    });

    row.append(twist, label, count, add);
    row.addEventListener('click', () => loadBoard(board.id));
    row.addEventListener('contextmenu', (ev) => {
      ev.preventDefault();
      boardMenu(board, ev.clientX, ev.clientY);
    });
    wrap.appendChild(row);

    if (board.children.length && expanded.has(board.id)) {
      const kids = branch(board.children);
      kids.className = 'kids';
      wrap.appendChild(kids);
    }
  });
  return wrap;
}

function boardMenu(board, x, y) {
  menu(x, y, [
    ['Rename', async () => {
      const title = await ask('Board name', board.title, 'Rename');
      if (title === null) return;
      await api.patchBoard(S.project.id, board.id, { title });
      if (S.board && S.board.id === board.id) { S.board.title = title; drawCrumbs(); }
      refreshTree();
    }],
    ['New board inside', async () => {
      const child = await api.createBoard(S.project.id, 'Untitled board', board.id);
      expanded.add(board.id);
      await refreshTree();
      loadBoard(child.id);
    }],
    ['Open this board first', async () => {
      await api.setHomeBoard(S.project.id, board.id);
      refreshProjects();
    }],
    ['Delete board', async () => {
      const sure = await confirmBox(
        `Delete "${board.title}" and everything inside it?\n\nIt goes to this project's trash, so you can put it back.`);
      if (!sure) return;
      await api.deleteBoard(S.project.id, board.id);
      const data = await refreshTree();
      await refreshTrash();
      if (S.board && S.board.id === board.id) loadBoard(data.home);
    }],
  ]);
}

function menu(x, y, items) {
  document.querySelector('.ctxmenu')?.remove();
  const box = document.createElement('div');
  box.className = 'ctxmenu';
  box.style.left = `${x}px`;
  box.style.top = `${y}px`;

  const close = () => {
    box.remove();
    document.removeEventListener('pointerdown', away, true);
  };
  // Only dismiss on a press *outside* the menu. Closing on any pointerdown
  // detaches the button before its own click fires, which silently kills
  // every menu item in the app.
  const away = (ev) => { if (!box.contains(ev.target)) close(); };

  items.forEach(([label, fn]) => {
    const item = document.createElement('button');
    item.textContent = label;
    item.addEventListener('click', () => { close(); fn(); });
    box.appendChild(item);
  });

  document.body.appendChild(box);
  const rect = box.getBoundingClientRect();
  if (rect.right > innerWidth) box.style.left = `${Math.max(6, innerWidth - rect.width - 6)}px`;
  if (rect.bottom > innerHeight) box.style.top = `${Math.max(6, innerHeight - rect.height - 6)}px`;
  document.addEventListener('pointerdown', away, true);
}

// --- breadcrumbs -----------------------------------------------------------

function drawCrumbs() {
  crumbs.textContent = '';
  if (!S.board) return;
  const trail = S.trail.length ? S.trail : [{ id: S.board.id, title: S.board.title }];
  trail.forEach((step, index) => {
    const last = index === trail.length - 1;
    if (last) {
      const here = document.createElement('span');
      here.className = 'here';
      here.contentEditable = 'true';
      here.spellcheck = false;
      here.textContent = S.board.title;
      here.addEventListener('keydown', (ev) => {
        ev.stopPropagation();
        if (ev.key === 'Enter') { ev.preventDefault(); here.blur(); }
      });
      here.addEventListener('blur', async () => {
        const title = here.textContent.trim() || 'Untitled board';
        if (title === S.board.title) return;
        S.board.title = title;
        await api.patchBoard(S.project.id, S.board.id, { title });
        refreshTree();
      });
      crumbs.appendChild(here);
    } else {
      const link = document.createElement('a');
      link.textContent = step.title;
      link.addEventListener('click', () => loadBoard(step.id));
      crumbs.appendChild(link);
      const sep = document.createElement('span');
      sep.className = 'sep';
      sep.textContent = '/';
      crumbs.appendChild(sep);
    }
  });
}

// --- search ----------------------------------------------------------------

let searchTimer = null;

searchInput.addEventListener('input', () => {
  clearTimeout(searchTimer);
  const query = searchInput.value.trim();
  if (!query) {
    resultsBox.hidden = true;
    treeBox.hidden = false;
    return;
  }
  searchTimer = setTimeout(async () => {
    const { hits } = await api.search(S.project.id, query);
    resultsBox.textContent = '';
    resultsBox.hidden = false;
    treeBox.hidden = true;
    if (!hits.length) {
      const none = document.createElement('div');
      none.className = 'none';
      none.textContent = 'Nothing found';
      resultsBox.appendChild(none);
      return;
    }
    hits.forEach((hit) => {
      const row = document.createElement('div');
      row.className = 'hit';
      row.innerHTML = '<b></b><span></span>';
      row.querySelector('b').textContent = `${hit.board} - ${hit.kind}`;
      row.querySelector('span').textContent = hit.text.slice(0, 90);
      row.addEventListener('click', async () => {
        if (!S.board || hit.board_id !== S.board.id) await loadBoard(hit.board_id);
        if (hit.element_id) centreOnElement(hit.element_id);
      });
      resultsBox.appendChild(row);
    });
  }, 220);
});

searchInput.addEventListener('keydown', (ev) => {
  ev.stopPropagation();
  if (ev.key === 'Escape') { searchInput.value = ''; searchInput.dispatchEvent(new Event('input')); }
});

function centreOnElement(id) {
  const el = byId(id);
  if (!el) return;
  const rect = stage.getBoundingClientRect();
  S.view.zoom = 1;
  S.view.x = rect.width / 2 - (el.x + el.w / 2);
  S.view.y = rect.height / 2 - (el.y + el.h / 2);
  applyView();
  select(id);
}

// --- tool rail -------------------------------------------------------------

const GHOST_LABEL = {
  note: 'Note', todo: 'To-do', text: 'Heading', image: 'Image',
  link: 'Link', file: 'File', column: 'Column', board: 'Board',
};

document.querySelectorAll('#rail .tool').forEach((tool) => {
  tool.addEventListener('pointerdown', (ev) => {
    ev.preventDefault();
    const type = tool.dataset.tool;
    const ghost = document.createElement('div');
    ghost.id = 'ghost';
    ghost.className = `el ${type}`;
    ghost.style.width = '150px';
    ghost.style.height = '84px';
    ghost.style.position = 'fixed';
    ghost.innerHTML = `<div class="body"><div class="title">${GHOST_LABEL[type]}</div></div>`;
    if (type !== 'text') ghost.style.background = `var(--c-${type === 'note' ? 'yellow' : 'white'})`;
    document.body.appendChild(ghost);

    const move = (move_ev) => {
      ghost.style.left = `${move_ev.clientX}px`;
      ghost.style.top = `${move_ev.clientY}px`;
    };
    move(ev);

    const up = (up_ev) => {
      document.removeEventListener('pointermove', move);
      document.removeEventListener('pointerup', up);
      ghost.remove();
      const overStage = document.elementFromPoint(up_ev.clientX, up_ev.clientY);
      if (!overStage || !stage.contains(overStage)) return;
      addByTool(type, screenToWorld(up_ev.clientX, up_ev.clientY));
    };
    document.addEventListener('pointermove', move);
    document.addEventListener('pointerup', up);
  });

  tool.addEventListener('click', (ev) => {
    // A plain click (no drag) drops the card into the middle of the view.
    if (ev.detail === 0) addByTool(tool.dataset.tool, freeSpotNear(centreOfView()));
  });
});

export async function addByTool(type, at) {
  if (type === 'image' || type === 'file') return pickFiles(at);

  if (type === 'live' || type === 'watch') {
    // A real Windows dialog, because the browser will not tell us a real path.
    let paths = [];
    try {
      paths = (await api.fsPick(type === 'watch' ? 'folder' : 'files')).paths;
    } catch { /* fall through to typing one */ }
    if (!paths.length) {
      const typed = await ask(type === 'watch'
        ? 'Folder to watch (paste a path)'
        : 'File to link (paste a path)', '', 'Link');
      if (!typed) return;
      paths = [typed.trim().replace(/^"|"$/g, '')];
    }
    return addLiveCards(paths, at);
  }

  if (type === 'link') {
    const url = await ask('Link URL', '', 'Add');
    if (url) await dropText(url.trim(), at);
    return;
  }

  if (type === 'board') {
    const child = await api.createBoard(S.project.id, 'Untitled board', S.board.id);
    addElement(centreOn(create('board', 0, 0, { board_id: child.id, title: child.title }), at.x, at.y));
    expanded.add(S.board.id);
    refreshTree();
    return;
  }

  const el = centreOn(create(type, 0, 0), at.x, at.y);
  addElement(el, { edit: type === 'note' || type === 'text' || type === 'todo' });
}

// --- left contextual toolbar (selrail) -------------------------------------
//
// The left rail shows the add-tools by default and swaps to card actions
// (Colour / Icon / Rename / Copy / Delete) when a card is selected, like
// Milanote. Editing a card hides both so the text formatting toolbar is clear.

const rail = $('#rail');
const selrail = $('#selrail');
const colorpop = $('#colorpop');

function updateRails() {
  const editing = isEditing();
  const hasSel = S.sel.size > 0;
  rail.hidden = hasSel;
  selrail.hidden = !hasSel || editing;
  if (selrail.hidden) colorpop.hidden = true;
  if (!selrail.hidden) refreshSelrail();
}

function refreshSelrail() {
  const one = S.sel.size === 1 ? byId([...S.sel][0]) : null;
  // Icon only for a single board card; Rename only for a card with a title/text.
  selrail.querySelector('[data-sel="icon"]').hidden = !(one && one.type === 'board');
  const renameable = one && ['note', 'todo', 'text', 'board'].includes(one.type);
  selrail.querySelector('[data-sel="rename"]').hidden = !renameable;
  // reflect the selection's colour on the Colour swatch
  const sw = selrail.querySelector('.selswatch');
  const c = one && one.color;
  sw.style.background = c ? (c[0] === '#' ? c : `var(--c-${c})`) : 'var(--c-white)';
}

on('rails', updateRails);
on('edit-start', updateRails);
on('edit-end', updateRails);
on('board-loaded', updateRails);

// Colour palette popover, opened by the Colour action.
function openColorPop() {
  colorpop.textContent = '';
  colorpop.style.display = 'grid';
  COLORS.forEach((color) => {
    const dot = document.createElement('button');
    dot.className = 'tcsw';
    dot.style.background = `var(--c-${color})`;
    dot.title = color;
    dot.addEventListener('click', () => { colorSelected(color); colorpop.hidden = true; refreshSelrail(); });
    colorpop.appendChild(dot);
  });
  const custom = document.createElement('label');
  custom.className = 'tcsw custom';
  custom.title = 'Custom colour';
  const picker = document.createElement('input');
  picker.type = 'color';
  picker.value = '#e9e7e2';
  picker.addEventListener('input', () => { colorSelected(picker.value); refreshSelrail(); });
  custom.appendChild(picker);
  colorpop.appendChild(custom);

  // A hex field: type an exact colour and it applies as you go. Prefilled with
  // the current colour when it is already a custom hex.
  const one = S.sel.size === 1 ? byId([...S.sel][0]) : null;
  if (one && typeof one.color === 'string' && one.color[0] === '#') {
    picker.value = one.color;
  }
  const hexRow = document.createElement('div');
  hexRow.className = 'tchexrow';
  const hex = document.createElement('input');
  hex.type = 'text';
  hex.className = 'tchex';
  hex.placeholder = '#RRGGBB';
  hex.spellcheck = false;
  hex.maxLength = 7;
  if (one && typeof one.color === 'string' && one.color[0] === '#') hex.value = one.color;
  hex.addEventListener('pointerdown', (ev) => ev.stopPropagation());
  hex.addEventListener('keydown', (ev) => {
    ev.stopPropagation();                       // keep canvas shortcuts out of the field
    if (ev.key === 'Enter') { colorpop.hidden = true; refreshSelrail(); }
  });
  hex.addEventListener('input', () => {
    let v = hex.value.trim();
    if (v && v[0] !== '#') v = `#${v}`;
    if (/^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$/.test(v)) {
      hex.classList.remove('bad');
      picker.value = v.length === 4
        ? `#${v[1]}${v[1]}${v[2]}${v[2]}${v[3]}${v[3]}` : v;
      colorSelected(v);
      refreshSelrail();
    } else if (v && v !== '#') {
      hex.classList.add('bad');
    }
  });
  hexRow.appendChild(hex);
  colorpop.appendChild(hexRow);

  const btn = selrail.querySelector('[data-sel="color"]');
  const r = btn.getBoundingClientRect();
  const sr = stage.getBoundingClientRect();
  colorpop.hidden = false;
  colorpop.style.left = `${r.right - sr.left + 8}px`;
  colorpop.style.top = `${r.top - sr.top}px`;
  colorpop.style.transform = 'none';
}

selrail.addEventListener('pointerdown', (ev) => ev.stopPropagation());
selrail.addEventListener('click', (ev) => {
  const btn = ev.target.closest('[data-sel]');
  if (!btn) return;
  const action = btn.dataset.sel;
  if (action === 'color') { colorpop.hidden ? openColorPop() : (colorpop.hidden = true); return; }
  colorpop.hidden = true;
  if (action === 'dup') return duplicateSelected();
  if (action === 'del') return removeSelected();
  const one = S.sel.size === 1 ? byId([...S.sel][0]) : null;
  if (!one) return;
  const node = document.querySelector(`.el[data-id="${one.id}"]`);
  if (action === 'icon' && one.type === 'board') {
    const r = btn.getBoundingClientRect();
    openIconPicker(r.right + 8, r.top, async (icon) => {
      mutate(() => { one.icon = icon; });
      if (one.board_id) { await api.patchBoard(S.project.id, one.board_id, { icon }); refreshTree(); }
    });
  } else if (action === 'rename' && node) {
    const field = node.querySelector('.btitle, .title, .rich, [data-edit]');
    if (field) enterEdit(node, field);
  }
});
colorpop.addEventListener('pointerdown', (ev) => ev.stopPropagation());

// --- theme -----------------------------------------------------------------

export function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  $('#theme').querySelector('use').setAttribute('href', theme === 'light' ? '#i-sun' : '#i-moon');
  storage.setItem('muse.theme', theme);
}

// Default is dark; honour a saved choice.
applyTheme(storage.getItem('muse.theme') || 'dark');

$('#theme').addEventListener('click', () => {
  const next = document.documentElement.dataset.theme === 'light' ? 'dark' : 'light';
  applyTheme(next);
  emit('theme', next);   // code cards re-highlight for the new palette
});

// --- top bar ---------------------------------------------------------------

// Back = go up to the parent board (breadcrumb trail is root-first).
function goBack() {
  if (S.trail && S.trail.length > 1) loadBoard(S.trail[S.trail.length - 2].id);
}
$('#back').addEventListener('click', goBack);

// Explicit save: a button and Ctrl+S. Muse already autosaves, but an on-demand
// save with clear confirmation is reassuring. forceSave() always writes the
// current board to disk (atomic write with a .bak fallback), even when nothing
// is marked dirty, so the button is never a silent no-op. It only ever writes
// the board you are looking at, never any other board. The confirmation shows
// ON the button so you see it where you clicked, not only in the sidebar.
const saveBtn = $('#save-now');
let saveResetTimer = null;
async function saveNow() {
  saveBtn.disabled = true;
  const ok = await forceSave();
  saveBtn.textContent = ok ? 'Saved' : 'Save failed';
  saveBtn.classList.toggle('is-saved', ok);
  saveBtn.classList.toggle('is-error', !ok);
  saveState.classList.add('flash');
  clearTimeout(saveResetTimer);
  saveResetTimer = setTimeout(() => {
    saveBtn.textContent = 'Save';
    saveBtn.classList.remove('is-saved', 'is-error');
    saveState.classList.remove('flash');
    saveBtn.disabled = false;
  }, 1400);
  saveBtn.disabled = false;
}
saveBtn.addEventListener('click', saveNow);
// Capture phase: an editable field stops keydown from bubbling, so a normal
// listener would miss Ctrl+S while a note is being edited.
document.addEventListener('keydown', (ev) => {
  if ((ev.ctrlKey || ev.metaKey) && !ev.shiftKey && !ev.altKey
      && (ev.key === 's' || ev.key === 'S')) {
    ev.preventDefault();
    saveNow();
  }
}, true);

on('board-loaded', () => {
  $('#back').hidden = !(S.trail && S.trail.length > 1);
});

$('#present').addEventListener('click', startPresent);
async function runExport(format) {
  await flush();
  saveState.textContent = `Exporting ${format.toUpperCase()}...`;
  try {
    const { name } = await api.exportBoard(S.project.id, S.board.id, format);
    saveState.textContent = `Exported ${name}`;
  } catch {
    saveState.textContent = 'Export failed';
  }
  setTimeout(() => emit('save-state'), 3200);
}

$('#export').addEventListener('click', (ev) => {
  const r = ev.currentTarget.getBoundingClientRect();
  menu(r.left, r.bottom + 4, [
    ['Export as PDF', () => runExport('pdf')],
    ['Export as image (PNG)', () => runExport('png')],
    ['Export as web page (HTML)', () => runExport('html')],
  ]);
});

$('#undo').addEventListener('click', undo);
$('#redo').addEventListener('click', redo);
$('#zoom-in').addEventListener('click', () => zoomBy(1.2));
$('#zoom-out').addEventListener('click', () => zoomBy(1 / 1.2));
$('#zoom-level').addEventListener('click', resetZoom);
$('#zoom-fit').addEventListener('click', fitBoard);
$('#new-root').addEventListener('click', () =>
  showTemplates('New board', newBoardFromTemplate));

on('view', () => { $('#zoom-level').textContent = `${Math.round(S.view.zoom * 100)}%`; });
on('history', () => {
  $('#undo').disabled = !S.undo.length;
  $('#redo').disabled = !S.redo.length;
  $('#undo').style.opacity = S.undo.length ? 1 : 0.4;
  $('#redo').style.opacity = S.redo.length ? 1 : 0.4;
});
on('save-state', () => {
  saveState.textContent = S.saving ? 'Saving...' : S.dirty ? 'Unsaved changes' : 'Saved';
});
on('board-loaded', () => { drawCrumbs(); drawTree(); refreshTrash(); });
// A board card's miniature is only as fresh as the last time we looked.
on('board-loaded', () => forgetMiniature(S.board.id));
on('moved-away', async ({ count, board }) => {
  await refreshTree();
  const target = document.querySelector(`#tree .row[data-id="${board}"] .label`);
  saveState.textContent = `Moved ${count} card${count === 1 ? '' : 's'} to ${target ? target.textContent : 'another board'}`;
  setTimeout(() => emit('save-state'), 2600);
});
on('project-loaded', () => { $('#project-name').textContent = S.project.name; });
on('projects', () => {
  if (S.project) $('#project-name').textContent = S.project.name;
  if (!picker.hidden) drawPicker();
});

// --- projects --------------------------------------------------------------

const picker = $('#picker');

/** Open a project and land on its home board. */
export async function openProject(project) {
  const home = await loadProject(project);
  await loadBoard(home);
  await refreshTree();
  picker.hidden = true;
  $('#project-name').textContent = project.name;
}

export function showPicker(canClose = true) {
  picker.hidden = false;
  picker.dataset.closable = canClose ? '1' : '';
  drawPicker();
  refreshBackupInfo();
}

function drawPicker() {
  const grid = picker.querySelector('.pgrid');
  grid.textContent = '';
  S.projects.forEach((project) => {
    const card = document.createElement('button');
    card.className = 'pcard' + (S.project && project.id === S.project.id ? ' current' : '');
    card.innerHTML = '<b></b><span class="pmeta"></span><span class="pfolder"></span>';
    card.querySelector('b').textContent = project.name;
    card.querySelector('.pmeta').textContent =
      `${project.boards} board${project.boards === 1 ? '' : 's'} - ${when(project.opened || project.modified)}`;
    card.querySelector('.pfolder').textContent = project.folder;
    card.addEventListener('click', () => openProject(project));
    card.addEventListener('contextmenu', (ev) => {
      ev.preventDefault();
      projectMenu(project, ev.clientX, ev.clientY);
    });
    grid.appendChild(card);
  });

  const add = document.createElement('button');
  add.className = 'pcard new';
  add.innerHTML = '<svg class="ic"><use href="#i-plus"/></svg><b>New project</b>';
  add.addEventListener('click', newProject);
  grid.appendChild(add);
}

function when(stamp) {
  if (!stamp) return 'never opened';
  const days = Math.floor((Date.now() - new Date(stamp)) / 86400000);
  if (days <= 0) return 'today';
  if (days === 1) return 'yesterday';
  if (days < 30) return `${days} days ago`;
  return new Date(stamp).toLocaleDateString();
}

async function newProject() {
  const name = await ask('Project name', 'New project', 'Create');
  if (name === null) return;
  picker.hidden = true;
  showTemplates(`First board in "${name.trim() || 'New project'}"`, async (template) => {
    const project = await api.createProject(name.trim() || 'New project', template.id);
    await refreshProjects();
    await openProject(project);
  });
}

function projectMenu(project, x, y) {
  menu(x, y, [
    ['Open', () => openProject(project)],
    ['Rename', async () => {
      const name = await ask('Project name', project.name, 'Rename');
      if (name === null) return;
      await api.renameProject(project.id, name);
      await refreshProjects();
    }],
    ['Show folder', () => api.revealProject(project.id)],
    ['Delete project', async () => {
      const sure = await confirmBox(
        `Delete "${project.name}" and every board in it?\n\nThe folder moves to the Trash folder beside your boards, so it is recoverable from there.`);
      if (!sure) return;
      await api.deleteProject(project.id);
      const data = await refreshProjects();
      if (S.project && S.project.id === project.id) {
        const next = S.projects[0];
        if (next) await openProject(next);
        else await openProject(await api.createProject('My first project'));
      }
      drawPicker();
    }],
  ]);
}

// --- board icons -----------------------------------------------------------

// Board-icon options: ids into the bi-* SVG set in index.html. Stored on a board
// as "svg:<id>", so they render crisp everywhere instead of as emoji (which the
// WebView2 shell draws as tofu boxes).
const ICON_SET = [
  'folder', 'note', 'doc', 'pin', 'bookmark', 'tag', 'flag', 'star',
  'target', 'bulb', 'fire', 'bolt', 'rocket', 'heart', 'chat', 'check',
  'code', 'terminal', 'bug', 'brain', 'chart', 'trend', 'blocks', 'box',
  'palette', 'brush', 'pencil2', 'ruler', 'camera', 'film', 'music', 'game',
  'book', 'flask', 'wrench', 'gear', 'map', 'globe', 'calendar', 'clock',
  'leaf', 'shield', 'trophy',
];

/** SVG icon grid, plus a "clear" back to the default board glyph. */
function openIconPicker(x, y, onPick) {
  document.querySelector('.iconpop')?.remove();
  const pop = document.createElement('div');
  pop.className = 'iconpop';
  const grid = document.createElement('div');
  grid.className = 'iconpop-grid';
  ICON_SET.forEach((id) => {
    const b = document.createElement('button');
    b.innerHTML = `<svg class="ic"><use href="#bi-${id}"/></svg>`;
    b.title = id;
    b.addEventListener('click', () => { pop.remove(); onPick(`svg:${id}`); });
    grid.appendChild(b);
  });
  const clear = document.createElement('button');
  clear.className = 'iconpop-clear';
  clear.textContent = 'Default icon';
  clear.addEventListener('click', () => { pop.remove(); onPick(''); });
  pop.append(grid, clear);
  document.body.appendChild(pop);
  const r = pop.getBoundingClientRect();
  pop.style.left = `${clamp(x, 6, innerWidth - r.width - 6)}px`;
  pop.style.top = `${clamp(y, 6, innerHeight - r.height - 6)}px`;
  const away = (ev) => { if (!pop.contains(ev.target)) { pop.remove(); document.removeEventListener('pointerdown', away, true); } };
  document.addEventListener('pointerdown', away, true);
}

const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));

// The board card's icon no longer opens a picker on click: that swallowed the
// first click of a double-click, so double-clicking a board to open it opened
// the icon picker instead. Icons are changed from the contextual toolbar's Icon
// button when a board card is selected. Now a double-click on the card opens the
// board (handled in board.js), matching Milanote.

// --- image lightbox --------------------------------------------------------

const lightbox = $('#lightbox');

stage.addEventListener('click', (ev) => {
  const zoom = ev.target.closest('.zoom');
  if (!zoom) return;
  ev.stopPropagation();
  const el = byId(zoom.dataset.zoomFor);
  if (!el || !el.src) return;
  lightbox.querySelector('img').src = mediaUrl(S.project.id, S.board.id, el.src);
  const cap = lightbox.querySelector('.lb-cap');
  cap.textContent = el.caption || '';
  cap.hidden = !el.caption;
  lightbox.hidden = false;
});

lightbox.addEventListener('click', () => { lightbox.hidden = true; });
window.addEventListener('keydown', (ev) => {
  if (ev.key === 'Escape' && !lightbox.hidden) lightbox.hidden = true;
}, true);

// --- code language picker --------------------------------------------------

let languages = null;

stage.addEventListener('click', async (ev) => {
  const label = ev.target.closest('.klang');
  if (!label) return;
  ev.stopPropagation();
  const el = byId(label.dataset.langFor);
  if (!el) return;
  if (!languages) {
    try { languages = (await api.languages()).languages; } catch { return; }
  }
  const r = label.getBoundingClientRect();
  menu(r.left, r.bottom + 4, languages.map((lang) => [
    lang.name, () => { mutate(() => { el.lang = lang.id; }); },
  ]));
});

// --- live file cards -------------------------------------------------------

stage.addEventListener('contextmenu', (ev) => {
  const node = ev.target.closest('.el.live, .el.watch');
  if (!node) return;
  ev.preventDefault();
  const el = byId(node.dataset.id);
  if (!el) return;
  const watching = el.type === 'watch';

  const items = [
    [watching ? 'Open folder' : 'Open file', () => fs.open(el.path).catch(() => {})],
    ['Show in Explorer', () => fs.reveal(el.path).catch(() => {})],
  ];

  if (watching) {
    items.push([el.auto ? 'Stop adding new files' : 'Add new files to this board', () => {
      mutate(() => { el.auto = !el.auto; if (el.auto) el.seen = []; });
    }]);
    items.push([`Showing ${el.kinds === 'images' ? 'images only' : 'everything'} - switch`, () => {
      mutate(() => { el.kinds = el.kinds === 'images' ? 'all' : 'images'; });
    }]);
  }

  items.push([watching ? 'Watch a different folder' : 'Point at a different file', async () => {
    let paths = [];
    try {
      paths = (await api.fsPick(watching ? 'folder' : 'file')).paths;
    } catch { /* typed below */ }
    const chosen = paths[0] || await ask('Path', el.path, 'Relink');
    if (!chosen) return;
    const info = await fs.info(chosen.trim().replace(/^"|"$/g, ''));
    mutate(() => {
      el.path = info.path;
      el.name = info.name;
      if (watching) { el.title = info.name; el.seen = []; }
      else { el.kind = info.kind; el.mtime = info.mtime; }
    });
  }]);

  if (!watching) {
    items.push(['Copy to clipboard', () => api.copyTarget({ path: el.path }).catch(() => {})]);
    items.push(['Save a copy...', () => api.saveCopyTarget({ path: el.path }).catch(() => {})]);
  }
  items.push(['Copy path', () => navigator.clipboard.writeText(el.path).catch(() => {})]);
  menu(ev.clientX, ev.clientY, items);
});

// Image and file cards: get them into other apps, or open where they live.
stage.addEventListener('contextmenu', (ev) => {
  const node = ev.target.closest('.el.image, .el.file');
  if (!node) return;
  const el = byId(node.dataset.id);
  if (!el || !el.src) return;         // empty placeholder has nothing to act on
  ev.preventDefault();
  const target = { project_id: S.project.id, board_id: S.board.id, src: el.src };
  menu(ev.clientX, ev.clientY, [
    ['Copy to clipboard', () => api.copyTarget(target).catch(() => {})],
    ['Save a copy...', () => api.saveCopyTarget(target).catch(() => {})],
    ['Show in Explorer', () => api.revealTarget(target).catch(() => {})],
    [el.type === 'file' ? 'Open file' : 'Open in default app',
      () => api.openAsset(S.project.id, S.board.id, el.src).catch(() => {})],
  ]);
});

// --- trash -----------------------------------------------------------------

let trashed = [];

export async function refreshTrash() {
  if (!S.project) return;
  try {
    trashed = (await api.trash(S.project.id)).boards;
  } catch {
    trashed = [];
  }
  const button = $('#trash-btn');
  button.hidden = !trashed.length;
  $('#trash-count').textContent = trashed.length ? `(${trashed.length})` : '';
}

$('#trash-btn').addEventListener('click', (ev) => {
  if (!trashed.length) return;
  const items = trashed.slice(0, 12).map((entry) => [
    `Restore "${entry.title}"`,
    async () => {
      const board = await api.restoreBoard(S.project.id, entry.id);
      await refreshTree();
      await refreshTrash();
      if (board) loadBoard(board.id);
    },
  ]);
  items.push(['Empty trash', async () => {
    const sure = await confirmBox(
      `Permanently delete ${trashed.length} board${trashed.length === 1 ? '' : 's'}?\n\nThis one cannot be undone.`);
    if (!sure) return;
    await api.emptyTrash(S.project.id);
    refreshTrash();
  }]);
  const rect = ev.currentTarget.getBoundingClientRect();
  menu(rect.left, Math.max(10, rect.top - 40 - items.length * 30), items);
});

// --- templates -------------------------------------------------------------

const tpl = $('#tpl');
let catalogue = null;
let pickTemplate = null;      // callback for whoever opened the gallery
let category = 'All';

async function loadCatalogue() {
  if (!catalogue) catalogue = (await api.templates()).templates;
  return catalogue;
}

export async function showTemplates(title, onPick) {
  await loadCatalogue();
  pickTemplate = onPick;
  category = 'All';
  $('#tpl-title').textContent = title;
  tpl.hidden = false;
  drawTemplates();
}

function drawTemplates() {
  const cats = ['All', ...new Set(catalogue.map((t) => t.category))];
  const bar = tpl.querySelector('.tcats');
  bar.textContent = '';
  cats.forEach((name) => {
    const chip = document.createElement('button');
    chip.className = 'chip' + (name === category ? ' on' : '');
    chip.textContent = name;
    chip.addEventListener('click', () => { category = name; drawTemplates(); });
    bar.appendChild(chip);
  });

  const grid = tpl.querySelector('.tgrid');
  grid.textContent = '';
  catalogue
    .filter((t) => category === 'All' || t.category === category)
    .forEach((template) => {
      const card = document.createElement('button');
      card.className = 'tcard';
      card.innerHTML = '<span class="tcat"></span><b></b><span class="tblurb"></span>';
      card.querySelector('.tcat').textContent = template.category;
      card.querySelector('b').textContent = template.name;
      card.querySelector('.tblurb').textContent = template.blurb;
      card.addEventListener('click', async () => {
        tpl.hidden = true;
        const pick = pickTemplate;
        pickTemplate = null;
        if (pick) await pick(template);
      });
      grid.appendChild(card);
    });
}

/** New board in this project, built from a template. */
async function newBoardFromTemplate(template) {
  const board = await api.boardFromTemplate(S.project.id, template.id, null, template.name);
  await refreshTree();
  await loadBoard(board.id);
}

$('#tpl-close').addEventListener('click', () => { tpl.hidden = true; pickTemplate = null; });
tpl.addEventListener('click', (ev) => {
  if (ev.target === tpl) { tpl.hidden = true; pickTemplate = null; }
});
$('#empty-template').addEventListener('click', () =>
  showTemplates('Start this board from a template', async (template) => {
    // Swap out the empty board you are looking at rather than leaving it behind.
    const old = S.board;
    const built = await api.boardFromTemplate(
      S.project.id, template.id, old.parent_id, template.name);
    if (S.project.home === old.id) await api.setHomeBoard(S.project.id, built.id);
    if (!old.elements.length) await api.deleteBoard(S.project.id, old.id).catch(() => {});
    await refreshProjects();
    await refreshTree();
    await loadBoard(built.id);
  }));

$('#project-switch').addEventListener('click', async () => {
  await refreshProjects();
  showPicker();
});
$('#picker-close').addEventListener('click', () => { picker.hidden = true; });
$('#picker-new').addEventListener('click', newProject);
picker.addEventListener('click', (ev) => {
  if (ev.target === picker && picker.dataset.closable) picker.hidden = true;
});

// --- backups ---------------------------------------------------------------

async function refreshBackupInfo() {
  const info = $('#backup-info');
  try {
    const { backups } = await api.backups();
    if (!backups.length) { info.textContent = 'No backups yet'; return; }
    info.innerHTML = '';
    const last = document.createElement('span');
    last.textContent = `Last backup ${when(backups[0].when)} (${backups.length} kept) - `;
    const open = document.createElement('a');
    open.textContent = 'open folder';
    open.className = 'backup-open';
    open.addEventListener('click', () => api.revealBackups().catch(() => {}));
    info.append(last, open);
  } catch { info.textContent = ''; }
}

$('#picker-backup').addEventListener('click', async (ev) => {
  const btn = ev.currentTarget;
  btn.disabled = true; btn.textContent = 'Backing up...';
  try {
    await api.backupNow();
    btn.textContent = 'Backed up';
  } catch {
    btn.textContent = 'Nothing to back up';
  }
  await refreshBackupInfo();
  setTimeout(() => { btn.disabled = false; btn.textContent = 'Back up now'; }, 1800);
});

// --- shortcuts -------------------------------------------------------------

export const typingIn = (target) =>
  !!(target && target.matches && target.matches('input, textarea, [contenteditable="true"]'));

window.addEventListener('keydown', (ev) => {
  const typing = isEditing() || typingIn(ev.target);
  const mod = ev.ctrlKey || ev.metaKey;

  if (ev.key === 'F5' && S.board) {
    ev.preventDefault();
    if (!present.on) startPresent();
    return;
  }
  if (present.on) {
    if (ev.key === 'Escape') { stopPresent(); return; }
    if (['ArrowRight', ' ', 'PageDown', 'Enter'].includes(ev.key)) {
      ev.preventDefault();
      presentStep(1);
    } else if (['ArrowLeft', 'PageUp'].includes(ev.key)) {
      ev.preventDefault();
      presentStep(-1);
    } else if (ev.key === 'Home') {
      ev.preventDefault();
      presentStep(-present.order.length - 2);   // clamps to the fit-all view
    }
    return;
  }

  if (ev.key === 'Escape') {
    if (isEditing()) exitEdit(); else deselect();
    return;
  }
  if (typing) return;

  if (mod && ev.key.toLowerCase() === 'z') {
    ev.preventDefault();
    ev.shiftKey ? redo() : undo();
  } else if (mod && ev.key.toLowerCase() === 'y') {
    ev.preventDefault();
    redo();
  } else if (mod && ev.key.toLowerCase() === 'd') {
    ev.preventDefault();
    duplicateSelected();
  } else if (mod && ev.key.toLowerCase() === 'c' && S.sel.size) {
    ev.preventDefault();
    copySelection();
  } else if (mod && ev.key.toLowerCase() === 'x' && S.sel.size) {
    ev.preventDefault();
    copySelection({ cut: true });
  } else if (mod && ev.shiftKey && ev.key.toLowerCase() === 'v') {
    // Explicit "paste the cards I copied", for when the clipboard API is blocked.
    ev.preventDefault();
    pasteClipboard(freeSpotNear(centreOfView()));
  } else if (mod && ev.key.toLowerCase() === 'a') {
    ev.preventDefault();
    select(els().map((e) => e.id));
  } else if (mod && ev.key.toLowerCase() === 'f') {
    ev.preventDefault();
    searchInput.focus();
  } else if (ev.key === 'Delete' || ev.key === 'Backspace') {
    ev.preventDefault();
    removeSelected();
  } else if (ev.key === 'Enter' && S.sel.size === 1) {
    ev.preventDefault();
    const node = document.querySelector(`.el[data-id="${[...S.sel][0]}"]`);
    if (node) enterEdit(node);
  } else if (mod && (ev.key === '=' || ev.key === '+')) {
    ev.preventDefault();
    zoomBy(1.2);
  } else if (mod && ev.key === '-') {
    ev.preventDefault();
    zoomBy(1 / 1.2);
  } else if (mod && ev.key === '0') {
    ev.preventDefault();
    resetZoom();
  } else if (['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight'].includes(ev.key) && S.sel.size) {
    ev.preventDefault();
    const step = ev.shiftKey ? 20 : 2;
    const delta = { ArrowUp: [0, -step], ArrowDown: [0, step], ArrowLeft: [-step, 0], ArrowRight: [step, 0] }[ev.key];
    mutate(() => selected().forEach((el) => { el.x += delta[0]; el.y += delta[1]; }));
  }
});

window.addEventListener('beforeunload', flushOnExit);

export { drawCrumbs, drawTree };
