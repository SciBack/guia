// Auto-redirige al login de UPeU sin mostrar la pantalla intermedia de Chainlit.
// Busca el botón OAuth de Keycloak y lo cliquea automáticamente.
(function () {
  function clickOAuthButton() {
    // Chainlit renderiza un botón con el texto del proveedor OAuth
    const buttons = document.querySelectorAll("button");
    for (const btn of buttons) {
      if (btn.textContent.includes("Correo UPeU")) {
        btn.click();
        return true;
      }
    }
    return false;
  }

  // Espera a que React monte el DOM y cliquea
  function tryClick(attempts) {
    if (attempts <= 0) return;
    if (!clickOAuthButton()) {
      setTimeout(() => tryClick(attempts - 1), 300);
    }
  }

  // Solo actuar si el usuario NO está autenticado (página de login)
  if (window.location.pathname === "/login" || window.location.pathname === "/") {
    setTimeout(() => tryClick(20), 500);
  }
})();
