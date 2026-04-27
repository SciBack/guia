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
    '¿Cómo accedo a las bases de datos digitales de biblioteca?',
    '¿Hay actividades culturales o deportivas esta semana?'
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

    // Overlay lateral izquierdo
    var overlay = document.createElement('div');
    overlay.className = 'guia-video-overlay';
    panel.appendChild(overlay);

    // Degradado fijo en la base — siempre pegado al fondo del panel
    var bottomFade = document.createElement('div');
    bottomFade.className = 'guia-bottom-fade';
    panel.appendChild(bottomFade);

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
      var span = document.createElement('span');
      span.className = 'guia-qoverlay-text';
      span.textContent = QUERIES[s];
      item.appendChild(span);
      qlist.appendChild(item);
    }
    qbox.appendChild(qlist);
    panel.appendChild(qbox);

    // Rotación por grupos de 3
    // Transición: salida hacia arriba (exit-up) → entrada desde abajo (enter-down)
    // Rotación por grupos de 3 — solo fade, sin slide
    var groupIdx = 1;
    var GROUPS = Math.ceil(QUERIES.length / 3);
    var FADE_MS = 500;
    var VISIBLE_MS = 3000;

    function rotateGroup() {
      var spans = qlist.querySelectorAll('.guia-qoverlay-text');

      // 1. Fade out solo el texto (el fondo del card permanece)
      spans.forEach(function (sp) { sp.classList.add('q-hidden'); });

      setTimeout(function () {
        // 2. Cambiar texto mientras está invisible
        var base = (groupIdx % GROUPS) * 3;
        spans.forEach(function (sp, i) {
          var qi = base + i;
          sp.textContent = qi < QUERIES.length ? QUERIES[qi] : '';
        });
        groupIdx++;

        // 3. Fade in con stagger suave
        spans.forEach(function (sp, i) {
          setTimeout(function () { sp.classList.remove('q-hidden'); }, i * 80);
        });
      }, FADE_MS);
    }

    setTimeout(function () {
      rotateGroup();
      setInterval(rotateGroup, VISIBLE_MS + FADE_MS + 300);
    }, VISIBLE_MS);

    return true;
  }

  // ── 4. README modal ──────────────────────────────────────────────
  var _rmModal = null;

  function buildReadmeModal() {
    if (_rmModal) return _rmModal;

    // Backdrop
    var backdrop = document.createElement('div');
    backdrop.id = 'guia-rm-backdrop';
    backdrop.setAttribute('role', 'dialog');
    backdrop.setAttribute('aria-modal', 'true');
    backdrop.setAttribute('aria-labelledby', 'guia-rm-title');

    // Modal box
    var modal = document.createElement('div');
    modal.id = 'guia-rm-modal';

    // Header
    var header = document.createElement('div');
    header.id = 'guia-rm-header';

    var titleEl = document.createElement('h2');
    titleEl.id = 'guia-rm-title';
    titleEl.textContent = 'Guía rápida de GUIA';

    var closeBtn = document.createElement('button');
    closeBtn.id = 'guia-rm-close';
    closeBtn.setAttribute('aria-label', 'Cerrar');
    closeBtn.innerHTML =
      '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor"' +
      ' stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">' +
      '<line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>';

    header.appendChild(titleEl);
    header.appendChild(closeBtn);

    // Body
    var body = document.createElement('div');
    body.id = 'guia-rm-body';
    body.innerHTML = '<p style="color:hsl(var(--muted-foreground));padding:1rem 0">Cargando…</p>';

    modal.appendChild(header);
    modal.appendChild(body);
    backdrop.appendChild(modal);
    document.body.appendChild(backdrop);

    function closeModal() {
      backdrop.classList.remove('open');
      document.body.style.overflow = '';
    }

    function openModal() {
      // Re-trigger animation
      modal.classList.remove('guia-rm-animate');
      void modal.offsetWidth;
      modal.classList.add('guia-rm-animate');

      backdrop.classList.add('open');
      document.body.style.overflow = 'hidden';
      closeBtn.focus();

      if (!body.dataset.loaded) {
        fetch('/public/readme-content.html')
          .then(function (r) { return r.text(); })
          .then(function (html) {
            body.innerHTML = html;
            body.dataset.loaded = '1';
          })
          .catch(function () {
            body.innerHTML = '<p>No se pudo cargar el contenido. Recarga la página.</p>';
          });
      }
    }

    closeBtn.addEventListener('click', closeModal);
    backdrop.addEventListener('click', function (e) {
      if (e.target === backdrop) closeModal();
    });
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && backdrop.classList.contains('open')) closeModal();
    });

    _rmModal = { open: openModal };
    return _rmModal;
  }

  function interceptReadmeButton(btn) {
    if (btn.dataset.guiaRm) return;
    btn.dataset.guiaRm = '1';
    btn.addEventListener('click', function (e) {
      e.preventDefault();
      e.stopPropagation();
      e.stopImmediatePropagation();
      buildReadmeModal().open();
    }, true); // capture — antes de que React lo procese
  }

  function scanReadmeButtons() {
    var all = document.querySelectorAll('button, [role="button"], a');
    for (var i = 0; i < all.length; i++) {
      var el = all[i];
      if (el.dataset.guiaRm) continue;
      var text  = (el.textContent || '').trim();
      var label = (el.getAttribute('aria-label') || '').toLowerCase();
      var title = (el.getAttribute('title') || '').toLowerCase();
      if (
        text === 'Léeme' || text === 'Readme' || text === 'Read me' ||
        label.includes('readme') || label.includes('léeme') || label.includes('leeme') ||
        title.includes('readme') || title.includes('léeme') || title.includes('leeme')
      ) {
        interceptReadmeButton(el);
      }
    }
  }

  // ── 5. Logout → Keycloak end_session (top-level navigation) ────
  // fetch() no envía cookies cross-origin al seguir redirects, así que
  // on_logout devuelve JSON con la URL y aquí navegamos el browser.
  function patchFetchForLogout() {
    var _orig = window.fetch.bind(window);
    window.fetch = function (url, opts) {
      var p = _orig(url, opts);
      var path = typeof url === 'string' ? url : (url && url.url) || '';
      if (path === '/logout' || path.endsWith('/logout')) {
        p.then(function (resp) {
          resp.clone().json().then(function (data) {
            if (data && data.keycloak_logout) {
              window.location.href = data.keycloak_logout;
            }
          }).catch(function () {});
        }).catch(function () {});
      }
      return p;
    };
  }

  // ── Bootstrap ──────────────────────────────────────────────────
  function init() {
    patchFetchForLogout();
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

    // Siempre escanear — el botón Léeme solo existe en el chat, no en el login
    scanReadmeButtons();
    var rmObs = new MutationObserver(scanReadmeButtons);
    rmObs.observe(document.body, { childList: true, subtree: true });
  }

  if (document.body) { init(); }
  else { document.addEventListener('DOMContentLoaded', init); }
})();
