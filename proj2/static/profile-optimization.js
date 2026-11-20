for (const row of document.querySelectorAll("#optimization-preferences .optimization-row")) {
  const slider = row.querySelector('input[type="range"]');
  const output = row.querySelector("output");
  slider.addEventListener("input", () => {
    output.value = slider.value;
  });
}
