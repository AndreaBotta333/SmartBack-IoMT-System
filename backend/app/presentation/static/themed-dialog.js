// Fornisce finestre di conferma e messaggio coerenti con il tema scuro SmartBack.
  const STYLE_ID = "smartback-dialog-style";
  const ROOT_ID = "smartback-dialog-root";

  function hostDocument() {
    try {
      if (window.parent !== window && window.parent.document) return window.parent.document;
    } catch (_) {
      // In caso di origine differente il popup resta nel documento corrente.
    }
    return document;
  }

  function ensureStyle(target) {
    if (target.getElementById(STYLE_ID)) return;
    const style = target.createElement("style");
    style.id = STYLE_ID;
    style.textContent = `
      #${ROOT_ID} {
        position: fixed;
        inset: 0;
        z-index: 2147483647;
        display: grid;
        place-items: center;
        padding: 24px;
        background: rgba(3, 7, 14, .76);
        backdrop-filter: blur(5px);
        -webkit-backdrop-filter: blur(5px);
      }
      #${ROOT_ID} .smartback-dialog {
        box-sizing: border-box;
        width: min(460px, 100%);
        padding: 24px;
        color: #f4f7fb;
        background: #151b26;
        border: 1px solid #344157;
        border-radius: 16px;
        box-shadow: 0 24px 70px rgba(0, 0, 0, .55);
        font: 15px/1.5 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      }
      #${ROOT_ID} .smartback-dialog-title {
        margin: 0 0 10px;
        color: #f4f7fb;
        font-size: 20px;
        font-weight: 750;
      }
      #${ROOT_ID} .smartback-dialog-message {
        margin: 0;
        color: #b8c2d1;
        white-space: pre-line;
      }
      #${ROOT_ID} .smartback-dialog-actions {
        display: flex;
        justify-content: flex-end;
        gap: 10px;
        margin-top: 24px;
      }
      #${ROOT_ID} button {
        min-width: 108px;
        padding: 11px 17px;
        border: 1px solid transparent;
        border-radius: 9px;
        color: #fff;
        background: #3274d9;
        font: inherit;
        font-weight: 750;
        cursor: pointer;
      }
      #${ROOT_ID} button:hover { filter: brightness(1.08); }
      #${ROOT_ID} button:focus-visible {
        outline: 2px solid #75a7f5;
        outline-offset: 2px;
      }
      #${ROOT_ID} .smartback-dialog-cancel {
        color: #d7deea;
        background: #273248;
        border-color: #3a465a;
      }
      @media (max-width: 520px) {
        #${ROOT_ID} { padding: 14px; }
        #${ROOT_ID} .smartback-dialog { padding: 20px; }
        #${ROOT_ID} .smartback-dialog-actions { flex-direction: column-reverse; }
        #${ROOT_ID} button { width: 100%; }
      }
    `;
    target.head.appendChild(style);
  }

  function openDialog({title, message, confirmation}) {
    const target = hostDocument();
    ensureStyle(target);
    target.getElementById(ROOT_ID)?.remove();

    return new Promise((resolve) => {
      const root = target.createElement("div");
      root.id = ROOT_ID;
      root.setAttribute("role", "presentation");

      const panel = target.createElement("section");
      panel.className = "smartback-dialog";
      panel.setAttribute("role", "alertdialog");
      panel.setAttribute("aria-modal", "true");

      const heading = target.createElement("h2");
      heading.className = "smartback-dialog-title";
      heading.textContent = title;
      panel.appendChild(heading);

      const copy = target.createElement("p");
      copy.className = "smartback-dialog-message";
      copy.textContent = message;
      panel.appendChild(copy);

      const actions = target.createElement("div");
      actions.className = "smartback-dialog-actions";

      const close = (value) => {
        target.removeEventListener("keydown", onKeyDown);
        root.remove();
        resolve(value);
      };
      const onKeyDown = (event) => {
        if (event.key === "Escape") close(false);
      };

      if (confirmation) {
        const cancel = target.createElement("button");
        cancel.type = "button";
        cancel.className = "smartback-dialog-cancel";
        cancel.textContent = "Annulla";
        cancel.addEventListener("click", () => close(false));
        actions.appendChild(cancel);
      }

      const accept = target.createElement("button");
      accept.type = "button";
      accept.textContent = confirmation ? "Conferma" : "OK";
      accept.addEventListener("click", () => close(true));
      actions.appendChild(accept);

      panel.appendChild(actions);
      root.appendChild(panel);
      target.body.appendChild(root);
      target.addEventListener("keydown", onKeyDown);
      root.addEventListener("click", (event) => {
        if (event.target === root) close(false);
      });
      accept.focus();
    });
  }

export const smartbackDialog = {
  confirm(message, title = "Conferma operazione") {
    return openDialog({title, message, confirmation: true});
  },
  message(message, title = "SmartBack") {
    return openDialog({title, message, confirmation: false});
  },
};
