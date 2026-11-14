// Background music: starts on the first click or key press (browsers block sound before the user interacts).
// The audio element uses preload="none", so nothing is downloaded until it plays.
(function () {
  var player = document.getElementById("music-audio");
  var toggle = document.getElementById("music-toggle");
  if (!player || !toggle) { return; }
  player.volume = 0.4;

  var on = true;
  try { on = localStorage.getItem("music") !== "off"; } catch (e) { /* storage blocked */ }

  function play() {
    var started = player.play();
    if (started && started.catch) { started.catch(function () { /* blocked or offline: stay quiet */ }); }
  }

  function show() {
    toggle.textContent = on ? "Music: on" : "Music: off";
    toggle.setAttribute("aria-pressed", on ? "true" : "false");
  }

  function firstInteraction(event) {
    if (event.target === toggle || event.target === player) { return; }   // those decide for themselves
    document.removeEventListener("pointerdown", firstInteraction, true);
    document.removeEventListener("keydown", firstInteraction, true);
    if (on) { play(); }
  }

  toggle.addEventListener("click", function () {
    on = !on;
    try { localStorage.setItem("music", on ? "on" : "off"); } catch (e) { /* storage blocked */ }
    if (on) { play(); } else { player.pause(); }
    show();
  });

  show();
  document.addEventListener("pointerdown", firstInteraction, true);
  document.addEventListener("keydown", firstInteraction, true);
})();
