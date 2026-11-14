// Prank pop-up ads, shown only on a browser's first visit. Every ad is made up and closable;
// none of them link anywhere, download anything or collect anything.
(function () {
  var ADS = [
    { title: "HOT SINGLE CONTAINERS IN YOUR PORT", body: "3 lonely 40ft containers are waiting near SGSIN right now.", cta: "Meet them" },
    { title: "Congratulations!!!", body: "You are the 1,000,000th visitor to this risk assessor. Claim your free cargo ship!", cta: "Claim prize" },
    { title: "Doctors HATE this one weird trick", body: "Local captain avoids port congestion with this simple method.", cta: "Learn the trick" },
    { title: "Make $5,000 a week shipping from home", body: "No experience needed. No ship needed. No sense needed.", cta: "Start now" },
    { title: "Singles who love supply chains", body: "Find someone who will never leave you on delivered.", cta: "Find love" }
  ];
  var LAST = { title: "Just kidding!", body: "That was the last ad, ever. Enjoy the app.", cta: "Close" };
  var FIRST_DELAY_MS = 3000;
  var INTERVAL_MS = 4000;

  try {
    if (localStorage.getItem("ads-seen")) { return; }
    localStorage.setItem("ads-seen", "1");
  } catch (e) { return; }                           // storage blocked: skip, so it can't repeat on every page

  var queue = ADS.concat([LAST]);
  var open = [];
  var reduceMotion = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) { node.className = className; }
    if (text) { node.textContent = text; }
    return node;
  }

  function remove(box) {
    var index = open.indexOf(box);
    if (index !== -1) { open.splice(index, 1); }
    box.remove();
  }

  function closeAll() {
    open.slice().forEach(remove);
    queue = [];
  }

  function show(ad, isLast) {
    var box = el("aside", "ad" + (reduceMotion ? "" : " ad-wiggle"));
    box.setAttribute("aria-label", "Advertisement");
    var bar = el("div", "ad-bar");
    bar.appendChild(el("span", "ad-label", "Ad"));
    var close = el("button", "ad-close", "×");
    close.type = "button";
    close.setAttribute("aria-label", "Close ad");
    close.addEventListener("click", function () { remove(box); });
    bar.appendChild(close);
    box.appendChild(bar);
    box.appendChild(el("h2", "ad-title", ad.title));
    box.appendChild(el("p", "", ad.body));
    var cta = el("button", "ad-cta", ad.cta);
    cta.type = "button";
    cta.addEventListener("click", function () {
      if (isLast) { remove(box); return; }
      cta.textContent = "Nice try. This is a prank.";
      cta.disabled = true;
    });
    box.appendChild(cta);
    if (!isLast) {
      var skip = el("button", "ad-skip", "Close all ads");
      skip.type = "button";
      skip.addEventListener("click", closeAll);
      box.appendChild(skip);
    }
    // A random spot that keeps the whole ad on screen.
    var width = Math.min(288, window.innerWidth - 32);
    box.style.width = width + "px";
    box.style.left = Math.round(16 + Math.random() * Math.max(0, window.innerWidth - width - 32)) + "px";
    box.style.top = Math.round(16 + Math.random() * Math.max(0, window.innerHeight - 260)) + "px";
    document.body.appendChild(box);
    open.push(box);
  }

  function next() {
    if (!queue.length) { return; }
    if (document.querySelector("dialog[open]")) {     // wait while a paywall prank is open
      setTimeout(next, 1000);
      return;
    }
    var ad = queue.shift();
    show(ad, ad === LAST);
    if (queue.length) { setTimeout(next, INTERVAL_MS); }
  }

  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape" && open.length && !document.querySelector("dialog[open]")) {
      remove(open[open.length - 1]);
    }
  });

  setTimeout(next, FIRST_DELAY_MS);
})();
