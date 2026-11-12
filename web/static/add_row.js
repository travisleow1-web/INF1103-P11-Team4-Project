// "Add row": copy the last shipment row with its boxes emptied.
document.getElementById("add-row").addEventListener("click", function () {
  var body = document.querySelector("#rows tbody");
  var copy = body.rows[body.rows.length - 1].cloneNode(true);
  copy.querySelectorAll("input").forEach(function (input) { input.value = ""; });
  body.appendChild(copy);
});
