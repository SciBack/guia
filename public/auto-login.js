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
    // Notas y académico
    '¿Cuáles son mis notas del semestre actual?',
    '¿Cuál es mi promedio ponderado acumulado?',
    '¿Cuántos créditos me faltan para graduarme?',
    // Horarios y campus
    '¿Dónde es mi próxima clase y a qué hora?',
    '¿Cuál es mi horario completo de esta semana?',
    '¿En qué aula tengo el examen de mañana?',
    // Biblioteca Koha
    '¿Tengo libros prestados o multas en biblioteca?',
    '¿Cuándo vence el plazo de devolución de mis préstamos?',
    '¿Está disponible "Cálculo de Stewart" en biblioteca?',
    // Repositorio DSpace / OJS
    'Busca tesis sobre inteligencia artificial en el repositorio UPeU',
    '¿Qué investigaciones publicó la Facultad de Ingeniería este año?',
    '¿En qué revistas UPeU puedo publicar mi artículo?',
    // Eventos Indico
    '¿Qué eventos hay esta semana en el salón de actos?',
    '¿Cuándo es el próximo congreso de investigación UPeU?',
    // Recursos
    '¿Dónde consigo un proyector para mi sustentación?',
    '¿Cuáles son los horarios de atención de la biblioteca CRAI?',
    '¿Cómo accedo a las bases de datos digitales de biblioteca?'
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

    // Queries rotativas sobre el video — grupos de 3
    var qbox = document.createElement('div');
    qbox.className = 'guia-qoverlay';

    var qlabel = document.createElement('div');
    qlabel.className = 'guia-qoverlay-label';
    qlabel.textContent = 'Pregúntale a GUIA';
    qbox.appendChild(qlabel);

    var qlist = document.createElement('div');
    qlist.className = 'guia-qoverlay-list';

    for (var s = 0; s < 3; s++) {
      var item = document.createElement('div');
      item.className = 'guia-qoverlay-item';
      item.textContent = QUERIES[s];
      qlist.appendChild(item);
    }
    qbox.appendChild(qlist);
    panel.appendChild(qbox);

    // Rotación por grupos de 3
    // Transición: salida hacia arriba (exit-up) → entrada desde abajo (enter-down)
    var groupIdx = 1; // próximo grupo a mostrar (grupo 0 ya visible)
    var GROUPS = Math.ceil(QUERIES.length / 3);
    var EXIT_MS = 420;
    var PAUSE_MS = 80;
    var VISIBLE_MS = 3200;

    function rotateGroup() {
      var items = qlist.querySelectorAll('.guia-qoverlay-item');

      // 1. Salida: todos suben y desaparecen
      items.forEach(function (el) { el.classList.add('q-exit'); });

      setTimeout(function () {
        // 2. Reposicionar abajo sin transición
        items.forEach(function (el) {
          el.classList.remove('q-exit');
          el.classList.add('q-enter');
        });

        // 3. Actualizar texto del nuevo grupo
        var base = (groupIdx % GROUPS) * 3;
        items.forEach(function (el, i) {
          var qi = base + i;
          el.textContent = qi < QUERIES.length ? QUERIES[qi] : '';
        });

        groupIdx++;

        // 4. Forzar reflow para que la transición de entrada sea visible
        void qlist.offsetHeight;

        // 5. Entrada: suben desde abajo al sitio
        requestAnimationFrame(function () {
          requestAnimationFrame(function () {
            items.forEach(function (el, i) {
              el.classList.remove('q-enter');
              el.style.transitionDelay = (i * 60) + 'ms';
            });
            // Limpiar delay después de la transición
            setTimeout(function () {
              items.forEach(function (el) { el.style.transitionDelay = ''; });
            }, EXIT_MS + 200);
          });
        });

      }, EXIT_MS + PAUSE_MS);
    }

    // Primera rotación después de VISIBLE_MS, luego ciclo continuo
    setTimeout(function () {
      rotateGroup();
      setInterval(rotateGroup, VISIBLE_MS + EXIT_MS + PAUSE_MS + 100);
    }, VISIBLE_MS);

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
