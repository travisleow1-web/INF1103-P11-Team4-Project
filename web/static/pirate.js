(function () {
  var button = document.getElementById("crate-open");
  var video = document.getElementById("pirate-overlay");
  if (!button || !video) { return; }
  var fallbackSrc = video.getAttribute("data-fallback-src");
  var fallbackUsed = false;

  function playOverlay() {
    if (!video.hidden) { return; }
    video.hidden = false;
    video.currentTime = 0;
    startPlayback();
  }

  function startPlayback() {
    var playback = video.play();
    if (playback && typeof playback.catch === "function") {
      playback.catch(function (error) {
        if (!fallbackUsed && fallbackSrc &&
            (error.name === "NotSupportedError" || (video.error && video.error.code === 4))) {
          fallbackUsed = true;
          video.src = fallbackSrc;
          video.load();
          startPlayback();
        } else if (!document.hidden) {
          console.error("Could not play Pirate overlay video:", error);
          hideOverlay();
        }
      });
    }
  }

  function hideOverlay() {
    if (video.hidden) { return; }
    video.pause();
    video.currentTime = 0;
    video.hidden = true;
  }

  button.addEventListener("click", function () {
    if (Math.random() >= 1 / 100000) { return; }
    playOverlay();
  });

  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape" && !video.hidden) {
      event.preventDefault();
      hideOverlay();
      return;
    }
    var target = event.target;
    var editing = target && (target.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName));
    if (event.key !== "\\" || event.altKey || event.ctrlKey || event.metaKey || event.shiftKey ||
        editing || !video.hidden) { return; }
    event.preventDefault();
    playOverlay();
  });

  video.addEventListener("ended", hideOverlay);
  document.addEventListener("visibilitychange", function () {
    if (!document.hidden && !video.hidden && video.paused) { startPlayback(); }
  });
})();
