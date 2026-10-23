/* Modernization Tracker: small progressive enhancements. Every page still works without this file. */
(function () {
  'use strict';

  var root = document.documentElement;
  var csrf = (document.querySelector('meta[name="csrf-token"]') || {}).content;

  function store(key, value) {
    try {
      if (value === undefined) return localStorage.getItem(key);
      if (value === null) localStorage.removeItem(key); else localStorage.setItem(key, value);
    } catch (e) { return null; }
  }

  function typing(el) {
    return el && (el.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName));
  }

  /* ------------------------------------------------------------ theme */

  function effectiveTheme() {
    var set = root.getAttribute('data-theme');
    if (set) return set;
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  }
  function paintThemeButtons() {
    var dark = effectiveTheme() === 'dark';
    document.querySelectorAll('[data-theme-toggle] .ms').forEach(function (icon) {
      icon.textContent = dark ? 'light_mode' : 'dark_mode';
    });
  }
  document.querySelectorAll('[data-theme-toggle]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var next = effectiveTheme() === 'dark' ? 'light' : 'dark';
      root.setAttribute('data-theme', next);
      store('tracker-theme', next);
      paintThemeButtons();
    });
  });
  paintThemeButtons();

  /* ------------------------------------------------------------ drawer & top bar */

  document.querySelectorAll('[data-drawer-toggle]').forEach(function (btn) {
    btn.addEventListener('click', function () { document.body.classList.toggle('drawer-open'); });
  });

  var topbar = document.querySelector('.topbar');
  if (topbar) {
    var onScroll = function () { topbar.classList.toggle('scrolled', window.scrollY > 4); };
    window.addEventListener('scroll', onScroll, { passive: true });
    onScroll();
  }

  /* ------------------------------------------------------------ snackbars */

  var snackHost = document.querySelector('.snackbars');
  function dismiss(el) {
    el.classList.add('hide');
    setTimeout(function () { el.remove(); }, 260);
  }
  function arm(el) {
    var close = el.querySelector('[data-dismiss]');
    if (close) close.addEventListener('click', function () { dismiss(el); });
    setTimeout(function () { if (el.isConnected) dismiss(el); }, el.classList.contains('error') ? 8000 : 4500);
  }
  document.querySelectorAll('.snackbar').forEach(arm);

  function snack(text, isError) {
    if (!snackHost) return;
    var el = document.createElement('div');
    el.className = 'snackbar' + (isError ? ' error' : '');
    el.setAttribute('role', 'status');
    el.innerHTML = '<span class="ms"></span><span class="text"></span>' +
      '<button type="button" class="icon-btn sm" data-dismiss aria-label="Dismiss"><span class="ms">close</span></button>';
    el.querySelector('.ms').textContent = isError ? 'warning' : 'check_circle';
    el.querySelector('.text').textContent = text;
    snackHost.appendChild(el);
    arm(el);
  }

  /* ------------------------------------------------------------ keyboard shortcuts */

  var dialog = document.getElementById('shortcuts');
  document.querySelectorAll('[data-shortcuts]').forEach(function (btn) {
    btn.addEventListener('click', function () { if (dialog) dialog.showModal(); });
  });

  var goPending = false;
  var goTimer;
  var goRoutes = { b: 'board', l: 'backlog', m: 'my_work', i: 'insights', u: 'users' };

  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') document.body.classList.remove('drawer-open');
    if (e.ctrlKey || e.metaKey || e.altKey || typing(e.target)) return;

    if (goPending) {
      goPending = false;
      var link = goRoutes[e.key] && document.querySelector('[data-route="' + goRoutes[e.key] + '"]');
      if (link) { e.preventDefault(); window.location = link.href; }
      return;
    }
    var target;
    switch (e.key) {
      case '/':
        target = document.querySelector('[data-search]');
        if (target) { e.preventDefault(); target.focus(); target.select(); }
        break;
      case 'n':
      case 'c':
        target = document.querySelector('[data-route="ticket_create"]');
        if (target) { e.preventDefault(); window.location = target.href; }
        break;
      case 'e':
        target = document.querySelector('[data-shortcut="edit"]');
        if (target) { e.preventDefault(); window.location = target.href; }
        break;
      case 'a':
        target = document.querySelector('[data-shortcut="assign"]');
        if (target) { e.preventDefault(); target.requestSubmit ? target.requestSubmit() : target.submit(); }
        break;
      case 'g':
        goPending = true;
        clearTimeout(goTimer);
        goTimer = setTimeout(function () { goPending = false; }, 1200);
        break;
      case '?':
        if (dialog) { e.preventDefault(); dialog.showModal(); }
        break;
    }
  });

  /* Ctrl/Cmd + Enter submits the form a textarea belongs to. */
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey) && e.target.tagName === 'TEXTAREA' && e.target.form) {
      e.preventDefault();
      e.target.form.requestSubmit ? e.target.form.requestSubmit() : e.target.form.submit();
    }
  });

  /* ------------------------------------------------------------ small helpers */

  document.querySelectorAll('[data-autosubmit]').forEach(function (el) {
    el.addEventListener('change', function () { el.form.submit(); });
  });

  document.querySelectorAll('form[data-confirm]').forEach(function (form) {
    form.addEventListener('submit', function (e) {
      if (!window.confirm(form.getAttribute('data-confirm'))) e.preventDefault();
    });
  });

  document.querySelectorAll('[data-copy]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var text = btn.getAttribute('data-copy');
      var done = function () { snack('Copied ' + text); };
      if (navigator.clipboard && window.isSecureContext) navigator.clipboard.writeText(text).then(done);
      else {
        var area = document.createElement('textarea');
        area.value = text;
        document.body.appendChild(area);
        area.select();
        try { document.execCommand('copy'); done(); } catch (err) { snack('Copy failed', true); }
        area.remove();
      }
    });
  });

  /* ------------------------------------------------------------ board drag and drop */

  var board = document.querySelector('[data-board]');
  if (board) {
    var dragged = null;

    function refreshCounts() {
      board.querySelectorAll('[data-status]').forEach(function (col) {
        var badge = col.querySelector('[data-count]');
        var cards = col.querySelectorAll('.ticket').length;
        var hidden = parseInt(col.getAttribute('data-hidden') || '0', 10);
        if (badge) badge.textContent = cards + hidden;
        var empty = col.querySelector('.empty');
        if (empty) empty.hidden = cards > 0;
      });
    }

    function move(card, column) {
      var from = card.parentElement;
      var next = card.nextElementSibling;
      var status = column.getAttribute('data-status');
      if (card.getAttribute('data-current') === status) return;
      column.querySelector('.column-list').prepend(card);
      card.classList.add('saving');
      refreshCounts();

      var body = new FormData();
      body.append('status', status);
      fetch(card.getAttribute('data-move-url'), {
        method: 'POST',
        body: body,
        headers: { 'X-CSRFToken': csrf, 'X-Requested-With': 'fetch' },
        credentials: 'same-origin'
      }).then(function (r) {
        if (!r.ok) throw new Error(r.status);
        return r.json();
      }).then(function (data) {
        card.setAttribute('data-current', data.status);
        var select = card.querySelector('select[name="status"]');
        if (select) select.value = data.status;
        snack(data.ticket + ' moved to ' + data.label);
      }).catch(function () {
        from.insertBefore(card, next);
        refreshCounts();
        snack('Could not move the ticket. Please try again.', true);
      }).finally(function () {
        card.classList.remove('saving');
      });
    }

    board.addEventListener('dragstart', function (e) {
      var card = e.target.closest && e.target.closest('.ticket');
      if (!card) return;
      dragged = card;
      card.classList.add('dragging');
      e.dataTransfer.effectAllowed = 'move';
      e.dataTransfer.setData('text/plain', card.getAttribute('data-number'));
    });
    board.addEventListener('dragend', function () {
      if (dragged) dragged.classList.remove('dragging');
      dragged = null;
      board.querySelectorAll('.drag-over').forEach(function (c) { c.classList.remove('drag-over'); });
    });
    board.querySelectorAll('[data-status]').forEach(function (column) {
      column.addEventListener('dragover', function (e) {
        if (!dragged) return;
        e.preventDefault();
        e.dataTransfer.dropEffect = 'move';
        column.classList.add('drag-over');
      });
      column.addEventListener('dragleave', function (e) {
        if (!column.contains(e.relatedTarget)) column.classList.remove('drag-over');
      });
      column.addEventListener('drop', function (e) {
        e.preventDefault();
        column.classList.remove('drag-over');
        if (dragged) move(dragged, column);
      });
    });

    /* The per card status menu also moves without a page reload. */
    board.querySelectorAll('.ticket select[name="status"]').forEach(function (select) {
      select.addEventListener('change', function (e) {
        e.stopPropagation();
        var card = select.closest('.ticket');
        var column = board.querySelector('[data-status="' + select.value + '"]');
        if (column) move(card, column);
      });
    });
  }

  /* ------------------------------------------------------------ backlog bulk selection */

  var bulk = document.querySelector('[data-bulk]');
  if (bulk) {
    var bar = bulk.querySelector('.bulk-bar');
    var all = bulk.querySelector('[data-select-all]');
    var boxes = Array.prototype.slice.call(bulk.querySelectorAll('input[name="tickets"]'));
    var counter = bulk.querySelector('[data-selected-count]');
    var lastIndex = null;

    function sync() {
      var picked = boxes.filter(function (b) { return b.checked; }).length;
      bar.classList.toggle('show', picked > 0);
      counter.textContent = picked + ' selected';
      if (all) {
        all.checked = picked > 0 && picked === boxes.length;
        all.indeterminate = picked > 0 && picked < boxes.length;
      }
      boxes.forEach(function (b) { b.closest('tr').classList.toggle('selected', b.checked); });
    }
    if (all) all.addEventListener('change', function () {
      boxes.forEach(function (b) { b.checked = all.checked; });
      sync();
    });
    boxes.forEach(function (box, index) {
      box.addEventListener('click', function (e) {
        /* Shift click selects a range. */
        if (e.shiftKey && lastIndex !== null) {
          var lo = Math.min(lastIndex, index), hi = Math.max(lastIndex, index);
          for (var i = lo; i <= hi; i++) boxes[i].checked = box.checked;
        }
        lastIndex = index;
        sync();
      });
    });
    var clear = bulk.querySelector('[data-clear-selection]');
    if (clear) clear.addEventListener('click', function () {
      boxes.forEach(function (b) { b.checked = false; });
      sync();
    });
    sync();
  }
})();
