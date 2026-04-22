// GUIA UPeU — scripts de inyección externa
// 1. Colorea "IA" de GUIA en gold en el header del chat
// 2. Inyecta knowledge graph animado en Canvas en el panel derecho del login

(function () {
  'use strict';

  // ── 1. Wordmark: "IA" en gold ──────────────────────────────────
  var STYLED = 'data-guia-styled';

  function styleGuiaNode(node) {
    if (node.textContent !== 'GUIA') return;
    var p = node.parentElement;
    if (!p || p.hasAttribute(STYLED)) return;
    var s = document.createElement('span');
    s.className = 'guia-wordmark';
    s.setAttribute(STYLED, '1');
    s.innerHTML = 'GU<span class="guia-ia">IA</span>';
    p.replaceChild(s, node);
  }

  function walkForGuia(root) {
    if (!root) return;
    var walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, null, false);
    var nodes = [], n;
    while ((n = walker.nextNode())) { if (n.textContent === 'GUIA') nodes.push(n); }
    nodes.forEach(styleGuiaNode);
  }

  var guiaObs = new MutationObserver(function (muts) {
    muts.forEach(function (m) {
      m.addedNodes.forEach(function (n) {
        if (n.nodeType === 1) walkForGuia(n);
        else if (n.nodeType === 3) styleGuiaNode(n);
      });
    });
  });

  // ── 2. Knowledge graph en Canvas ──────────────────────────────
  function isLoginPage() {
    return /^\/(login)?$/.test(window.location.pathname);
  }

  // Nodos del grafo (posiciones relativas 0-1 al canvas)
  var NODE_DEFS = [
    // Hub central — representa GUIA
    { rx: 0.50, ry: 0.47, r: 7.5, op: 0.85, hub: true,  po: 0 },
    // Nodos de primer nivel (papers, autores)
    { rx: 0.30, ry: 0.24, r: 4.5, op: 0.60, hub: false, po: 1.1 },
    { rx: 0.62, ry: 0.20, r: 3.5, op: 0.50, hub: false, po: 2.3 },
    { rx: 0.76, ry: 0.38, r: 5.0, op: 0.65, hub: false, po: 0.7 },
    { rx: 0.72, ry: 0.63, r: 3.0, op: 0.45, hub: false, po: 3.1 },
    { rx: 0.54, ry: 0.74, r: 4.0, op: 0.55, hub: false, po: 1.8 },
    { rx: 0.33, ry: 0.71, r: 3.5, op: 0.50, hub: false, po: 2.7 },
    { rx: 0.20, ry: 0.55, r: 4.5, op: 0.58, hub: false, po: 0.4 },
    { rx: 0.22, ry: 0.34, r: 3.0, op: 0.45, hub: false, po: 3.8 },
    // Nodos de segundo nivel (más periféricos)
    { rx: 0.42, ry: 0.14, r: 2.0, op: 0.35, hub: false, po: 1.5 },
    { rx: 0.82, ry: 0.24, r: 2.5, op: 0.35, hub: false, po: 2.1 },
    { rx: 0.85, ry: 0.58, r: 2.0, op: 0.30, hub: false, po: 0.9 },
    { rx: 0.14, ry: 0.18, r: 2.0, op: 0.28, hub: false, po: 4.2 },
    { rx: 0.12, ry: 0.72, r: 2.5, op: 0.32, hub: false, po: 3.4 },
    { rx: 0.60, ry: 0.88, r: 2.0, op: 0.28, hub: false, po: 1.9 },
  ];

  // Conexiones: [from, to, base_opacity]
  var CONNECTIONS = [
    // Hub → todos los de primer nivel
    [0,1,0.18],[0,2,0.15],[0,3,0.20],[0,4,0.14],[0,5,0.17],
    [0,6,0.15],[0,7,0.18],[0,8,0.14],
    // Anillo exterior
    [1,2,0.10],[2,3,0.11],[3,4,0.10],[4,5,0.09],
    [5,6,0.10],[6,7,0.09],[7,8,0.10],[8,1,0.09],
    // Nodos periféricos
    [1,9,0.08],[2,10,0.08],[3,11,0.07],
    [1,12,0.07],[7,13,0.07],[5,14,0.07],
    // Conexiones cruzadas
    [2,5,0.08],[1,6,0.07],[3,7,0.08],[4,8,0.07],
  ];

  function injectKnowledgeGraph() {
    var panel = document.querySelector('div.grid > div:last-child');
    if (!panel) return false;
    if (panel.querySelector('.guia-canvas')) return true;
    // El panel tiene que tener algo (img u otros hijos) para estar listo
    if (!panel.children.length) return false;

    var canvas = document.createElement('canvas');
    canvas.className = 'guia-canvas';
    panel.appendChild(canvas);

    var ctx = canvas.getContext('2d');
    var reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    // Fade-in de conexiones escalonado
    var connState = CONNECTIONS.map(function (c, i) {
      return { cur: 0, max: c[2], delay: i * 0.12 };
    });

    var t0 = Date.now();
    var raf;

    function draw() {
      var W = panel.offsetWidth;
      var H = panel.offsetHeight;
      if (!W || !H) { raf = requestAnimationFrame(draw); return; }
      canvas.width = W;
      canvas.height = H;

      var t = (Date.now() - t0) / 1000;

      // ── Fondo ────────────────────────────────────────────────
      var bg = ctx.createLinearGradient(0, 0, W * 0.6, H);
      bg.addColorStop(0, '#001929');
      bg.addColorStop(1, '#023052');
      ctx.fillStyle = bg;
      ctx.fillRect(0, 0, W, H);

      var g1 = ctx.createRadialGradient(W*0.35,H*0.28,0, W*0.35,H*0.28, W*0.55);
      g1.addColorStop(0, 'rgba(46,163,242,0.12)'); g1.addColorStop(1,'transparent');
      ctx.fillStyle = g1; ctx.fillRect(0,0,W,H);

      var g2 = ctx.createRadialGradient(W*0.72,H*0.78,0, W*0.72,H*0.78, W*0.4);
      g2.addColorStop(0,'rgba(248,169,0,0.05)'); g2.addColorStop(1,'transparent');
      ctx.fillStyle = g2; ctx.fillRect(0,0,W,H);

      // ── Posiciones actuales de nodos ─────────────────────────
      var nodes = NODE_DEFS.map(function (n, i) {
        var pulse = reduced ? 0 : Math.sin(t * 1.1 + n.po) * 0.22;
        return {
          x: n.rx * W, y: n.ry * H,
          r: n.r + (n.hub ? Math.abs(pulse) * 2.5 : Math.abs(pulse)),
          op: Math.max(0.15, Math.min(1, n.op + pulse * 0.35)),
          hub: n.hub
        };
      });

      // ── Conexiones ───────────────────────────────────────────
      CONNECTIONS.forEach(function (c, i) {
        var a = nodes[c[0]], b = nodes[c[1]];
        var cs = connState[i];
        var elapsed = t - cs.delay;
        if (elapsed < 0) return;
        // Fade in suave
        cs.cur = Math.min(cs.max, cs.cur + 0.006);
        var op = cs.cur;
        if (!reduced) op *= (0.65 + 0.35 * Math.sin(t * 0.35 + i * 0.7));

        ctx.beginPath();
        ctx.moveTo(a.x, a.y);
        ctx.lineTo(b.x, b.y);
        ctx.strokeStyle = 'rgba(46,163,242,' + op + ')';
        ctx.lineWidth = 0.75;
        ctx.stroke();
      });

      // ── Nodos ────────────────────────────────────────────────
      nodes.forEach(function (n) {
        // Glow exterior
        var gr = ctx.createRadialGradient(n.x, n.y, 0, n.x, n.y, n.r * 5);
        gr.addColorStop(0, 'rgba(46,163,242,' + (n.op * 0.22) + ')');
        gr.addColorStop(1, 'transparent');
        ctx.fillStyle = gr;
        ctx.beginPath();
        ctx.arc(n.x, n.y, n.r * 5, 0, Math.PI * 2);
        ctx.fill();

        // Punto central
        ctx.fillStyle = 'rgba(46,163,242,' + Math.min(1, n.op) + ')';
        ctx.beginPath();
        ctx.arc(n.x, n.y, n.r, 0, Math.PI * 2);
        ctx.fill();
      });

      raf = requestAnimationFrame(draw);
    }

    draw();
    return true;
  }

  // ── Bootstrap ──────────────────────────────────────────────────
  function init() {
    walkForGuia(document.body);
    guiaObs.observe(document.body, { childList: true, subtree: true });

    if (isLoginPage()) {
      if (!injectKnowledgeGraph()) {
        var obs = new MutationObserver(function () {
          if (injectKnowledgeGraph()) obs.disconnect();
        });
        obs.observe(document.body, { childList: true, subtree: true });
        setTimeout(function () { obs.disconnect(); }, 15000);
      }
    }
  }

  if (document.body) { init(); }
  else { document.addEventListener('DOMContentLoaded', init); }
})();
