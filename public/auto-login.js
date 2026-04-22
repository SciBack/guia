// GUIA UPeU — scripts de inyección externa
// 1. Colorea "IA" de GUIA en gold en el header del chat
// 2. Auto-redirige al OAuth de UPeU en la página de login
// 3. Reemplaza <img> del panel derecho con SVG inline animable

(function () {
  'use strict';

  // ── 1. Wordmark: "IA" en gold ──────────────────────────────────
  var PROCESSED = 'data-guia-styled';

  function styleGuiaNode(node) {
    if (node.textContent !== 'GUIA') return;
    var parent = node.parentElement;
    if (!parent || parent.hasAttribute(PROCESSED)) return;
    var span = document.createElement('span');
    span.className = 'guia-wordmark';
    span.setAttribute(PROCESSED, '1');
    span.innerHTML = 'GU<span class="guia-ia">IA</span>';
    parent.replaceChild(span, node);
  }

  function walkForGuia(root) {
    if (!root) return;
    var walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, null, false);
    var nodes = [];
    var n;
    while ((n = walker.nextNode())) {
      if (n.textContent === 'GUIA') nodes.push(n);
    }
    nodes.forEach(styleGuiaNode);
  }

  var guiaObserver = new MutationObserver(function (mutations) {
    mutations.forEach(function (m) {
      m.addedNodes.forEach(function (n) {
        if (n.nodeType === Node.ELEMENT_NODE) walkForGuia(n);
        else if (n.nodeType === Node.TEXT_NODE) styleGuiaNode(n);
      });
    });
  });

  // ── 2. OAuth auto-click ────────────────────────────────────────
  function isLoginPage() {
    return window.location.pathname === '/login' ||
           window.location.pathname === '/';
  }

  function clickOAuthButton() {
    var buttons = document.querySelectorAll('button');
    for (var i = 0; i < buttons.length; i++) {
      var text = (buttons[i].textContent || '').toLowerCase();
      if (text.includes('upeu') || text.includes('continuar con')) {
        buttons[i].click();
        return true;
      }
    }
    return false;
  }

  // ── 3. SVG radar inline ────────────────────────────────────────
  var NS = 'http://www.w3.org/2000/svg';

  function el(tag, attrs) {
    var e = document.createElementNS(NS, tag);
    Object.keys(attrs).forEach(function (k) { e.setAttribute(k, attrs[k]); });
    return e;
  }

  function buildRadarSVG() {
    var svg = el('svg', {
      xmlns: NS,
      viewBox: '0 0 800 900',
      preserveAspectRatio: 'xMidYMid slice',
      'aria-hidden': 'true',
      class: 'guia-radar'
    });

    var defs = document.createElementNS(NS, 'defs');

    // Gradientes
    var bgGrad = el('linearGradient', { id: 'g-bg', x1: '0%', y1: '0%', x2: '60%', y2: '100%' });
    bgGrad.appendChild(el('stop', { offset: '0%',   'stop-color': '#001929' }));
    bgGrad.appendChild(el('stop', { offset: '100%', 'stop-color': '#023052' }));

    var glow1 = el('radialGradient', { id: 'g-glow1', cx: '35%', cy: '28%', r: '55%' });
    glow1.appendChild(el('stop', { offset: '0%',   'stop-color': '#2ea3f2', 'stop-opacity': '0.13' }));
    glow1.appendChild(el('stop', { offset: '100%', 'stop-color': '#2ea3f2', 'stop-opacity': '0' }));

    var glow2 = el('radialGradient', { id: 'g-glow2', cx: '72%', cy: '78%', r: '40%' });
    glow2.appendChild(el('stop', { offset: '0%',   'stop-color': '#f8a900', 'stop-opacity': '0.06' }));
    glow2.appendChild(el('stop', { offset: '100%', 'stop-color': '#f8a900', 'stop-opacity': '0' }));

    var dotFade = el('radialGradient', { id: 'g-dotfade', cx: '50%', cy: '45%', r: '48%' });
    dotFade.appendChild(el('stop', { offset: '0%',  'stop-color': 'white', 'stop-opacity': '1' }));
    dotFade.appendChild(el('stop', { offset: '75%', 'stop-color': 'white', 'stop-opacity': '0' }));

    // Dot pattern
    var pattern = el('pattern', { id: 'g-dots', x: '0', y: '0', width: '28', height: '28', patternUnits: 'userSpaceOnUse' });
    pattern.appendChild(el('circle', { cx: '14', cy: '14', r: '1.3', fill: '#2ea3f2', opacity: '0.22' }));

    // Mask
    var mask = el('mask', { id: 'g-mdots' });
    mask.appendChild(el('rect', { width: '800', height: '900', fill: 'url(#g-dotfade)' }));

    [bgGrad, glow1, glow2, dotFade, pattern, mask].forEach(function (d) { defs.appendChild(d); });
    svg.appendChild(defs);

    // Capas de fondo
    svg.appendChild(el('rect', { width: '800', height: '900', fill: 'url(#g-bg)' }));
    svg.appendChild(el('rect', { width: '800', height: '900', fill: 'url(#g-glow1)' }));
    svg.appendChild(el('rect', { width: '800', height: '900', fill: 'url(#g-glow2)' }));
    svg.appendChild(el('rect', { width: '800', height: '900', fill: 'url(#g-dots)', mask: 'url(#g-mdots)' }));

    // Anillos con data-ring para CSS animations
    [
      { r: '120', sw: '0.8', op: '0.20', ring: '1' },
      { r: '200', sw: '0.7', op: '0.16', ring: '2' },
      { r: '290', sw: '0.6', op: '0.12', ring: '3' },
      { r: '390', sw: '0.5', op: '0.08', ring: '4' }
    ].forEach(function (cfg) {
      svg.appendChild(el('circle', {
        cx: '400', cy: '420', r: cfg.r,
        fill: 'none', stroke: '#2ea3f2',
        'stroke-width': cfg.sw, opacity: cfg.op,
        'data-ring': cfg.ring
      }));
    });

    // Punto central
    svg.appendChild(el('circle', { cx: '400', cy: '420', r: '5', fill: '#2ea3f2', opacity: '0.55', 'data-center': 'true' }));

    // Crosshair dashed giratorio
    svg.appendChild(el('circle', {
      cx: '400', cy: '420', r: '12',
      fill: 'none', stroke: '#2ea3f2',
      'stroke-width': '1.0', 'stroke-dasharray': '4 8',
      opacity: '0.35', 'data-crosshair': 'true'
    }));

    // Corner accents
    [
      ['0',   '0',   '80',  '0',   '#2ea3f2', '0.35'],
      ['0',   '0',   '0',   '80',  '#2ea3f2', '0.35'],
      ['800', '900', '720', '900', '#f8a900', '0.22'],
      ['800', '900', '800', '820', '#f8a900', '0.22'],
      ['0',   '450', '180', '450', '#2ea3f2', '0.15'],
      ['620', '390', '800', '390', '#2ea3f2', '0.15']
    ].forEach(function (l) {
      svg.appendChild(el('line', { x1: l[0], y1: l[1], x2: l[2], y2: l[3], stroke: l[4], 'stroke-width': '2', opacity: l[5] }));
    });

    return svg;
  }

  function injectRadar() {
    var panel = document.querySelector('div.grid > div:last-child');
    if (!panel) return false;
    if (panel.querySelector('.guia-radar')) return true;
    var img = panel.querySelector('img');
    if (!img) return false;
    panel.insertBefore(buildRadarSVG(), img);
    return true;
  }

  // ── Bootstrap ──────────────────────────────────────────────────
  function init() {
    // Wordmark en toda la app
    walkForGuia(document.body);
    guiaObserver.observe(document.body, { childList: true, subtree: true });

    if (isLoginPage()) {
      // OAuth auto-click
      if (!clickOAuthButton()) {
        var oauthObs = new MutationObserver(function () {
          if (clickOAuthButton()) oauthObs.disconnect();
        });
        oauthObs.observe(document.body, { childList: true, subtree: true });
        setTimeout(function () { oauthObs.disconnect(); }, 10000);
      }

      // SVG radar
      if (!injectRadar()) {
        var radarObs = new MutationObserver(function () {
          if (injectRadar()) radarObs.disconnect();
        });
        radarObs.observe(document.body, { childList: true, subtree: true });
        setTimeout(function () { radarObs.disconnect(); }, 15000);
      }
    }
  }

  if (document.body) { init(); }
  else { document.addEventListener('DOMContentLoaded', init); }
})();
