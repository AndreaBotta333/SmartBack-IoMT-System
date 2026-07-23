const main = document.querySelector("main");
const select = document.getElementById("sessions");
const search = document.getElementById("search");
const current = main.dataset.current;
const mode = main.dataset.mode;
const original = [...select.options].map((option) => ({
  value: option.value,
  start: option.dataset.start || "",
  stop: option.dataset.stop || "",
  text: option.text,
}));

function render(filter = "") {
  const selected = select.value || current;
  const needle = filter.trim().toLocaleLowerCase("it");
  select.replaceChildren(...original
    .filter((option) => !needle || option.text.toLocaleLowerCase("it").includes(needle))
    .map((option) => {
      const node = new Option(option.text, option.value, false, option.value === selected);
      node.dataset.start = option.start;
      node.dataset.stop = option.stop;
      return node;
    }));
}

function choose(value, start, stop) {
  if (!value || !start || !stop) return;
  const url = new URL(window.parent.location.href);
  url.searchParams.set("var-session_id", value);
  if (mode === "day") {
    url.searchParams.set("var-alert_day_start", start);
    url.searchParams.set("var-alert_day_stop", stop);
    url.searchParams.delete("var-session_filter");
  }
  url.searchParams.set("from", String(Date.parse(start)));
  url.searchParams.set("to", String(Date.parse(stop)));
  window.parent.location.assign(url.toString());
}

render();
if (original.length && !original.some((option) => option.value === current)) {
  choose(original[0].value, original[0].start, original[0].stop);
}
search.addEventListener("input", () => render(search.value));
select.addEventListener("change", () => {
  const option = select.selectedOptions[0];
  choose(select.value, option.dataset.start, option.dataset.stop);
});
