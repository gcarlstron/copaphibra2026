/* UI helpers — Copa Phibra
 *
 * Painéis recolhíveis (opt-in): qualquer `.round-card--collapsible` ganha um
 * chevron, cabeçalho clicável (com teclado e ARIA) e persiste o estado
 * recolhido/aberto em localStorage por `data-panel-id`. Sem JS, o painel
 * permanece aberto (comportamento padrão) — degradação graciosa.
 */
(function () {
  "use strict";

  var STORAGE_PREFIX = "copaphibra:panel:";

  function storageGet(key) {
    try {
      return window.localStorage.getItem(key);
    } catch (e) {
      return null;
    }
  }

  function storageSet(key, value) {
    try {
      window.localStorage.setItem(key, value);
    } catch (e) {
      /* private mode / quota — ignora, só não persiste */
    }
  }

  function panelId(card) {
    var explicit = card.getAttribute("data-panel-id");
    if (explicit) return explicit;
    var h3 = card.querySelector(".round-head h3");
    return h3 ? h3.textContent.trim() : "";
  }

  function setup(card) {
    var head = card.querySelector(".round-head");
    if (!head || head.dataset.collapsibleReady === "1") return;
    head.dataset.collapsibleReady = "1";

    var storageKey = STORAGE_PREFIX + panelId(card);

    var chevron = document.createElement("span");
    chevron.className = "round-card__chevron";
    chevron.setAttribute("aria-hidden", "true");
    chevron.textContent = "▾"; /* ▾ */
    head.appendChild(chevron);

    head.setAttribute("role", "button");
    head.setAttribute("tabindex", "0");

    function syncAria() {
      head.setAttribute(
        "aria-expanded",
        card.classList.contains("is-collapsed") ? "false" : "true"
      );
    }

    if (storageGet(storageKey) === "collapsed") {
      card.classList.add("is-collapsed");
    }
    syncAria();

    function toggle() {
      card.classList.toggle("is-collapsed");
      var collapsed = card.classList.contains("is-collapsed");
      storageSet(storageKey, collapsed ? "collapsed" : "open");
      syncAria();
    }

    head.addEventListener("click", function (e) {
      /* não togglar ao clicar em elementos interativos dentro do cabeçalho */
      if (e.target.closest("a, button, input, select, textarea, label, form")) return;
      toggle();
    });

    head.addEventListener("keydown", function (e) {
      if (e.key === "Enter" || e.key === " " || e.key === "Spacebar") {
        e.preventDefault();
        toggle();
      }
    });
  }

  function init() {
    var cards = document.querySelectorAll(".round-card--collapsible");
    for (var i = 0; i < cards.length; i++) setup(cards[i]);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
