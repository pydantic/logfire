/*
 * Logfire docs data-region selector.
 *
 * Renders a US / EU segmented toggle at the top of the "On this page"
 * (secondary) sidebar and rewrites the region host in every fenced code
 * block to the region the reader picked. The choice is persisted in
 * localStorage so it sticks across pages and visits.
 *
 * Only fenced code blocks (`.highlight`) are templated. Prose, inline code,
 * comparison tables (e.g. the data-regions reference) and hand-written
 * "# or EU: ..." comment hints are deliberately left untouched.
 */
(function () {
  'use strict';

  var STORAGE_KEY = 'logfire-data-region';
  var DEFAULT_REGION = 'us';
  var REGIONS = ['us', 'eu'];
  var REGION_LABELS = { us: 'US', eu: 'EU' };
  var HOST_RE = /logfire-(?:us|eu)\.pydantic\.dev/g;
  // Lines that are comments describe the *other* region as an alternative;
  // leave them alone so the hint stays readable.
  var COMMENT_PREFIXES = ['#', '//', '--', ';', '/*', '*', '<!--'];

  function getRegion() {
    try {
      var stored = window.localStorage.getItem(STORAGE_KEY);
      if (stored && REGIONS.indexOf(stored) !== -1) return stored;
    } catch (e) {
      /* localStorage unavailable (private mode / disabled) */
    }
    return DEFAULT_REGION;
  }

  function setRegion(region) {
    try {
      window.localStorage.setItem(STORAGE_KEY, region);
    } catch (e) {
      /* ignore persistence failures */
    }
  }

  function hostFor(region) {
    return 'logfire-' + region + '.pydantic.dev';
  }

  function isCommentNode(value) {
    var trimmed = value.replace(/^\s+/, '');
    for (var i = 0; i < COMMENT_PREFIXES.length; i++) {
      if (trimmed.indexOf(COMMENT_PREFIXES[i]) === 0) return true;
    }
    return false;
  }

  // Walk the text nodes of every fenced code block and rewrite the region host.
  function applyRegion(region) {
    var host = hostFor(region);
    var blocks = document.querySelectorAll('.md-content .highlight');
    for (var b = 0; b < blocks.length; b++) {
      var walker = document.createTreeWalker(
        blocks[b],
        NodeFilter.SHOW_TEXT,
        null,
        false
      );
      var node;
      while ((node = walker.nextNode())) {
        var value = node.nodeValue;
        if (value.indexOf('logfire-') === -1) continue;
        if (isCommentNode(value)) continue;
        // `String.replace` with a global regex always scans from the start
        // and resets lastIndex, so it is safe to reuse HOST_RE here.
        var replaced = value.replace(HOST_RE, host);
        if (replaced !== value) node.nodeValue = replaced;
      }
    }
  }

  function buildWidget(region) {
    var wrapper = document.createElement('div');
    wrapper.className = 'lf-region-selector';
    wrapper.setAttribute('role', 'group');
    wrapper.setAttribute('aria-label', 'Logfire data region');

    var label = document.createElement('span');
    label.className = 'lf-region-selector__label';
    label.textContent = 'Data region';
    wrapper.appendChild(label);

    var group = document.createElement('div');
    group.className = 'lf-region-selector__group';

    REGIONS.forEach(function (r) {
      var button = document.createElement('button');
      button.type = 'button';
      button.className = 'lf-region-selector__option';
      button.textContent = REGION_LABELS[r];
      button.dataset.region = r;
      button.setAttribute('aria-pressed', String(r === region));
      button.addEventListener('click', function () {
        selectRegion(r);
      });
      group.appendChild(button);
    });

    wrapper.appendChild(group);

    var hint = document.createElement('span');
    hint.className = 'lf-region-selector__hint';
    hint.textContent = 'applied to code examples';
    wrapper.appendChild(hint);

    return wrapper;
  }

  function syncWidgets(region) {
    var options = document.querySelectorAll('.lf-region-selector__option');
    for (var i = 0; i < options.length; i++) {
      options[i].setAttribute(
        'aria-pressed',
        String(options[i].dataset.region === region)
      );
    }
  }

  function selectRegion(region) {
    if (REGIONS.indexOf(region) === -1) return;
    setRegion(region);
    syncWidgets(region);
    applyRegion(region);
  }

  function insertWidget(region) {
    if (document.querySelector('.lf-region-selector')) return;
    var widget = buildWidget(region);

    // Preferred home: top of the "On this page" (secondary) sidebar.
    var secondaryNav = document.querySelector(
      '.md-sidebar--secondary .md-nav--secondary'
    );
    if (secondaryNav) {
      secondaryNav.insertBefore(widget, secondaryNav.firstChild);
      return;
    }

    // Fallback: top of the article, just under the page title.
    var content = document.querySelector('.md-content__inner');
    if (content) {
      var heading = content.querySelector('h1');
      if (heading && heading.nextSibling) {
        content.insertBefore(widget, heading.nextSibling);
      } else {
        content.insertBefore(widget, content.firstChild);
      }
    }
  }

  function render() {
    var region = getRegion();
    insertWidget(region);
    applyRegion(region);
  }

  // Material's instant navigation swaps page content without a full reload.
  // `document$` emits on every (re)load, so re-render each time. Fall back to
  // a plain DOMContentLoaded listener if the observable is unavailable.
  if (typeof document$ !== 'undefined' && document$.subscribe) {
    document$.subscribe(render);
  } else if (document.readyState !== 'loading') {
    render();
  } else {
    document.addEventListener('DOMContentLoaded', render);
  }
})();
