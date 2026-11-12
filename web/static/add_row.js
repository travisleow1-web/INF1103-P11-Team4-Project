// "Add row": copy the last shipment row with its boxes emptied and its error marks removed.
document.getElementById("add-row").addEventListener("click", function () {
  var body = document.querySelector("#rows tbody");
  var entries = body.querySelectorAll("tr.entry");
  var copy = entries[entries.length - 1].cloneNode(true);
  copy.classList.remove("has-errors");
  copy.querySelectorAll("input").forEach(function (input) {
    input.value = "";
    input.removeAttribute("aria-invalid");
    input.removeAttribute("aria-describedby");
  });
  body.appendChild(copy);
});
