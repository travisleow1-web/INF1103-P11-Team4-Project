// Cargo crate: a horizontal reel of items that spins and stops on a random prize.
// Purely for fun on the client; it never talks to the server.
(function () {
  var RARITIES = [
    { name: "Common",    css: "common",    weight: 7990, items: ["Foreskin", "Scrotum", "Just da tip", "4D number"] },
    { name: "Uncommon",  css: "uncommon",  weight: 1600, items: ["XxDRAGONLORDSKINxX", "Bodyache everywhere", "Fake Legendary"] },
    { name: "Rare",      css: "rare",      weight: 320,  items: ["$3 Ang Bao", "WHY U REDEEM"] },
    { name: "Epic",      css: "epic",      weight: 64,   items: ["Gege Fking Easyyyy"] },
    { name: "Legendary", css: "legendary", weight: 26,   items: ["Who's in paris?"] }
  ];
  var REEL_LENGTH = 60;     // items on the strip
  var WIN_INDEX = 52;       // the strip stops with this item under the marker
  var SPIN_MS = 6000;

  var strip = document.getElementById("crate-strip");
  var button = document.getElementById("crate-open");
  var result = document.getElementById("crate-result");
  if (!strip || !button || !result) { return; }
  var reel = strip.parentElement;
  var reduceMotion = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  // Sound: generated with the Web Audio API, so there are no audio files to load.
  // The context is created on the first click because browsers block audio until the user interacts.
  var soundButton = document.getElementById("crate-sound");
  var audio = null;
  var soundOn = true;
  try { soundOn = localStorage.getItem("crate-sound") !== "off"; } catch (e) { /* storage blocked */ }

  function showSound() {
    if (!soundButton) { return; }
    soundButton.textContent = soundOn ? "Sound: on" : "Sound: off";
    soundButton.setAttribute("aria-pressed", soundOn ? "true" : "false");
  }

  function getAudio() {
    if (!soundOn) { return null; }
    var Context = window.AudioContext || window.webkitAudioContext;
    if (!Context) { return null; }
    if (!audio) { audio = new Context(); }
    if (audio.state === "suspended") { audio.resume(); }
    return audio;
  }

  // One short note: wave type, start and end pitch (Hz), length (s), volume, delay from now (s).
  function tone(type, from, to, length, volume, delay) {
    var ctx = getAudio();
    if (!ctx) { return; }
    var start = ctx.currentTime + (delay || 0);
    var osc = ctx.createOscillator();
    var gain = ctx.createGain();
    osc.type = type;
    osc.frequency.setValueAtTime(from, start);
    osc.frequency.exponentialRampToValueAtTime(to, start + length);
    gain.gain.setValueAtTime(volume, start);
    gain.gain.exponentialRampToValueAtTime(0.0001, start + length);
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.start(start);
    osc.stop(start + length + 0.02);
  }

  // The click as each item passes the marker.
  function playTick() {
    tone("triangle", 2400 + Math.random() * 300, 900, 0.035, 0.12);
  }

  // The reveal tune for each tier (note pitches in Hz). Rarer drops get a longer, brighter tune.
  var FANFARES = {
    common:    [523, 659],
    uncommon:  [523, 659, 784],
    rare:      [523, 659, 784, 1047],
    epic:      [440, 554, 659, 880, 1109],
    legendary: [392, 494, 587, 784, 988, 1175, 1568]
  };

  function playReveal(rarity) {
    var notes = FANFARES[rarity.css] || FANFARES.common;
    notes.forEach(function (freq, i) {
      tone("square", freq, freq, 0.22, 0.06, i * 0.09);
      tone("sine", freq * 2, freq * 2, 0.3, 0.04, i * 0.09);
    });
    if (rarity.css === "epic" || rarity.css === "legendary") {
      var end = notes.length * 0.09;
      for (var i = 0; i < 8; i++) {                    // a sparkle on top of the big drops
        tone("sine", 2000 + Math.random() * 2000, 1500, 0.15, 0.03, end + i * 0.05);
      }
    }
  }

  if (soundButton) {
    showSound();
    soundButton.addEventListener("click", function () {
      soundOn = !soundOn;
      try { localStorage.setItem("crate-sound", soundOn ? "on" : "off"); } catch (e) { /* storage blocked */ }
      showSound();
    });
  }

  // While the strip moves, tick each time a new item passes under the marker.
  function tickWhileSpinning(until) {
    var items = strip.children;
    var step = items[1].offsetLeft - items[0].offsetLeft;
    var first = items[0].offsetLeft;
    var last = -1;
    function frame() {
      var transform = getComputedStyle(strip).transform;
      if (transform && transform !== "none") {
        var moved = -new DOMMatrixReadOnly(transform).m41;
        var under = Math.floor((moved + reel.clientWidth / 2 - first) / step);
        if (under !== last) {
          if (last !== -1) { playTick(); }
          last = under;
        }
      }
      if (performance.now() < until) { requestAnimationFrame(frame); }
    }
    requestAnimationFrame(frame);
  }

  function roll() {
    var total = RARITIES.reduce(function (sum, r) { return sum + r.weight; }, 0);
    var pick = Math.random() * total;
    for (var i = 0; i < RARITIES.length; i++) {
      pick -= RARITIES[i].weight;
      if (pick < 0) { break; }
    }
    var rarity = RARITIES[Math.min(i, RARITIES.length - 1)];
    return { rarity: rarity, name: rarity.items[Math.floor(Math.random() * rarity.items.length)] };
  }

  function makeItem(prize) {
    var li = document.createElement("li");
    li.className = "crate-item crate-" + prize.rarity.css;
    var name = document.createElement("span");
    name.className = "crate-name";
    name.textContent = prize.name;
    var tier = document.createElement("span");
    tier.className = "crate-tier";
    tier.textContent = prize.rarity.name;
    li.appendChild(name);
    li.appendChild(tier);
    return li;
  }

  function fill(winner) {
    strip.textContent = "";
    for (var i = 0; i < REEL_LENGTH; i++) {
      strip.appendChild(makeItem(i === WIN_INDEX ? winner : roll()));
    }
  }

  function reset() {
    strip.style.transition = "none";
    strip.style.transform = "translateX(0)";
    void strip.offsetWidth;                     // apply the reset before the next transition starts
  }

  function finish(winner) {
    var items = strip.children;
    items[WIN_INDEX].classList.add("crate-won");
    result.textContent = "You got: " + winner.name + " (" + winner.rarity.name + ")";
    playReveal(winner.rarity);
    button.disabled = false;
    button.textContent = "Open another";
  }

  button.addEventListener("click", function () {
    var winner = roll();
    getAudio();                                         // unlock audio inside the click
    button.disabled = true;
    result.textContent = "Opening...";
    reset();
    fill(winner);

    var item = strip.children[WIN_INDEX];
    var width = item.offsetWidth;
    var jitter = (Math.random() - 0.5) * width * 0.8;   // land somewhere inside the item, not always dead centre
    var target = item.offsetLeft + width / 2 - reel.clientWidth / 2 + jitter;

    if (reduceMotion) {
      strip.style.transform = "translateX(" + (-target) + "px)";
      finish(winner);
      return;
    }
    strip.style.transition = "transform " + SPIN_MS + "ms cubic-bezier(0.12, 0.8, 0.2, 1)";
    strip.style.transform = "translateX(" + (-target) + "px)";
    tickWhileSpinning(performance.now() + SPIN_MS);
    setTimeout(function () { finish(winner); }, SPIN_MS + 50);
  });

  fill(roll());
})();
