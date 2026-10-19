// In-app ask/confirm dialogs. window.prompt() does not exist inside the
// desktop window (WebView2 returns null without asking), so nothing in Muse
// may ever call prompt() or confirm() - use these instead.

function build(kind, message, value, okLabel) {
  return new Promise((resolve) => {
    const wrap = document.createElement('div');
    wrap.className = 'dlg-wrap';
    wrap.innerHTML = `
      <div class="dlg">
        <div class="dlg-msg"></div>
        ${kind === 'ask' ? '<input class="dlg-in" type="text" spellcheck="false">' : ''}
        <div class="dlg-row">
          <button class="dlg-cancel">Cancel</button>
          <button class="dlg-ok"></button>
        </div>
      </div>`;
    wrap.querySelector('.dlg-msg').textContent = message;
    const okButton = wrap.querySelector('.dlg-ok');
    okButton.textContent = okLabel;
    if (/delete|remove|empty/i.test(okLabel)) okButton.classList.add('danger');
    const input = wrap.querySelector('.dlg-in');
    if (input) input.value = value || '';

    const done = (result) => { wrap.remove(); resolve(result); };
    const cancelValue = kind === 'ask' ? null : false;

    okButton.addEventListener('click', () => done(kind === 'ask' ? input.value : true));
    wrap.querySelector('.dlg-cancel').addEventListener('click', () => done(cancelValue));
    wrap.addEventListener('pointerdown', (ev) => {
      if (ev.target === wrap) done(cancelValue);
      ev.stopPropagation();            // never reaches the canvas behind it
    });
    wrap.addEventListener('keydown', (ev) => {
      ev.stopPropagation();            // Delete/arrows must not hit the board
      if (ev.key === 'Enter') { ev.preventDefault(); okButton.click(); }
      else if (ev.key === 'Escape') done(cancelValue);
    });

    document.body.appendChild(wrap);
    if (input) { input.focus(); input.select(); } else okButton.focus();
  });
}

/** Text question. Resolves to the string, or null on cancel - like prompt(). */
export const ask = (message, value = '', okLabel = 'OK') =>
  build('ask', message, value, okLabel);

/** Yes/no question. Resolves to true/false - like confirm(). */
export const confirmBox = (message, okLabel = 'Delete') =>
  build('confirm', message, '', okLabel);
