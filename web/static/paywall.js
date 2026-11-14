// A prank paywall (on the search and assess pages). Any choice reveals the joke; nothing is charged or sent.
// Each page's paywall shows once per browser tab, and the page works normally without JavaScript.
(function () {
  var dialog = document.getElementById("paywall");
  if (!dialog || typeof dialog.showModal !== "function") { return; }
  var seen = "paywall-seen-" + (dialog.getAttribute("data-key") || "page");
  try {
    if (sessionStorage.getItem(seen)) { return; }
    sessionStorage.setItem(seen, "1");
  } catch (e) { /* storage blocked: show it anyway */ }

  var offer = document.getElementById("paywall-offer");
  var joke = document.getElementById("paywall-joke");
  var close = document.getElementById("paywall-close");

  function reveal() {
    offer.hidden = true;
    joke.hidden = false;
    close.focus();
  }

  dialog.querySelectorAll(".paywall-pick").forEach(function (button) {
    button.addEventListener("click", reveal);
  });
  dialog.addEventListener("cancel", function (event) {   // Esc shows the joke first instead of slipping past it
    if (joke.hidden) { event.preventDefault(); reveal(); }
  });
  close.addEventListener("click", function () { dialog.close(); });

  dialog.showModal();
})();
