// Bootstrap: pick up where you left off - same project, same board.

import * as state from './state.js';
import { S, loadBoard, loadProject, refreshProjects } from './state.js';
import { refreshTree, openProject, showPicker } from './ui.js';
import * as board from './board.js';
import * as elements from './elements.js';
import * as ui from './ui.js';
import { applyView } from './board.js';
import { api } from './api.js';

// --- auto update -----------------------------------------------------------

async function checkForUpdate() {
  let info;
  try { info = await api.updateCheck(); } catch { return; }
  if (!info.available) return;
  const bar = document.getElementById('update-bar');
  document.getElementById('update-text').textContent =
    `Muse ${info.latest} is available.` + (info.notes ? ` ${info.notes}` : '');
  bar.hidden = false;
  document.getElementById('update-later').onclick = () => { bar.hidden = true; };
  document.getElementById('update-now').onclick = async () => {
    const btn = document.getElementById('update-now');
    btn.disabled = true;
    btn.textContent = 'Downloading...';
    try {
      await state.flush();
      await api.updateApply(info.url);      // app will close and reinstall itself
      document.getElementById('update-text').textContent = 'Installing update - Muse will reopen...';
    } catch {
      btn.disabled = false;
      btn.textContent = 'Update now';
      document.getElementById('update-text').textContent = 'Update failed. Try again later.';
    }
  };
}

// Handy from the browser console when poking at a board.
window.muse = { state, board, elements, ui, S };

const BOARD_ID = /^b_[0-9a-f]{8}$/;
const PROJECT_ID = /^p_[0-9a-f]{8}$/;

function fromHash() {
  const [project, board_] = location.hash.slice(1).split('/');
  return {
    project: PROJECT_ID.test(project) ? project : null,
    board: BOARD_ID.test(board_) ? board_ : null,
  };
}

async function showBuild() {
  try {
    const info = await (await fetch('/api/version')).json();
    const stamp = `v${info.version} (${info.build})`;
    document.getElementById('app-build').textContent = stamp;
    console.log(`Muse ${stamp} loaded`);
  } catch { /* offline is fine */ }
}

async function boot() {
  const data = await refreshProjects();
  document.getElementById('picker-root').textContent = data.root;
  showBuild();

  const wanted = fromHash();
  const project =
    S.projects.find((p) => p.id === wanted.project) ||
    S.projects.find((p) => p.id === data.current) ||
    S.projects[0];

  if (!project) return showPicker(false);

  const home = await loadProject(project);
  document.getElementById('project-name').textContent = project.name;
  const target = wanted.board || data.last_board || home;
  try {
    await loadBoard(target);
  } catch {
    await loadBoard(home);
  }
  await refreshTree();
  applyView();
  setTimeout(checkForUpdate, 2500);   // quietly, after the board is up
}

window.addEventListener('hashchange', () => {
  const wanted = fromHash();
  if (!wanted.board || !S.board || wanted.board === S.board.id) return;
  if (wanted.project && S.project && wanted.project !== S.project.id) {
    const project = S.projects.find((p) => p.id === wanted.project);
    if (project) return openProject(project);
  }
  loadBoard(wanted.board).then(refreshTree).catch(() => {});
});

boot().catch((err) => {
  console.error(err);
  document.body.insertAdjacentHTML(
    'afterbegin',
    '<p style="padding:14px">Muse could not start. Is the server running?</p>',
  );
});
