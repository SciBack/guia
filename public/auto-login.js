// GUIA UPeU — inyección externa
// 1. Wordmark "IA" gold en header del chat
// 2. Hero content en login (acrónimo, queries de ejemplo, icono usuario)
// 3. Knowledge graph animado en panel derecho

(function () {
  'use strict';

  // ── 1. Wordmark "IA" gold en chat ─────────────────────────────
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

  // ── 2. Hero content en login ──────────────────────────────────
  function isLoginPage() {
    return /^\/(login)?$/.test(window.location.pathname);
  }

  var QUERIES = [
    '¿Cuáles son mis notas del semestre actual?',
    '¿Dónde es mi próxima clase y a qué hora?',
    '¿Tengo libros prestados o multas en biblioteca?',
    '¿Qué eventos hay esta semana en el salón de actos?',
    'Busca tesis sobre machine learning en el repositorio UPeU',
    '¿Dónde consigo una laptop o proyector para mi sustentación?'
  ];

  var USER_ICON = '<svg width="17" height="17" viewBox="0 0 24 24" fill="none" ' +
    'stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" ' +
    'style="flex-shrink:0;opacity:0.75">' +
    '<path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/>' +
    '<circle cx="12" cy="7" r="4"/></svg>';

  function injectHeroContent() {
    if (document.querySelector('.guia-acronym')) return true;

    var form = document.querySelector('form.flex');
    if (!form) return false;

    var titleDiv = form.querySelector('div.flex.flex-col.items-center');
    if (!titleDiv) return false;

    // Acrónimo bajo el h1
    var acronym = document.createElement('p');
    acronym.className = 'guia-acronym';
    acronym.textContent = 'Gateway Universitario · Información y Asistencia';
    titleDiv.appendChild(acronym);

    // Cambiar alineación del div de título a izquierda
    titleDiv.style.alignItems = 'center';
    titleDiv.style.textAlign = 'center';

    // Queries de ejemplo
    var section = document.createElement('div');
    section.className = 'guia-queries';

    var label = document.createElement('div');
    label.className = 'guia-queries-label';
    label.textContent = 'Pregúntale a GUIA';
    section.appendChild(label);

    QUERIES.forEach(function (q) {
      var item = document.createElement('div');
      item.className = 'guia-query-item';
      item.textContent = q;
      section.appendChild(item);
    });

    var grid = form.querySelector('div.grid');
    if (grid) form.insertBefore(section, grid);

    // Icono usuario en el botón OAuth
    var btn = form.querySelector('button[type="button"]');
    if (btn) btn.insertAdjacentHTML('afterbegin', USER_ICON);

    return true;
  }

  // ── 3. Video de fondo en panel derecho ───────────────────────
  function injectVideoPanel() {
    var panel = document.querySelector('div.bg-muted.overflow-hidden');
    if (!panel) return false;
    if (panel.querySelector('.guia-video')) return true;

    var video = document.createElement('video');
    video.className = 'guia-video';
    video.autoplay = true;
    video.loop = true;
    video.muted = true;
    video.setAttribute('playsinline', '');
    video.setAttribute('aria-hidden', 'true');

    var source = document.createElement('source');
    source.src = '/public/guia-bg.mp4';
    source.type = 'video/mp4';
    video.appendChild(source);

    var overlay = document.createElement('div');
    overlay.className = 'guia-video-overlay';

    panel.appendChild(video);
    panel.appendChild(overlay);

    video.play().catch(function () {});
    return true;
  }

  // Legacy canvas vars (kept for reference but not used)
  var NODE_DEFS = [
    // hub central — GUIA
    { rx: 0.50, ry: 0.46, r: 8.0, op: 0.90, hub: true,  po: 0,   dr: 0     },
    // primer nivel
    { rx: 0.30, ry: 0.23, r: 5.0, op: 0.65, hub: false, po: 1.1, dr: 0.012 },
    { rx: 0.63, ry: 0.19, r: 4.0, op: 0.55, hub: false, po: 2.3, dr: 0.010 },
    { rx: 0.77, ry: 0.37, r: 5.5, op: 0.68, hub: false, po: 0.7, dr: 0.011 },
    { rx: 0.73, ry: 0.64, r: 3.5, op: 0.50, hub: false, po: 3.1, dr: 0.013 },
    { rx: 0.55, ry: 0.75, r: 4.5, op: 0.58, hub: false, po: 1.8, dr: 0.010 },
    { rx: 0.32, ry: 0.72, r: 4.0, op: 0.55, hub: false, po: 2.7, dr: 0.012 },
    { rx: 0.19, ry: 0.54, r: 5.0, op: 0.62, hub: false, po: 0.4, dr: 0.009 },
    { rx: 0.21, ry: 0.33, r: 3.5, op: 0.50, hub: false, po: 3.8, dr: 0.011 },
    // segundo nivel
    { rx: 0.43, ry: 0.13, r: 2.5, op: 0.38, hub: false, po: 1.5, dr: 0.016 },
    { rx: 0.83, ry: 0.23, r: 3.0, op: 0.38, hub: false, po: 2.1, dr: 0.014 },
    { rx: 0.87, ry: 0.59, r: 2.5, op: 0.33, hub: false, po: 0.9, dr: 0.015 },
    { rx: 0.13, ry: 0.17, r: 2.5, op: 0.30, hub: false, po: 4.2, dr: 0.013 },
    { rx: 0.11, ry: 0.73, r: 3.0, op: 0.35, hub: false, po: 3.4, dr: 0.012 },
    { rx: 0.61, ry: 0.89, r: 2.5, op: 0.30, hub: false, po: 1.9, dr: 0.014 },
  ];

  var CONNECTIONS = [
    [0,1,0.22],[0,2,0.18],[0,3,0.24],[0,4,0.17],[0,5,0.20],
    [0,6,0.18],[0,7,0.22],[0,8,0.17],
    [1,2,0.12],[2,3,0.13],[3,4,0.12],[4,5,0.11],
    [5,6,0.12],[6,7,0.11],[7,8,0.12],[8,1,0.11],
    [1,9,0.09],[2,10,0.09],[3,11,0.08],
    [1,12,0.08],[7,13,0.08],[5,14,0.08],
    [2,5,0.09],[1,6,0.08],[3,7,0.09],[4,8,0.08],
  ];

  function injectKnowledgeGraph() {
    var panel = document.querySelector('div.bg-muted.overflow-hidden');
    if (!panel) return false;
    if (panel.querySelector('.guia-canvas')) return true;

    var canvas = document.createElement('canvas');
    canvas.className = 'guia-canvas';
    panel.appendChild(canvas);

    var ctx = canvas.getContext('2d');
    var reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    // Estado de fade-in de cada conexión
    var connState = CONNECTIONS.map(function (c, i) {
      return { cur: 0, max: c[2], delay: i * 0.09 };
    });

    var t0 = Date.now();

    function draw() {
      var W = panel.offsetWidth;
      var H = panel.offsetHeight;
      if (!W || !H) { requestAnimationFrame(draw); return; }
      canvas.width = W;
      canvas.height = H;

      var t = (Date.now() - t0) / 1000;

      // ── Fondo ────────────────────────────────────────────────
      var bg = ctx.createLinearGradient(0, 0, W * 0.5, H);
      bg.addColorStop(0, '#001626');
      bg.addColorStop(1, '#012d4e');
      ctx.fillStyle = bg;
      ctx.fillRect(0, 0, W, H);

      // Glows de ambiente
      var g1 = ctx.createRadialGradient(W*0.32, H*0.25, 0, W*0.32, H*0.25, W*0.52);
      g1.addColorStop(0, 'rgba(46,163,242,0.11)'); g1.addColorStop(1, 'transparent');
      ctx.fillStyle = g1; ctx.fillRect(0, 0, W, H);

      var g2 = ctx.createRadialGradient(W*0.70, H*0.80, 0, W*0.70, H*0.80, W*0.38);
      g2.addColorStop(0, 'rgba(248,169,0,0.06)'); g2.addColorStop(1, 'transparent');
      ctx.fillStyle = g2; ctx.fillRect(0, 0, W, H);

      // ── Posiciones de nodos con drift orgánico ────────────────
      var nodes = NODE_DEFS.map(function (n) {
        var pulse = reduced ? 0 : Math.sin(t * 1.1 + n.po) * 0.20;
        var dx = reduced ? 0 : Math.sin(t * 0.19 + n.po * 1.73) * n.dr * W;
        var dy = reduced ? 0 : Math.cos(t * 0.16 + n.po * 1.41) * n.dr * H;
        return {
          x: n.rx * W + (n.hub ? 0 : dx),
          y: n.ry * H + (n.hub ? 0 : dy),
          r: n.r + (n.hub ? Math.abs(pulse) * 2.8 : Math.abs(pulse) * 0.9),
          op: Math.max(0.18, Math.min(1, n.op + pulse * 0.30)),
          hub: n.hub
        };
      });

      var hub = nodes[0];

      // ── Pulsos radiales desde el hub (3 anillos en fases) ─────
      if (!reduced) {
        for (var p = 0; p < 3; p++) {
          var pt = ((t * 0.20 + p / 3) % 1);
          var pr = pt * 130;
          var po = Math.pow(1 - pt, 1.5) * 0.18;
          ctx.beginPath();
          ctx.arc(hub.x, hub.y, pr, 0, Math.PI * 2);
          ctx.strokeStyle = 'rgba(46,163,242,' + po + ')';
          ctx.lineWidth = 1.2;
          ctx.stroke();
        }
      }

      // ── Conexiones con fade-in escalonado ─────────────────────
      CONNECTIONS.forEach(function (c, i) {
        var a = nodes[c[0]], b = nodes[c[1]];
        var cs = connState[i];
        var elapsed = t - cs.delay;
        if (elapsed < 0) return;
        cs.cur = Math.min(cs.max, cs.cur + 0.005);
        var op = cs.cur;
        if (!reduced) op *= (0.60 + 0.40 * Math.sin(t * 0.32 + i * 0.68));

        ctx.beginPath();
        ctx.moveTo(a.x, a.y);
        ctx.lineTo(b.x, b.y);
        ctx.strokeStyle = 'rgba(46,163,242,' + op + ')';
        ctx.lineWidth = 0.8;
        ctx.stroke();
      });

      // ── Partículas de datos viajando por conexiones ───────────
      if (!reduced) {
        CONNECTIONS.forEach(function (c, i) {
          var cs = connState[i];
          if (cs.cur < cs.max * 0.4) return;
          var a = nodes[c[0]], b = nodes[c[1]];
          var speed = 0.28 + (i % 7) * 0.04;
          var phase = (t * speed + i * 0.43) % 1;
          var px = a.x + (b.x - a.x) * phase;
          var py = a.y + (b.y - a.y) * phase;
          var particleOp = 0.5 + 0.5 * Math.sin(t * 1.5 + i);
          var gp = ctx.createRadialGradient(px, py, 0, px, py, 3.5);
          gp.addColorStop(0, 'rgba(46,163,242,' + particleOp + ')');
          gp.addColorStop(1, 'transparent');
          ctx.fillStyle = gp;
          ctx.beginPath();
          ctx.arc(px, py, 3.5, 0, Math.PI * 2);
          ctx.fill();
        });
      }

      // ── Nodos ─────────────────────────────────────────────────
      nodes.forEach(function (n) {
        // Glow exterior
        var glowR = n.hub ? n.r * 6 : n.r * 5;
        var gr = ctx.createRadialGradient(n.x, n.y, 0, n.x, n.y, glowR);
        gr.addColorStop(0, 'rgba(46,163,242,' + (n.op * (n.hub ? 0.28 : 0.18)) + ')');
        gr.addColorStop(1, 'transparent');
        ctx.fillStyle = gr;
        ctx.beginPath();
        ctx.arc(n.x, n.y, glowR, 0, Math.PI * 2);
        ctx.fill();

        // Punto central
        ctx.fillStyle = n.hub
          ? 'rgba(46,163,242,' + Math.min(1, n.op) + ')'
          : 'rgba(46,163,242,' + Math.min(0.95, n.op) + ')';
        ctx.beginPath();
        ctx.arc(n.x, n.y, n.r, 0, Math.PI * 2);
        ctx.fill();

        // Ring extra en hub
        if (n.hub) {
          ctx.beginPath();
          ctx.arc(n.x, n.y, n.r + 4, 0, Math.PI * 2);
          ctx.strokeStyle = 'rgba(46,163,242,0.30)';
          ctx.lineWidth = 1;
          ctx.stroke();
        }
      });

      requestAnimationFrame(draw);
    }

    draw();
    return true;
  }

  // ── Bootstrap ──────────────────────────────────────────────────
  function init() {
    walkForGuia(document.body);
    guiaObs.observe(document.body, { childList: true, subtree: true });

    if (isLoginPage()) {
      var heroDone = false;
      var graphDone = false;

      function tryInject() {
        if (!heroDone) heroDone = injectHeroContent();
        if (!graphDone) graphDone = injectVideoPanel();
        return heroDone && graphDone;
      }

      if (!tryInject()) {
        var obs = new MutationObserver(function () {
          if (tryInject()) obs.disconnect();
        });
        obs.observe(document.body, { childList: true, subtree: true });
        setTimeout(function () { obs.disconnect(); }, 15000);
      }
    }
  }

  if (document.body) { init(); }
  else { document.addEventListener('DOMContentLoaded', init); }
})();
