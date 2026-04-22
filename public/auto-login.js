// GUIA UPeU — inyección externa
// 1. Wordmark "IA" gold en header del chat
// 2. Hero login: acrónimo + descripción + icono usuario en botón
// 3. Panel derecho: video de fondo + queries rotativas

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

  // ── Datos ────────────────────────────────────────────────────
  function isLoginPage() {
    return /^\/(login)?$/.test(window.location.pathname);
  }

  var DESCRIPTION =
    'Tu asistente académico UPeU. Consulta notas, ' +
    'horarios, préstamos de biblioteca, eventos del ' +
    'campus y repositorio de investigación — todo en ' +
    'lenguaje natural.';

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

  // ── 2. Hero content en login ──────────────────────────────────
  function injectHeroContent() {
    if (document.querySelector('.guia-acronym')) return true;

    var form = document.querySelector('form.flex');
    if (!form) return false;

    var titleDiv = form.querySelector('div.flex.flex-col.items-center');
    if (!titleDiv) return false;

    // Acrónimo bajo el wordmark GUIA
    var acronym = document.createElement('p');
    acronym.className = 'guia-acronym';
    acronym.textContent = 'Gateway Universitario · Información y Asistencia';
    titleDiv.appendChild(acronym);
    titleDiv.style.alignItems = 'center';
    titleDiv.style.textAlign = 'center';

    // Descripción breve en lugar de la lista de queries
    var desc = document.createElement('p');
    desc.className = 'guia-description';
    desc.textContent = DESCRIPTION;

    var grid = form.querySelector('div.grid');
    if (grid) form.insertBefore(desc, grid);

    // Icono + texto en botón OAuth
    var btn = form.querySelector('button[type="button"]');
    if (btn) {
      btn.insertAdjacentHTML('afterbegin', USER_ICON);
      var nodes = btn.childNodes;
      for (var i = 0; i < nodes.length; i++) {
        if (nodes[i].nodeType === 3 && nodes[i].textContent.trim()) {
          nodes[i].textContent = ' Ingresa con tu correo UPeU';
          break;
        }
      }
    }

    return true;
  }

  // ── 3. Panel derecho: video + queries rotativas ───────────────
  function injectVideoPanel() {
    var panel = document.querySelector('div.bg-muted.overflow-hidden');
    if (!panel) return false;
    if (panel.querySelector('.guia-video')) return true;

    // Video de fondo
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
    panel.appendChild(video);
    video.play().catch(function () {});

    // Overlay oscuro
    var overlay = document.createElement('div');
    overlay.className = 'guia-video-overlay';
    panel.appendChild(overlay);

    // Queries rotativas sobre el video
    var qbox = document.createElement('div');
    qbox.className = 'guia-qoverlay';

    var qlabel = document.createElement('div');
    qlabel.className = 'guia-qoverlay-label';
    qlabel.textContent = 'Pregúntale a GUIA';
    qbox.appendChild(qlabel);

    var qlist = document.createElement('div');
    qlist.className = 'guia-qoverlay-list';

    // 3 slots visibles en todo momento
    for (var s = 0; s < 3; s++) {
      var item = document.createElement('div');
      item.className = 'guia-qoverlay-item';
      item.textContent = QUERIES[s];
      qlist.appendChild(item);
    }
    qbox.appendChild(qlist);
    panel.appendChild(qbox);

    // Rotación rolling: un item cambia cada 2s en cascada
    // Slot 0 cambia a t=0, slot 1 a t=2s, slot 2 a t=4s, repite
    var indices = [0, 1, 2];   // índice actual de cada slot
    var nextIdx = 3;           // próximo query a mostrar

    function rotateSlot(slotPos) {
      var items = qlist.querySelectorAll('.guia-qoverlay-item');
      var el = items[slotPos];
      if (!el) return;

      el.classList.add('exiting');
      setTimeout(function () {
        el.textContent = QUERIES[nextIdx % QUERIES.length];
        indices[slotPos] = nextIdx % QUERIES.length;
        nextIdx++;
        el.classList.remove('exiting');
      }, 350);
    }

    // Stagger: slot 0 → 0ms, slot 1 → 2000ms, slot 2 → 4000ms, luego cicla
    var INTERVAL = 2000;
    setTimeout(function () {
      rotateSlot(0);
      setInterval(function () { rotateSlot(0); }, INTERVAL * 3);
    }, INTERVAL);

    setTimeout(function () {
      rotateSlot(1);
      setInterval(function () { rotateSlot(1); }, INTERVAL * 3);
    }, INTERVAL * 2);

    setTimeout(function () {
      rotateSlot(2);
      setInterval(function () { rotateSlot(2); }, INTERVAL * 3);
    }, INTERVAL * 3);

    return true;
  }

  // ── Bootstrap ──────────────────────────────────────────────────
  function init() {
    walkForGuia(document.body);
    guiaObs.observe(document.body, { childList: true, subtree: true });

    if (isLoginPage()) {
      var heroDone = false;
      var videoDone = false;

      function tryInject() {
        if (!heroDone) heroDone = injectHeroContent();
        if (!videoDone) videoDone = injectVideoPanel();
        return heroDone && videoDone;
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
