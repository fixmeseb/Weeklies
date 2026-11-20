(() => {
  const form = document.getElementById("optimization-form");
  if (!form) return;

  const rows = new Map(
    [...form.querySelectorAll("[data-objective]")].map(row => [row.dataset.objective, row])
  );
  const select = document.getElementById("optimization-objective");
  const add = document.getElementById("add-optimization");
  const empty = document.getElementById("optimization-empty");

  function refreshOptions() {
    for (const option of select.options) {
      option.hidden = option.disabled = !rows.get(option.value).hidden;
    }
    const next = [...select.options].find(option => !option.disabled);
    select.value = next ? next.value : "";
    select.disabled = add.disabled = !next;
    empty.hidden = [...rows.values()].some(row => !row.hidden);
  }

  for (const row of rows.values()) {
    const slider = row.querySelector("input");
    const output = row.querySelector("output");
    slider.addEventListener("input", () => {
      output.value = slider.value;
    });
    row.querySelector("[data-remove-preference]").addEventListener("click", () => {
      row.hidden = slider.disabled = true;
      refreshOptions();
      select.value = row.dataset.objective;
      select.focus();
    });
  }

  add.addEventListener("click", () => {
    const row = rows.get(select.value);
    if (!row) return;
    const slider = row.querySelector("input");
    row.hidden = slider.disabled = false;
    slider.value = row.querySelector("output").value = 50;
    refreshOptions();
    slider.focus();
  });

  refreshOptions();
})();
