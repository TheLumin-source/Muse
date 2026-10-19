// Element defaults and DOM rendering. One function per card type.

import { mediaUrl, api, fs } from './api.js';
import { S, uid, save, checkpointOnce, endBurst, emit, byId, loadBoard } from './state.js';

export const COLORS = [
  'white', 'yellow', 'amber', 'orange', 'coral', 'red', 'rose', 'pink',
  'purple', 'indigo', 'blue', 'sky', 'teal', 'green', 'lime', 'slate', 'gray',
];

const DEFAULTS = {
  note:   { w: 220, h: 150, color: 'yellow', title: '', text: '' },
  todo:   { w: 240, h: 170, color: 'white', title: 'To-do', items: [] },
  text:   { w: 340, h: 54, color: 'none', text: '' },
  image:  { w: 280, h: 200, color: 'white', src: '', caption: '' },
  link:   { w: 250, h: 210, color: 'white', url: '', title: '', desc: '', site: '', thumb: null },
  file:   { w: 240, h: 68, color: 'white', src: '', name: '', size: 0, ext: '' },
  board:  { w: 210, h: 150, color: 'white', title: 'New board', board_id: null, icon: '' },
  column: { w: 260, h: 300, color: 'slate', title: 'Column', children: [] },
  // Points at a real file on this machine. Nothing is copied.
  live:   { w: 260, h: 220, color: 'white', path: '', name: '', kind: 'file',
            mtime: 0, caption: '' },
  // Points at a real folder and shows what is newest in it.
  watch:  { w: 340, h: 300, color: 'white', path: '', title: '', kinds: 'images',
            limit: 12, auto: false, seen: [] },
  code:   { w: 380, h: 240, color: 'code', title: '', code: '', lang: 'auto' },
};

export function create(type, x, y, extra = {}) {
  const base = DEFAULTS[type] || DEFAULTS.note;
  return {
    id: uid('el'),
    type,
    x: Math.round(x),
    y: Math.round(y),
    parent: null,
    ...structuredClone(base),
    ...extra,
  };
}

/** Cards dropped by their centre feel better than by their top-left corner. */
export function centreOn(el, x, y) {
  el.x = Math.round(x - el.w / 2);
  el.y = Math.round(y - el.h / 2);
  return el;
}

// --- editing helpers -------------------------------------------------------

let editingNode = null;

export function isEditing() {
  return !!editingNode;
}

export function exitEdit() {
  if (!editingNode) return;
  editingNode.classList.remove('editing');
  editingNode.querySelectorAll('[data-edit]').forEach((f) => (f.contentEditable = 'false'));
  editingNode = null;
  endBurst();
  emit('edit-end');
}

export function editingElement() {
  return editingNode ? byId(editingNode.dataset.id) : null;
}

export function enterEdit(node, focus) {
  if (editingNode === node) {
    if (focus && document.activeElement !== focus) focus.focus();
    return;
  }
  exitEdit();
  editingNode = node;
  node.classList.add('editing');
  node.querySelectorAll('[data-edit]').forEach((f) => (f.contentEditable = 'true'));
  emit('edit-start', node);
  const target = focus && focus.dataset.edit ? focus : node.querySelector('[data-edit]');
  if (target) {
    target.focus();
    const range = document.createRange();
    range.selectNodeContents(target);
    range.collapse(false);
    const sel = getSelection();
    sel.removeAllRanges();
    sel.addRange(range);
  }
}

/** Wire a contenteditable field to a field on the element object. */
function bind(node, el, field, { ph = '', html = false, onEnter = null } = {}) {
  node.dataset.edit = field;
  node.dataset.ph = ph;
  node.contentEditable = 'false';
  const value = el[field] || '';
  if (html) node.innerHTML = value;
  else node.textContent = value;

  node.addEventListener('focus', () => checkpointOnce(`${el.id}:${field}`));
  node.addEventListener('input', () => {
    el[field] = html ? node.innerHTML : node.textContent;
    save();
    emit('measure', el);
  });
  node.addEventListener('blur', () => endBurst());
  node.addEventListener('keydown', (ev) => {
    ev.stopPropagation();          // never let Delete/arrows hit the canvas shortcuts
    if (ev.key === 'Escape') {
      ev.preventDefault();
      node.blur();
      exitEdit();
    } else if (ev.key === 'Enter' && onEnter) {
      onEnter(ev);
    }
  });
  node.addEventListener('paste', (ev) => {
    ev.preventDefault();
    const text = (ev.clipboardData || window.clipboardData).getData('text/plain');
    document.execCommand('insertText', false, text);
  });
  return node;
}

const div = (cls, parent) => {
  const node = document.createElement('div');
  if (cls) node.className = cls;
  if (parent) parent.appendChild(node);
  return node;
};

/** Fill a host with a board's icon: an SVG from the bi-* set for a "svg:name"
 *  value, a legacy emoji for any other non-empty string (older boards), or the
 *  default board glyph when empty. SVG renders identically everywhere, unlike
 *  emoji, which the WebView2 shell draws as tofu. */
export function renderBoardIcon(host, value, { fallback = true } = {}) {
  if (value && value.startsWith('svg:')) {
    const id = value.slice(4).replace(/[^a-z0-9-]/g, '');   // our own ids only
    host.innerHTML = `<svg class="ic"><use href="#bi-${id}"/></svg>`;
  } else if (value) {
    host.textContent = value;                                // legacy emoji
  } else if (fallback) {
    host.innerHTML = '<svg class="ic"><use href="#i-board"/></svg>';
  } else {
    host.textContent = '';
  }
}

// --- renderers -------------------------------------------------------------

const renderers = {
  note(el, body) {
    // Title is rich too, so bold/italic in the toolbar work there, not only in
    // the body. Both store HTML.
    bind(div('title', body), el, 'title', { ph: 'Title', html: true });
    bind(div('rich', body), el, 'text', { ph: 'Write something...', html: true });
  },

  text(el, body) {
    // A heading is styled text - it must keep the formatting you apply to it.
    bind(div('rich', body), el, 'text', { ph: 'Heading', html: true });
  },

  todo(el, body) {
    bind(div('title', body), el, 'title', { ph: 'List', html: true });
    const list = div('items', body);
    if (!el.items.length) el.items.push({ id: uid('t'), text: '', done: false });

    el.items.forEach((item, index) => {
      const row = div(`item${item.done ? ' done' : ''}`, list);
      const box = div('box', row);
      box.addEventListener('pointerdown', (ev) => ev.stopPropagation());
      box.addEventListener('click', (ev) => {
        ev.stopPropagation();
        checkpointOnce(`${el.id}:check:${item.id}`);
        endBurst();
        item.done = !item.done;
        row.classList.toggle('done', item.done);
        save();
      });

      const text = div('tx', row);
      text.dataset.edit = `item:${item.id}`;
      text.dataset.ph = 'To-do';
      text.contentEditable = 'false';
      text.textContent = item.text;
      text.addEventListener('focus', () => checkpointOnce(`${el.id}:item:${item.id}`));
      text.addEventListener('input', () => { item.text = text.textContent; save(); });
      text.addEventListener('blur', () => endBurst());
      text.addEventListener('keydown', (ev) => {
        ev.stopPropagation();
        if (ev.key === 'Enter') {
          ev.preventDefault();
          endBurst();
          checkpointOnce(`${el.id}:additem`);
          el.items.splice(index + 1, 0, { id: uid('t'), text: '', done: false });
          save();
          emit('render', { focus: { el: el.id, field: `item:${el.items[index + 1].id}` } });
        } else if (ev.key === 'Backspace' && !text.textContent && el.items.length > 1) {
          ev.preventDefault();
          el.items.splice(index, 1);
          save();
          const prev = el.items[Math.max(0, index - 1)];
          emit('render', { focus: { el: el.id, field: `item:${prev.id}` } });
        } else if (ev.key === 'Escape') {
          text.blur();
          exitEdit();
        }
      });
    });
  },

  image(el, body, node) {
    node.classList.add('image');
    if (el.src) {
      const img = document.createElement('img');
      img.src = mediaUrl(S.project.id, S.board.id, el.src);
      img.alt = el.caption || '';
      img.draggable = false;
      img.addEventListener('error', () => {
        img.remove();
        div('missing', node).textContent = 'Image missing';
      });
      node.appendChild(img);
      // Hover zoom -> open the full-size lightbox (ui.js listens for .zoom).
      const zoom = div('zoom', node);
      zoom.dataset.zoomFor = el.id;
      zoom.title = 'View full size';
      zoom.innerHTML = '<svg class="ic"><use href="#i-search"/></svg>';
    } else {
      // A placeholder from a template: drop a picture straight onto it.
      node.classList.add('placeholder');
      div('missing', node).textContent = el.caption ? `Drop ${el.caption.toLowerCase()}` : 'Drop an image';
    }
    const cap = div(`cap${el.caption ? ' has' : ''}`, node);
    bind(cap, el, 'caption', { ph: 'Caption' });
    cap.addEventListener('input', () => cap.classList.toggle('has', !!el.caption));
  },

  link(el, body, node) {
    node.classList.add('link');
    const thumb = div('thumb', node);
    if (el.thumb) thumb.style.backgroundImage = `url("${mediaUrl(S.project.id, S.board.id, el.thumb)}")`;
    else thumb.style.display = 'none';
    const meta = div('meta', node);
    bind(div('lt', meta), el, 'title', { ph: 'Link' });
    if (el.desc) div('ld', meta).textContent = el.desc;
    div('site', meta).textContent = el.site || el.url;
    node.title = el.url;
  },

  file(el, body, node) {
    node.classList.add('file');
    node.title = `Open ${el.name}`;
    if (el.thumb) {
      // Document preview (e.g. a rendered PDF page) with a name strip beneath.
      node.classList.add('withthumb');
      const shot = div('fthumb', node);
      const img = document.createElement('img');
      img.src = mediaUrl(S.project.id, S.board.id, el.thumb);
      img.draggable = false;
      img.addEventListener('error', () => { img.remove(); shot.textContent = (el.ext || 'file').toUpperCase(); });
      shot.appendChild(img);
      const foot = div('ffoot', node);
      div('fname', foot).textContent = el.name || 'File';
      return;
    }
    div('ext', node).textContent = (el.ext || 'file').slice(0, 4).toUpperCase();
    const meta = div('', node);
    div('fname', meta).textContent = el.name || 'File';
    div('fsize', meta).textContent = formatSize(el.size);
  },

  board(el, body, node) {
    node.classList.add('board');
    // A Milanote-style board tile: a big customizable icon (emoji or the default
    // board glyph) with the name and card count beneath. The icon and colour are
    // set from the contextual toolbar when the card is selected.
    const face = div('bface', node);
    const icon = div('bicon', face);
    icon.dataset.iconFor = el.id;
    renderBoardIcon(icon, el.icon);
    icon.title = 'Double-click to open this board';
    const titles = div('btitles', node);
    bind(div('btitle', titles), el, 'title', { ph: 'Board' });
    const count = div('bcount', titles);
    count.textContent = '';
    if (el.board_id) boardCount(el.board_id, count);
  },

  column(el, body, node) {
    node.classList.add('column');
    bind(div('chead', node), el, 'title', { ph: 'Column' });
  },

  code(el, body, node) {
    node.classList.add('code');
    const head = div('khead', node);
    const lang = document.createElement('button');
    lang.className = 'klang';
    lang.dataset.langFor = el.id;      // ui.js opens the language menu
    lang.title = 'Set language';
    lang.textContent = el.lang === 'auto' ? 'detect' : el.lang;
    lang.addEventListener('pointerdown', (ev) => ev.stopPropagation());
    const copy = document.createElement('button');
    copy.className = 'kcopy';
    copy.textContent = 'Copy';
    copy.addEventListener('pointerdown', (ev) => ev.stopPropagation());
    copy.addEventListener('click', async (ev) => {
      ev.stopPropagation();
      try {
        await navigator.clipboard.writeText(el.code || '');
        copy.textContent = 'Copied';
        setTimeout(() => { copy.textContent = 'Copy'; }, 1400);
      } catch { copy.textContent = 'Ctrl+C'; }
    });
    head.append(lang, copy);

    // An always-editable code screen: click in and type. The highlighted <pre>
    // sits behind a transparent <textarea> that owns the caret, both perfectly
    // aligned. No mode switch, so nothing to break.
    const editor = div('keditor', node);
    const pre = document.createElement('pre');
    // Code cards are a dark surface in both themes, so always the dark palette.
    pre.className = 'hl dark';
    pre.setAttribute('aria-hidden', 'true');
    pre.textContent = el.code || '';
    const area = document.createElement('textarea');
    area.className = 'kcode';
    area.spellcheck = false;
    area.value = el.code || '';
    area.placeholder = 'Type or paste code here...';
    editor.append(pre, area);

    const syncScroll = () => { pre.scrollTop = area.scrollTop; pre.scrollLeft = area.scrollLeft; };
    paintCode(el, pre, lang);

    // The code area owns clicks/keys - never let them drag the card or fire
    // canvas shortcuts.
    area.addEventListener('pointerdown', (ev) => ev.stopPropagation());
    area.addEventListener('scroll', syncScroll);
    area.addEventListener('focus', () => checkpointOnce(`${el.id}:code`));
    area.addEventListener('blur', () => endBurst());
    area.addEventListener('keydown', (ev) => {
      ev.stopPropagation();
      if (ev.key === 'Tab') {
        ev.preventDefault();
        const at = area.selectionStart;
        area.setRangeText('  ', at, area.selectionEnd, 'end');
        area.dispatchEvent(new Event('input', { bubbles: true }));
      }
    });
    area.addEventListener('input', () => {
      el.code = area.value;
      pre.textContent = area.value;   // keep text visible + aligned immediately
      syncScroll();
      save();
      scheduleHighlight(el, pre, lang);
    });
  },

  live(el, body, node) {
    node.classList.add('live');
    const frame = div('lframe', node);
    if (el.kind === 'image' || el.kind === 'pdf') {
      const img = document.createElement('img');
      img.src = fs.thumb(el.path, 480, el.mtime);
      img.draggable = false;
      img.addEventListener('error', () => { img.remove(); missingArt(frame, el); });
      frame.appendChild(img);
    } else {
      missingArt(frame, el);
    }

    const foot = div('lfoot', node);
    div('lname', foot).textContent = el.name || el.path || 'No file chosen';
    const badge = div('lbadge', foot);
    badge.textContent = 'live';
    badge.title = `Linked to ${el.path}\nThis card shows the file as it is now.`;
    node.title = el.path;

    refreshLive(el, node);
  },

  watch(el, body, node) {
    node.classList.add('watch');
    const head = div('whead', node);
    head.innerHTML = '<svg class="ic"><use href="#i-watch"/></svg>';
    const title = div('wtitle', head);
    title.textContent = el.title || el.path.split(/[\\/]/).pop() || 'Watch a folder';
    title.title = el.path;
    const count = div('wcount', head);
    const grid = div('wgrid', node);
    grid.dataset.watch = el.id;
    div('wempty', grid).textContent = el.path ? 'Looking...' : 'No folder chosen';
    if (el.auto) node.classList.add('auto');
    refreshWatch(el, node, count, grid);
  },
};

// --- code cards -------------------------------------------------------------

const codeCache = new Map();

/** Ask the server for highlighted HTML, then swap it in. */
async function paintCode(el, pre, langLabel) {
  if (!el.code) return;
  const dark = true;   // code cards are always a dark surface
  const key = `${el.lang}|${dark}|${el.code}`;
  let result = codeCache.get(key);
  if (!result) {
    try {
      result = await api.highlight(el.code, el.lang, dark);
      codeCache.set(key, result);
    } catch {
      return;      // plain text is already on screen, which is a fine fallback
    }
  }
  // Do not gate on pre.isConnected: render() builds the node and calls us
  // before appending it, so on a cache hit the pre is briefly detached.
  // Writing to it now is harmless - it is appended immediately after.
  pre.innerHTML = result.html || (el.code || '');
  if (langLabel && el.lang === 'auto' && result.lang) langLabel.textContent = result.lang;
}

// Re-highlight a code card a beat after typing stops (not every keystroke).
const highlightTimers = new WeakMap();
function scheduleHighlight(el, pre, langLabel) {
  clearTimeout(highlightTimers.get(pre));
  highlightTimers.set(pre, setTimeout(() => paintCode(el, pre, langLabel), 250));
}

function missingArt(frame, el) {
  const box = div('lmissing', frame);
  const kinds = { '3d': '3D', design: 'PSD', video: 'VIDEO', folder: 'FOLDER' };
  div('lext', box).textContent = kinds[el.kind]
    || (el.name || '').split('.').pop().slice(0, 4).toUpperCase() || 'FILE';
}

/** Ask the machine whether the file still exists and whether it changed. */
async function refreshLive(el, node) {
  if (!el.path) return;
  try {
    const info = await fs.info(el.path);
    if (!node.isConnected) return;
    node.classList.toggle('gone', !info.exists);
    if (!info.exists) {
      const foot = node.querySelector('.lbadge');
      if (foot) { foot.textContent = 'missing'; foot.classList.add('bad'); }
      return;
    }
    if (info.mtime !== el.mtime) {
      el.mtime = info.mtime;
      el.name = info.name;
      el.kind = info.kind;
      const img = node.querySelector('.lframe img');
      if (img) img.src = fs.thumb(el.path, 480, el.mtime);
      save();
    }
  } catch { /* the machine is busy; try again on the next pass */ }
}

async function refreshWatch(el, node, count, grid) {
  if (!el.path) return;
  let data;
  try {
    data = await fs.list(el.path, el.kinds, el.limit);
  } catch {
    return;
  }
  if (!node.isConnected) return;
  node.classList.toggle('gone', !data.exists);
  count.textContent = data.exists ? `${data.total}` : 'missing';

  grid.textContent = '';
  if (!data.files.length) {
    div('wempty', grid).textContent = data.exists ? 'Nothing here yet' : 'Folder not found';
  }
  data.files.forEach((file) => {
    const cell = div('wcell', grid);
    cell.title = `${file.name}\nDouble-click to open`;
    if (file.kind === 'image') {
      const img = document.createElement('img');
      img.src = fs.thumb(file.path, 200, file.mtime);
      img.draggable = false;
      cell.appendChild(img);
    } else {
      div('wext', cell).textContent = file.name.split('.').pop().slice(0, 4).toUpperCase();
    }
    cell.addEventListener('dblclick', (ev) => {
      ev.stopPropagation();
      fs.open(file.path).catch(() => {});
    });
  });

  emit('watch-files', { el, files: data.files });
}

// A board card shows how much its board holds. Cache the peek so re-renders and
// repeated cards do not each hit the server.
const miniCache = new Map();

export function forgetMiniature(boardId) {
  miniCache.delete(boardId);
}

async function boardCount(boardId, countEl) {
  let elements = miniCache.get(boardId);
  if (!elements) {
    try {
      elements = (await api.preview(S.project.id, boardId)).elements;
      miniCache.set(boardId, elements);
    } catch {
      return;
    }
  }
  if (!countEl || !countEl.isConnected) return;
  // "2 boards, 1 card" style count, like Milanote. Boards = board cards on it,
  // cards = everything else that isn't just a column container.
  const boards = elements.filter((e) => e.type === 'board').length;
  const cards = elements.filter((e) => !['board', 'column'].includes(e.type)).length;
  const parts = [];
  if (boards) parts.push(`${boards} board${boards === 1 ? '' : 's'}`);
  parts.push(`${cards} card${cards === 1 ? '' : 's'}`);
  countEl.textContent = parts.join(', ');
}

function formatSize(bytes) {
  if (!bytes) return '';
  const units = ['B', 'KB', 'MB', 'GB'];
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) { value /= 1024; unit += 1; }
  return `${value < 10 && unit ? value.toFixed(1) : Math.round(value)} ${units[unit]}`;
}

const NUB_SIDES = ['n', 'e', 's', 'w'];

/** Build the DOM node for one element. */
export function renderElement(el) {
  const node = document.createElement('div');
  node.className = `el ${el.type}`;
  node.dataset.id = el.id;
  if (el.parent) node.classList.add('child');
  if (el.color && el.color !== 'none' && el.color !== 'white' && el.type !== 'column') {
    // The colour drives --tint. Text cards use it as their background; cards
    // with their own surface (image/code/live/watch) show it as a frame. A hex
    // value is a custom colour set inline; a name maps to a theme class.
    node.classList.add('colored');
    if (el.color[0] === '#') node.style.setProperty('--tint', el.color);
    else node.classList.add(`c-${el.color}`);
  }
  place(node, el);

  const body = div('body', node);
  const render = renderers[el.type] || renderers.note;
  render(el, body, node);
  if (['image', 'link', 'file', 'board', 'column', 'live', 'watch', 'code'].includes(el.type)) body.remove();

  const grip = div('grip', node);
  grip.dataset.grip = '1';
  NUB_SIDES.forEach((side) => {
    const nub = div(`nub ${side}`, node);
    nub.dataset.nub = side;
  });

  if (el.type === 'link') {
    node.addEventListener('dblclick', (ev) => {
      if (ev.target.dataset.edit) return;
      window.open(el.url, '_blank', 'noopener');
    });
  }
  // These cards handle their own double-click, so stop it bubbling to the
  // canvas handler (which would otherwise treat it as a click on empty space).
  if (el.type === 'file') {
    node.addEventListener('dblclick', (ev) => {
      ev.stopPropagation();
      api.openAsset(S.project.id, S.board.id, el.src).catch(() => {});
    });
  }
  if (el.type === 'live') {
    node.addEventListener('dblclick', (ev) => {
      ev.stopPropagation();
      fs.open(el.path).catch(() => {});
    });
  }
  if (el.type === 'watch') {
    node.addEventListener('dblclick', (ev) => {
      ev.stopPropagation();
      if (ev.target.closest('.wcell')) return;
      fs.open(el.path).catch(() => {});
    });
  }
  // A board card opens its board on double-click. Handle it directly on the card
  // and stop it bubbling, so it can never fall through to the canvas handler and
  // spawn a note. Double-clicking the title still edits the name (it has
  // data-edit), matching the other cards above.
  if (el.type === 'board') {
    node.addEventListener('dblclick', (ev) => {
      if (ev.target.dataset.edit) return;
      ev.stopPropagation();
      if (el.board_id) loadBoard(el.board_id);
    });
  }
  return node;
}

/** Re-check every live card against the disk. Called on a timer by the canvas. */
export function tickLiveCards() {
  document.querySelectorAll('.el.live').forEach((node) => {
    const el = byId(node.dataset.id);
    if (el) refreshLive(el, node);
  });
  document.querySelectorAll('.el.watch').forEach((node) => {
    const el = byId(node.dataset.id);
    if (!el) return;
    refreshWatch(el, node, node.querySelector('.wcount'), node.querySelector('.wgrid'));
  });
}

export function place(node, el) {
  node.style.left = `${el.x}px`;
  node.style.top = `${el.y}px`;
  node.style.width = `${el.w}px`;
  node.style.height = `${el.h}px`;
}

/** Column geometry: children are laid out in a stack and own the column's height. */
export const COL = { pad: 10, gap: 8, head: 32 };

export function layoutColumn(col) {
  let y = col.y + COL.head;
  col.children = (col.children || []).filter((id) => byId(id));
  col.children.forEach((id) => {
    const child = byId(id);
    child.parent = col.id;
    child.x = col.x + COL.pad;
    child.w = col.w - COL.pad * 2;
    child.y = y;
    y += child.h + COL.gap;
  });
  col.h = Math.max(140, y - col.y + COL.pad - (col.children.length ? COL.gap : 0));
}

export function layoutAllColumns() {
  (S.board ? S.board.elements : []).forEach((el) => {
    if (el.type === 'column') layoutColumn(el);
  });
}
