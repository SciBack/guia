"""RuleBasedRouter — Gate 1 de la cascada (~0ms).

Resuelve los casos triviales sin pagar el costo de embedding ni LLM:
- Saludos y cortesía → GREETING + T0_FAST + CLOUD_OK
- Patrones inequívocos campus_personal → CAMPUS_PERSONAL + T1_STD + ALWAYS_LOCAL
- Comandos directos (/help, /reset) → COMMAND + T0_FAST + CLOUD_OK

Si ningún patrón matchea, retorna None y la cascada delega al Gate 2.

Diseño: regex precompilados, case-insensitive, normalización mínima.
Latencia objetivo: <1ms (medible, no estimado).
"""

from __future__ import annotations

import re
import time
import unicodedata

from guia.routing.decision import (
    Gate,
    IntentCategory,
    PrivacyLevel,
    RouteDecision,
    Tier,
)


def _normalize(text: str) -> str:
    """Normaliza texto: minúsculas, sin tildes, sin signos iniciales, espacios colapsados."""
    text = text.strip().lower()
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    # Quitar signos de interrogación / exclamación iniciales (español: ¿¡)
    text = text.lstrip("¿¡?!.,;:")
    text = re.sub(r"\s+", " ", text).strip()
    return text


# ── Patrones de saludo / cortesía ─────────────────────────────────────────

_GREETING_PATTERNS = [
    re.compile(r"^(hola|hi|hello|hey|saludos)\b"),
    re.compile(r"^buen(os|as)\s+(dias|tardes|noches)\b"),
    re.compile(r"^(gracias|muchas\s+gracias|thank\s*you|thanks)\b"),
    re.compile(r"^(adios|chao|hasta\s+(luego|pronto|manana))\b"),
    re.compile(r"^(ok|okay|vale|perfecto|entendido|listo)\.?$"),
    re.compile(r"^(si|no|sip|nop)\.?,?\s*(gracias|por\s+favor)?\.?$"),
    re.compile(r"^(como\s+estas|que\s+tal)\b"),
    # Meta-preguntas sobre GUIA
    re.compile(r"^(que|quien)\s+(eres|es)\s+(tu|guia)\b"),
    re.compile(r"^(que\s+puedes\s+hacer|en\s+que\s+(me\s+)?puedes\s+ayudar)\b"),
]


# ── Patrones inequívocos de campus_personal (ALWAYS_LOCAL) ────────────────

# Posesivos en primera persona referidos a datos académico-administrativos.
# El match aquí FUERZA local sin pasar por el Gate 2 — no se admite ambigüedad.
_CAMPUS_PERSONAL_PATTERNS = [
    re.compile(r"\bmis?\s+(notas|calificaciones|promedio|ponderado)\b"),
    re.compile(r"\bmi\s+(deuda|pago|cuenta|estado\s+de\s+cuenta|saldo)\b"),
    re.compile(r"\b(cuanto\s+debo|tengo\s+(deuda|pendiente|saldo))\b"),
    re.compile(r"\bmis?\s+(prestamos?|libros\s+prestados|reservas?)\b"),
    re.compile(r"\b(libros?|prestamos?)\s+vencid"),
    re.compile(r"\bmis?\s+(matriculas?|cursos\s+matriculados|asignaturas)\b"),
    re.compile(r"\bmi\s+(horario|programacion|carga\s+academica)\b"),
    re.compile(r"\bmis?\s+(creditos?|avance\s+curricular)\b"),
    re.compile(r"\b(cuantos?\s+creditos?\s+me\s+faltan)\b"),
    re.compile(r"\bmi\s+(perfil|usuario|cuenta\s+institucional)\b"),
    re.compile(r"\bmi\s+(correo|email|contrasena|password)\s+(institucional|upeu|universitario)?\b"),
]


# ── Comandos directos ─────────────────────────────────────────────────────

_COMMAND_PATTERN = re.compile(r"^/[a-z]+(\s|$)")


# ── Router ────────────────────────────────────────────────────────────────


class RuleBasedRouter:
    """Gate 1 — reglas deterministas sin embedding ni LLM.

    Stateless por diseño. Latencia <1ms.
    """

    def decide(self, query: str) -> RouteDecision | None:
        """Aplica las reglas en orden de especificidad. None = no decidió."""
        t0 = time.perf_counter()
        normalized = _normalize(query)

        # 1. Comandos directos (más específicos)
        if _COMMAND_PATTERN.match(normalized):
            return self._decision(
                IntentCategory.COMMAND,
                Tier.T0_FAST,
                PrivacyLevel.CLOUD_OK,
                t0,
                f"command: {normalized.split()[0]}",
            )

        # 2. Campus personal (ALWAYS_LOCAL — no se negocia)
        for pat in _CAMPUS_PERSONAL_PATTERNS:
            if pat.search(normalized):
                return self._decision(
                    IntentCategory.CAMPUS_PERSONAL,
                    Tier.T1_STD,
                    PrivacyLevel.ALWAYS_LOCAL,
                    t0,
                    f"campus_personal: {pat.pattern[:40]}",
                )

        # 3. Saludos / cortesía
        for pat in _GREETING_PATTERNS:
            if pat.match(normalized):
                return self._decision(
                    IntentCategory.GREETING,
                    Tier.T0_FAST,
                    PrivacyLevel.CLOUD_OK,
                    t0,
                    f"greeting: {pat.pattern[:40]}",
                )

        return None

    @staticmethod
    def _decision(
        intent: IntentCategory,
        tier: Tier,
        privacy: PrivacyLevel,
        t0: float,
        reason: str,
    ) -> RouteDecision:
        latency_ms = (time.perf_counter() - t0) * 1000
        return RouteDecision(
            intent=intent,
            tier=tier,
            privacy=privacy,
            gate_used=Gate.RULES,
            confidence=1.0,  # Reglas deterministas: certeza total
            latency_ms=latency_ms,
            reason=reason,
        )
