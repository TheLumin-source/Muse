// Thin wrapper over the backend. Every call returns parsed JSON or throws.

async function req(method, url, body) {
  const opts = { method, headers: {} };
  if (body !== undefined) {
    opts.headers['Content-Type'] = 'application/json';
    opts.body = JSON.stringify(body);
  }
  const res = await fetch(url, opts);
  if (!res.ok) throw new Error(`${method} ${url} -> ${res.status}`);
  return res.status === 204 ? null : res.json();
}

const P = (projectId) => `/api/p/${projectId}`;

export const api = {
  // projects
  projects: () => req('GET', '/api/projects'),
  createProject: (name, template) => req('POST', '/api/projects', { name, template }),
  templates: () => req('GET', '/api/templates'),
  boardFromTemplate: (pid, template, parentId, title) =>
    req('POST', `/api/p/${pid}/boards/from-template`,
        { template, parent_id: parentId ?? null, title }),
  renameProject: (id, name) => req('PATCH', `/api/projects/${id}`, { name }),
  setHomeBoard: (id, home) => req('PATCH', `/api/projects/${id}`, { home }),
  deleteProject: (id) => req('DELETE', `/api/projects/${id}`),
  openProject: (id) => req('POST', `/api/projects/${id}/open`),
  revealProject: (id) => req('POST', `/api/projects/${id}/reveal`),

  // boards, always inside a project
  tree: (pid) => req('GET', `${P(pid)}/tree`),
  board: (pid, id) => req('GET', `${P(pid)}/boards/${id}`),
  createBoard: (pid, title, parentId) =>
    req('POST', `${P(pid)}/boards`, { title, parent_id: parentId ?? null }),
  saveBoard: (pid, board) => req('PUT', `${P(pid)}/boards/${board.id}`, board),
  patchBoard: (pid, id, patch) => req('PATCH', `${P(pid)}/boards/${id}`, patch),
  deleteBoard: (pid, id) => req('DELETE', `${P(pid)}/boards/${id}`),
  search: (pid, q) => req('GET', `${P(pid)}/search?q=${encodeURIComponent(q)}`),
  receive: (pid, boardId, from, elements, connectors) =>
    req('POST', `${P(pid)}/boards/${boardId}/receive`, { from, elements, connectors }),
  preview: (pid, boardId) => req('GET', `${P(pid)}/boards/${boardId}/preview`),

  updateCheck: () => req('GET', '/api/update/check'),
  updateApply: (url) => req('POST', '/api/update/apply', { url }),

  backups: () => req('GET', '/api/backups'),
  backupNow: () => req('POST', '/api/backups/now'),
  revealBackups: () => req('POST', '/api/backups/reveal'),

  trash: (pid) => req('GET', `${P(pid)}/trash`),
  restoreBoard: (pid, boardId) => req('POST', `${P(pid)}/trash/${boardId}/restore`),
  purgeBoard: (pid, boardId) => req('DELETE', `${P(pid)}/trash/${boardId}`),
  emptyTrash: (pid) => req('DELETE', `${P(pid)}/trash`),

  fsPick: (mode) => req('POST', '/api/fs/pick', { mode }),
  highlight: (code, lang, dark) => req('POST', '/api/highlight', { code, lang, dark }),
  languages: () => req('GET', '/api/languages'),
  captures: () => req('GET', '/api/captures'),
  exportBoard: (pid, boardId, format = 'html') =>
    req('POST', `${P(pid)}/boards/${boardId}/export`, { format }),
  claimCapture: (name, pid, boardId) =>
    req('POST', `/api/captures/${name}/claim`, { project_id: pid, board_id: boardId }),
  linkPreview: (url, pid, boardId) =>
    req('POST', '/api/link-preview', { url, project_id: pid, board_id: boardId }),
  openAsset: (pid, boardId, src) =>
    req('POST', '/api/open', { project_id: pid, board_id: boardId, src }),

  async upload(pid, boardId, file) {
    const form = new FormData();
    form.append('file', file, file.name || 'pasted');
    const res = await fetch(`${P(pid)}/boards/${boardId}/assets`, { method: 'POST', body: form });
    if (!res.ok) throw new Error(`upload failed: ${res.status}`);
    return res.json();
  },

  /** Last-gasp save as the window closes; survives the page going away. */
  flush(pid, board) {
    const url = `${P(pid)}/boards/${board.id}/beacon`;
    const blob = new Blob([JSON.stringify(board)], { type: 'application/json' });
    if (navigator.sendBeacon && navigator.sendBeacon(url, blob)) return true;
    fetch(url, {
      method: 'POST', body: blob, keepalive: true,
      headers: { 'Content-Type': 'application/json' },
    }).catch(() => {});
    return true;
  },
};

// live files: cards that point at real paths on this machine
export const fs = {
  pick: (mode) => req('POST', '/api/fs/pick', { mode }),
  info: (path) => req('GET', `/api/fs/info?path=${encodeURIComponent(path)}`),
  list: (path, kinds = 'all', limit = 24) =>
    req('GET', `/api/fs/list?path=${encodeURIComponent(path)}&kinds=${kinds}&limit=${limit}`),
  open: (path) => req('POST', '/api/fs/open', { path }),
  reveal: (path) => req('POST', '/api/fs/reveal', { path }),
  // reveal / copy / save work for a real path OR a board asset {project_id,board_id,src}
  revealTarget: (t) => req('POST', '/api/fs/reveal', t),
  copyTarget: (t) => req('POST', '/api/clipboard/copy', t),
  saveCopyTarget: (t) => req('POST', '/api/fs/save-copy', t),
  thumb: (path, size = 320, version = 0) =>
    `/api/fs/thumb?path=${encodeURIComponent(path)}&size=${size}&v=${version}`,
};

export const mediaUrl = (pid, boardId, src) => `/media/${pid}/${boardId}/${src}`;
