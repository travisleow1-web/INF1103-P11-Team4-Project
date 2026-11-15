// Calendar button for the DD/MM/YYYY boxes. The box stays the only submitted field: the button opens
// the browser's own date picker (a hidden <input type="date">) and copies the chosen day into the box.
// An arrival or "to" picker cannot go before the start box of the same table row or filter group.
(function () {
  document.documentElement.classList.add("has-datepicker");   // CSS shows the buttons only with JavaScript

  function parse(text) {                    // "DD/MM/YYYY" -> Date (UTC midnight), or null when it is not a real day
    var m = /^\s*(\d{1,2})\/(\d{1,2})\/(\d{4})\s*$/.exec(text);
    if (!m) { return null; }
    var day = new Date(Date.UTC(+m[3], +m[2] - 1, +m[1]));
    var real = day.getUTCFullYear() === +m[3] && day.getUTCMonth() === +m[2] - 1 && day.getUTCDate() === +m[1];
    return real ? day : null;
  }

  function isoText(day) { return day.toISOString().slice(0, 10); }

  function textBox(field) { return field.querySelector("input:not([type='date'])"); }

  function startBox(field) {                // the start box next to this end field
    var group = field.closest("tr.entry, .filters");
    var start = group && group.querySelector(".date-field[data-range='start']");
    return start && textBox(start);
  }

  document.addEventListener("click", function (event) {
    var button = event.target.closest(".date-button");
    if (!button) { return; }
    var field = button.closest(".date-field");
    var native = field.querySelector("input[type='date']");
    var current = parse(textBox(field).value);
    native.value = current ? isoText(current) : "";
    native.min = "";
    if (field.dataset.range === "end") {
      var start = startBox(field);
      var from = start && parse(start.value);
      if (from) {
        native.min = isoText(new Date(from.getTime() + (+field.dataset.gap || 0) * 86400000));
      }
    }
    try { native.showPicker(); } catch (problem) { native.focus(); }
  });

  document.addEventListener("change", function (event) {
    var native = event.target;
    if (!native.matches || !native.matches(".date-native") || !native.value) { return; }
    var parts = native.value.split("-");    // YYYY-MM-DD from the picker
    var box = textBox(native.closest(".date-field"));
    box.value = parts[2] + "/" + parts[1] + "/" + parts[0];
    box.dispatchEvent(new Event("input", { bubbles: true }));
  });
})();
