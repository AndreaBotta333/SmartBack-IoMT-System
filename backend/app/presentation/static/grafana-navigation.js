// Forza il ritorno alla Home SmartBack fuori dal router interno di Grafana.
document.addEventListener("click", (event) => {
  const link = event.target.closest?.('a[href]');
  if (!link) return;

  const destination = new URL(link.href, window.location.href);
  if (!["/smartback/", "/grafana/smartback/"].includes(destination.pathname)) {
    return;
  }

  event.preventDefault();
  event.stopPropagation();
  event.stopImmediatePropagation();
  window.location.assign(`/smartback/${destination.search}${destination.hash}`);
}, true);
