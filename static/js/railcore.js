/* ==========================================================================
   RailCore ERP - interface behaviour

   Vanilla JavaScript, no dependencies. Everything here is progressive
   enhancement: with scripting disabled the sidebar stays open, the filter
   selects still submit through their form's submit button, and the messages
   remain on screen until the next page load.
   ========================================================================== */

(function () {
  "use strict";

  var COLLAPSED_KEY = "railcore.sidebar.collapsed";
  var MOBILE_BREAKPOINT = 992;
  var ALERT_TIMEOUT = 6000;

  function ready(fn) {
    if (document.readyState !== "loading") {
      fn();
    } else {
      document.addEventListener("DOMContentLoaded", fn);
    }
  }

  function isMobile() {
    return window.innerWidth < MOBILE_BREAKPOINT;
  }

  /* ------------------------------------------------------------------------
     Sidebar

     Desktop: the toggle collapses the sidebar to an icon rail and the choice
     is remembered in localStorage.
     Mobile: the same toggle opens an off-canvas drawer, closed by the overlay,
     the close button or the Escape key.
     ------------------------------------------------------------------------ */
  function initSidebar() {
    var body = document.body;
    var toggle = document.querySelector("[data-rc-sidebar-toggle]");
    var closeButton = document.querySelector("[data-rc-sidebar-close]");
    var overlay = document.querySelector("[data-rc-overlay]");

    if (!toggle) {
      return;
    }

    function setExpandedState() {
      var expanded = isMobile()
        ? body.classList.contains("rc-sidebar-open")
        : !body.classList.contains("rc-sidebar-collapsed");
      toggle.setAttribute("aria-expanded", expanded ? "true" : "false");
    }

    function closeDrawer() {
      body.classList.remove("rc-sidebar-open");
      setExpandedState();
    }

    // Restore the remembered desktop preference.
    try {
      if (window.localStorage.getItem(COLLAPSED_KEY) === "1" && !isMobile()) {
        body.classList.add("rc-sidebar-collapsed");
      }
    } catch (error) {
      /* Private browsing mode: fall back to the expanded default. */
    }

    setExpandedState();

    toggle.addEventListener("click", function () {
      if (isMobile()) {
        body.classList.toggle("rc-sidebar-open");
      } else {
        var collapsed = body.classList.toggle("rc-sidebar-collapsed");
        try {
          window.localStorage.setItem(COLLAPSED_KEY, collapsed ? "1" : "0");
        } catch (error) {
          /* Preference simply is not remembered. */
        }
      }
      setExpandedState();
    });

    if (closeButton) {
      closeButton.addEventListener("click", closeDrawer);
    }

    if (overlay) {
      overlay.addEventListener("click", closeDrawer);
    }

    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape" && body.classList.contains("rc-sidebar-open")) {
        closeDrawer();
        toggle.focus();
      }
    });

    // Leaving mobile width must not strand the page in the drawer state.
    window.addEventListener("resize", function () {
      if (!isMobile()) {
        body.classList.remove("rc-sidebar-open");
      }
      setExpandedState();
    });
  }

  /* ------------------------------------------------------------------------
     Dropdown menus (the header notification panel)
     ------------------------------------------------------------------------ */
  function initDropdowns() {
    var triggers = document.querySelectorAll("[data-rc-dropdown]");
    if (!triggers.length) {
      return;
    }

    var pairs = [];

    Array.prototype.forEach.call(triggers, function (trigger) {
      var menu = document.getElementById(trigger.getAttribute("data-rc-dropdown"));
      if (!menu) {
        return;
      }

      pairs.push({ trigger: trigger, menu: menu });

      trigger.setAttribute("aria-expanded", "false");

      trigger.addEventListener("click", function (event) {
        event.stopPropagation();
        var willOpen = !menu.classList.contains("is-open");

        // Only one menu open at a time.
        pairs.forEach(function (pair) {
          pair.menu.classList.remove("is-open");
          pair.trigger.setAttribute("aria-expanded", "false");
        });

        if (willOpen) {
          menu.classList.add("is-open");
          trigger.setAttribute("aria-expanded", "true");
        }
      });

      menu.addEventListener("click", function (event) {
        event.stopPropagation();
      });
    });

    function closeAll() {
      pairs.forEach(function (pair) {
        pair.menu.classList.remove("is-open");
        pair.trigger.setAttribute("aria-expanded", "false");
      });
    }

    document.addEventListener("click", closeAll);

    document.addEventListener("keydown", function (event) {
      if (event.key !== "Escape") {
        return;
      }
      pairs.forEach(function (pair) {
        if (pair.menu.classList.contains("is-open")) {
          pair.menu.classList.remove("is-open");
          pair.trigger.setAttribute("aria-expanded", "false");
          pair.trigger.focus();
        }
      });
    });
  }

  /* ------------------------------------------------------------------------
     Message alerts: manual dismiss plus an automatic timeout
     ------------------------------------------------------------------------ */
  function dismissAlert(alert) {
    if (!alert || alert.dataset.rcDismissed === "1") {
      return;
    }
    alert.dataset.rcDismissed = "1";
    alert.classList.add("is-leaving");
    window.setTimeout(function () {
      if (alert.parentNode) {
        alert.parentNode.removeChild(alert);
      }
    }, 200);
  }

  function initAlerts() {
    var alerts = document.querySelectorAll("[data-rc-alert]");

    Array.prototype.forEach.call(alerts, function (alert) {
      var closeButton = alert.querySelector("[data-rc-alert-close]");
      if (closeButton) {
        closeButton.addEventListener("click", function () {
          dismissAlert(alert);
        });
      }

      // Errors stay put: the user needs time to read what went wrong.
      if (!alert.classList.contains("rc-alert--danger")) {
        window.setTimeout(function () {
          dismissAlert(alert);
        }, ALERT_TIMEOUT);
      }
    });
  }

  /* ------------------------------------------------------------------------
     List toolbars

     A change to any filter select submits its form, and a debounced keystroke
     in the search box does the same. The page= parameter is dropped so a new
     filter always lands on page one.
     ------------------------------------------------------------------------ */
  function clearPageParam(form) {
    var pageInput = form.querySelector('input[name="page"]');
    if (pageInput) {
      pageInput.value = "";
      pageInput.disabled = true;
    }
  }

  function initFilters() {
    var selects = document.querySelectorAll("[data-rc-autosubmit]");

    Array.prototype.forEach.call(selects, function (control) {
      control.addEventListener("change", function () {
        var form = control.form;
        if (form) {
          clearPageParam(form);
          form.submit();
        }
      });
    });

    var searchInputs = document.querySelectorAll("[data-rc-search]");

    Array.prototype.forEach.call(searchInputs, function (input) {
      var timer = null;

      input.addEventListener("input", function () {
        window.clearTimeout(timer);
        timer = window.setTimeout(function () {
          var form = input.form;
          if (form) {
            clearPageParam(form);
            form.submit();
          }
        }, 450);
      });

      // Enter submits at once rather than waiting for the debounce.
      input.addEventListener("keydown", function (event) {
        if (event.key === "Enter") {
          window.clearTimeout(timer);
        }
      });
    });
  }

  /* ------------------------------------------------------------------------
     Clickable table rows

     Rows carry data-rc-href. Clicks inside a link, button or form are ignored
     so the row-level action buttons keep working. Every such row also holds a
     real link in its first cell, so keyboard users are never dependent on this.
     ------------------------------------------------------------------------ */
  function initRowLinks() {
    var rows = document.querySelectorAll("tr[data-rc-href]");

    Array.prototype.forEach.call(rows, function (row) {
      row.addEventListener("click", function (event) {
        if (event.target.closest("a, button, input, label, form, select")) {
          return;
        }
        if (window.getSelection && String(window.getSelection()).length) {
          return; // The user was selecting text, not navigating.
        }
        window.location.href = row.getAttribute("data-rc-href");
      });
    });
  }

  /* ------------------------------------------------------------------------
     Password reveal toggles
     ------------------------------------------------------------------------ */
  function initPasswordToggles() {
    var buttons = document.querySelectorAll("[data-rc-reveal]");

    Array.prototype.forEach.call(buttons, function (button) {
      var input = document.getElementById(button.getAttribute("data-rc-reveal"));
      if (!input) {
        return;
      }

      button.addEventListener("click", function () {
        var showing = input.type === "text";
        input.type = showing ? "password" : "text";
        button.setAttribute("aria-pressed", showing ? "false" : "true");
        button.setAttribute(
          "aria-label",
          showing ? "Show password" : "Hide password"
        );
      });
    });
  }

  /* ------------------------------------------------------------------------
     Chart bar widths

     Percentages arrive from the server in data-rc-percent. Applying them after
     load lets the CSS transition animate the bars into place, and keeps the
     templates free of inline style attributes.
     ------------------------------------------------------------------------ */
  function initBars() {
    var bars = document.querySelectorAll("[data-rc-percent]");

    Array.prototype.forEach.call(bars, function (bar) {
      var percent = parseFloat(bar.getAttribute("data-rc-percent"));
      if (isNaN(percent)) {
        percent = 0;
      }
      percent = Math.max(0, Math.min(100, percent));
      bar.style.setProperty("--rc-bar-percent", percent + "%");
    });
  }

  /* ------------------------------------------------------------------------
     Submit protection

     Stops a double click on Save from posting the same form twice.
     ------------------------------------------------------------------------ */
  function initSubmitGuards() {
    var forms = document.querySelectorAll("[data-rc-guard]");

    Array.prototype.forEach.call(forms, function (form) {
      form.addEventListener("submit", function () {
        var buttons = form.querySelectorAll('button[type="submit"]');
        window.setTimeout(function () {
          Array.prototype.forEach.call(buttons, function (button) {
            button.disabled = true;
          });
        }, 0);
      });
    });
  }

  ready(function () {
    initSidebar();
    initDropdowns();
    initAlerts();
    initFilters();
    initRowLinks();
    initPasswordToggles();
    initBars();
    initSubmitGuards();
  });
})();
