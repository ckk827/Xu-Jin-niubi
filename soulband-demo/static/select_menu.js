/* In-page dropdowns.
 *
 * Qt WebEngine renders native <select> popups as an oversized white box that
 * grows on every open (the same page in Edge/Chrome is fine). So instead of
 * letting the browser draw the list, we suppress the default mouse action and
 * draw the options ourselves. The <select> element itself stays in the DOM with
 * the same id, name and value, so existing handlers, form submission and
 * automated selectOption() calls keep working.
 */
(function () {
  if (window.__soulbandSelectMenu) return;
  window.__soulbandSelectMenu = true;

  var menu = null;
  var active = null;
  var highlighted = -1;

  function mark(open) {
    document.body.dataset.selectMenuOpen = open ? "1" : "";
    if (active) active.setAttribute("aria-expanded", open ? "true" : "false");
  }

  function options(select) {
    return Array.prototype.slice.call(select.options).filter(function (option) {
      return !option.disabled;
    });
  }

  function close(refocus) {
    if (!menu) return;
    var select = active;
    menu.remove();
    menu = null;
    active = null;
    highlighted = -1;
    mark(false);
    if (refocus && select && document.contains(select)) select.focus({ preventScroll: true });
  }

  function place(select) {
    var rect = select.getBoundingClientRect();
    var width = Math.max(Math.ceil(rect.width), 150);
    var left = Math.min(rect.left, window.innerWidth - width - 8);
    menu.style.width = width + "px";
    menu.style.left = Math.max(8, left) + "px";
    if (!menu.isConnected) {
      menu.style.top = "0px";
      menu.style.visibility = "hidden";
      document.body.appendChild(menu);
    }
    var height = menu.offsetHeight;
    var spaceBelow = window.innerHeight - rect.bottom;
    var below = spaceBelow > height + 12 || rect.top < height + 12;
    var top = below ? rect.bottom + 4 : rect.top - height - 4;
    menu.style.top = Math.max(8, Math.min(top, window.innerHeight - height - 8)) + "px";
    menu.style.visibility = "";
  }

  function highlight(index) {
    if (!menu) return;
    var items = menu.querySelectorAll(".select-menu-item");
    if (!items.length) return;
    highlighted = Math.max(0, Math.min(index, items.length - 1));
    Array.prototype.forEach.call(items, function (item, position) {
      item.classList.toggle("is-highlighted", position === highlighted);
    });
    // Scroll the list itself: scrollIntoView() would also scroll the page and
    // fire a scroll event that closes the menu it is trying to show.
    var item = items[highlighted];
    if (item.offsetTop < menu.scrollTop) {
      menu.scrollTop = item.offsetTop - 4;
    } else if (item.offsetTop + item.offsetHeight > menu.scrollTop + menu.clientHeight) {
      menu.scrollTop = item.offsetTop + item.offsetHeight - menu.clientHeight + 4;
    }
  }

  function choose(select, option) {
    if (!option) return;
    if (select.value !== option.value) {
      select.value = option.value;
      select.dispatchEvent(new Event("input", { bubbles: true }));
      select.dispatchEvent(new Event("change", { bubbles: true }));
    }
    close(true);
  }

  function open(select) {
    if (select.disabled || select.multiple) return;
    var items = options(select);
    if (!items.length) return;
    close(false);

    menu = document.createElement("div");
    menu.className = "select-menu";
    menu.id = "select-menu";
    menu.setAttribute("role", "listbox");
    menu.setAttribute("aria-label", select.getAttribute("aria-label") || "选项");
    items.forEach(function (option, index) {
      var item = document.createElement("button");
      item.type = "button";
      item.className = "select-menu-item" + (option.value === select.value ? " is-checked" : "");
      item.setAttribute("role", "option");
      item.setAttribute("aria-selected", option.value === select.value ? "true" : "false");
      item.dataset.index = String(index);
      item.textContent = option.textContent;
      item.addEventListener("mousedown", function (event) { event.preventDefault(); });
      item.addEventListener("click", function (event) {
        event.preventDefault();
        choose(select, option);
      });
      menu.appendChild(item);
    });
    active = select;
    active.setAttribute("aria-haspopup", "listbox");
    active.focus({ preventScroll: true });
    mark(true);
    place(select);
    var current = items.findIndex(function (option) { return option.value === select.value; });
    highlight(current < 0 ? 0 : current);
  }

  function isOpen() {
    return Boolean(menu && active);
  }

  function step(delta) {
    if (!isOpen()) return;
    highlight(highlighted + delta);
  }

  function selectAt(x, y) {
    var list = document.querySelectorAll("select");
    for (var i = 0; i < list.length; i++) {
      var select = list[i];
      if (select.disabled || select.multiple) continue;
      var rect = select.getBoundingClientRect();
      if (rect.width < 1 || rect.height < 1) continue;
      if (x >= rect.left && x <= rect.right && y >= rect.top && y <= rect.bottom) return select;
    }
    return null;
  }

  // A <label> that wraps a select, or points at one with for="", forwards its
  // click to the control, which is another path that opens the native popup.
  function selectFrom(target) {
    if (!target || !target.closest) return null;
    var select = target.closest("select");
    if (select) return select;
    var label = target.closest("label");
    if (!label) return null;
    var inside = label.querySelector("select");
    if (inside) return inside;
    if (label.htmlFor) {
      var labelled = document.getElementById(label.htmlFor);
      if (labelled && labelled.tagName === "SELECT") return labelled;
    }
    return null;
  }

  // The selects must never receive the pointer themselves: Qt WebEngine draws
  // the popup from the widget layer, where a preventDefault() cannot reach it.
  function markSelects() {
    var list = document.querySelectorAll("select:not(.select-menu-ready)");
    for (var i = 0; i < list.length; i++) list[i].classList.add("select-menu-ready");
  }

  document.addEventListener("mousedown", function (event) {
    if (event.button !== 0) return;
    if (event.target.closest && event.target.closest(".select-menu")) return;
    var select = selectAt(event.clientX, event.clientY) || selectFrom(event.target);
    if (!select) {
      if (isOpen()) close(true);
      return;
    }
    if (select.disabled || select.multiple) return;
    // Suppresses Chromium's native popup, which Qt WebEngine sizes wrongly.
    event.preventDefault();
    open(select);
  }, true);

  document.addEventListener("click", function (event) {
    if (event.target.closest && event.target.closest(".select-menu")) return;
    // A label activating its select dispatches this click without a mousedown.
    if (event.target.tagName === "SELECT" || selectAt(event.clientX, event.clientY) || selectFrom(event.target)) {
      event.preventDefault();
    }
  }, true);

  document.addEventListener("keydown", function (event) {
    var select = event.target.closest && event.target.closest("select");
    if (!isOpen()) {
      if (!select || select.disabled || select.multiple) return;
      if (["Enter", " ", "ArrowDown", "ArrowUp", "F4"].indexOf(event.key) < 0) return;
      event.preventDefault();
      open(select);
      return;
    }
    if (event.key === "Escape") {
      event.preventDefault();
      close(true);
    } else if (event.key === "ArrowDown") {
      event.preventDefault();
      step(1);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      step(-1);
    } else if (event.key === "Home") {
      event.preventDefault();
      highlight(0);
    } else if (event.key === "End") {
      event.preventDefault();
      highlight(menu.querySelectorAll(".select-menu-item").length - 1);
    } else if (event.key === "Enter" || event.key === " ") {
      if (!active) return;
      event.preventDefault();
      var items = options(active);
      choose(active, items[highlighted]);
    } else if (event.key === "Tab") {
      close(false);
    }
  }, true);

  document.addEventListener("scroll", function (event) {
    if (!isOpen()) return;
    if (menu.contains(event.target)) return;  // scrolling inside the list keeps it open
    if (!document.contains(active)) { close(false); return; }
    // The page moved: follow the control instead of closing, so a late
    // scroll-into-view from the click itself does not swallow the menu.
    place(active);
  }, true);
  window.addEventListener("resize", function () { if (isOpen()) close(false); });
  window.addEventListener("blur", function () { if (isOpen()) close(false); });

  markSelects();
  if (window.MutationObserver) {
    // The page re-renders with innerHTML, so new selects appear all the time.
    new MutationObserver(function (records) {
      for (var i = 0; i < records.length; i++) {
        if (records[i].addedNodes && records[i].addedNodes.length) {
          markSelects();
          return;
        }
      }
    }).observe(document.body, { childList: true, subtree: true });
  }
})();
