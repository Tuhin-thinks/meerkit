(function () {
  const disclaimerText =
    "This project was built out of curiosity for educational and research purposes only. It is strictly not for commercial use and is not affiliated with, endorsed by, or sponsored by Meta or Instagram.";

  function renderDisclaimer() {
    const host = document.querySelector('[data-md-component="announce"]');
    if (!host) {
      return;
    }

    host.innerHTML =
      '<div class="md-banner"><div class="md-banner__inner">' +
      disclaimerText +
      "</div></div>";
  }

  if (typeof window.document$ !== "undefined" && window.document$?.subscribe) {
    window.document$.subscribe(renderDisclaimer);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", renderDisclaimer);
  } else {
    renderDisclaimer();
  }
})();
