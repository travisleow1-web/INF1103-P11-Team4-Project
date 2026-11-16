(function () {
  var clickCount = 0;
  var hits = 0;
  var misses = 0;
  var hitCount = document.getElementById("pp-hits");
  var missCount = document.getElementById("pp-misses");
  var ppValue = document.getElementById("pp-value");

  if (!hitCount || !missCount || !ppValue) { return; }
  
  document.addEventListener("click", function (event) {
    var target = event.target;
    clickCount += 1;
    if (target instanceof Element && target.closest("button")) {
      hits += 1;
    } else {
      misses += 1;
    }

    var multiplier = (hits/clickCount);
    var pp = Math.floor(Math.max(0, 10 * hits * multiplier));

    hitCount.textContent = String(hits);
    missCount.textContent = String(misses);
    ppValue.textContent = String(pp);
  });
}());
