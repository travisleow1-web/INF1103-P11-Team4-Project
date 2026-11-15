// "Show suggested dates": while the switch is on, rows that have a suggested new date come first, then the
// other high-risk rows (they show why there is none), then the rest, so nothing needs scrolling.
// Turning the switch off puts the rows back in their original order. Without JavaScript the order is unchanged.
(function () {
  var original = null;                         // the row groups in their first order, kept to undo the sort

  function groups(body) {                      // a summary row plus the rows after it (date line, details)
    var list = [];
    Array.prototype.forEach.call(body.children, function (row) {
      if (row.classList.contains("summary") || !list.length) { list.push([]); }
      list[list.length - 1].push(row);
    });
    return list;
  }

  function rank(group) {                      // 0 = new date suggested, 1 = high risk without one, 2 = other
    var value = parseInt(group[0].getAttribute("data-rank"), 10);
    return isNaN(value) ? 2 : value;
  }

  function show(body, list) {
    list.forEach(function (group) { group.forEach(function (row) { body.appendChild(row); }); });
  }

  document.addEventListener("change", function (event) {
    var box = event.target;
    if (box.id !== "show-dates") { return; }
    var body = document.querySelector("table.results tbody");
    if (!body) { return; }
    original = original || groups(body);
    if (box.checked) {
      var sorted = original.map(function (group, i) { return { group: group, i: i }; });
      sorted.sort(function (a, b) { return rank(a.group) - rank(b.group) || a.i - b.i; });   // stable
      show(body, sorted.map(function (entry) { return entry.group; }));
    } else {
      show(body, original);
    }
  });
})();
