// A safe stand-in for localStorage.
//
// Not every WebView hands the page a working DOM storage. pywebview's GTK
// backend runs WebKit with an ephemeral website data manager unless it is
// started with private_mode=False, and in that mode localStorage is not merely
// empty, it is absent: touching the bare name throws ReferenceError rather than
// returning undefined. One unguarded top-level read is then enough to kill the
// whole module graph, which is exactly how the Linux window used to sit at
// "Loading" forever with an empty board.
//
// So: never touch the global directly. Everything here falls back to session
// storage and then to memory, so a host without persistence costs you a
// remembered preference for that run and never the app itself.

const memory = new Map();

// Reading globalThis[name] returns undefined for a missing global instead of
// throwing, which is the whole point. The write probe catches the other case:
// a store that exists but rejects everything (private windows, blocked site
// data, a full quota).
function usable(name) {
  try {
    const store = globalThis[name];
    if (!store) return null;
    const probe = '__muse_probe__';
    store.setItem(probe, '1');
    store.removeItem(probe);
    return store;
  } catch {
    return null;
  }
}

const backing = usable('localStorage') || usable('sessionStorage');

// True only when a choice made now will still be there next launch. Nothing
// depends on this yet; it is here so a caller can say so in the UI.
export const persists = backing === globalThis.localStorage && !!backing;

export const storage = {
  getItem(key) {
    if (backing) {
      try {
        return backing.getItem(key);
      } catch { /* fall through to whatever this run has remembered */ }
    }
    return memory.has(key) ? memory.get(key) : null;
  },

  // Memory is written first and always, so a backing store that throws midway
  // (a full quota is the usual one) still leaves the value readable this run.
  setItem(key, value) {
    const text = String(value);
    memory.set(key, text);
    if (!backing) return;
    try {
      backing.setItem(key, text);
    } catch { /* quota or blocked: memory is holding it */ }
  },

  removeItem(key) {
    memory.delete(key);
    if (!backing) return;
    try {
      backing.removeItem(key);
    } catch { /* nothing worth reporting */ }
  },
};
