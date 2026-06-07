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
    # Saludos básicos
    re.compile(r"^(hola|hi|hello|hey|saludos)\b"),
    re.compile(r"^buen(os|as)\s+(dias|tardes|noches)\b"),
    re.compile(r"^(gracias|muchas\s+gracias|thank\s*you|thanks)\b"),
    re.compile(r"^(adios|chao|hasta\s+(luego|pronto|manana))\b"),
    re.compile(r"^(ok|okay|vale|perfecto|entendido|listo)\.?$"),
    re.compile(r"^(si|no|sip|nop)\.?,?\s*(gracias|por\s+favor)?\.?$"),
    re.compile(r"^(como\s+estas|que\s+tal)\b"),
    # Identidad del asistente
    re.compile(r"^como\s+te\s+llamas\b"),
    re.compile(r"^cual\s+es\s+tu\s+nombre\b"),
    re.compile(r"^(quien|que)\s+eres\b"),
    re.compile(r"^(eres|es)\s+(un\s+)?(robot|ia|inteligencia|bot|chatbot|humano|persona)\b"),
    re.compile(r"^(que|quien)\s+(eres|es)\s+(tu|guia)\b"),
    # Capacidades y fuentes
    re.compile(r"^(que\s+puedes\s+hacer|en\s+que\s+(me\s+)?puedes\s+ayudar)\b"),
    re.compile(r"^(para\s+que\s+sirves?|como\s+funcionas?)\b"),
    re.compile(r"^(que\s+sabes?\s+(hacer|decirme))\b"),
    re.compile(r"^(cuales?\s+(son\s+)?(tus?\s+)?(capacidades?|funciones?|fuentes?))\b"),
    re.compile(r"^(que\s+(fuentes?|bases?\s+de\s+datos?|repositorios?)\s+(tienes?|usas?|manejas?))\b"),
    re.compile(r"^(que\s+informacion\s+(tienes?|manejas?|conoces?))\b"),
    # Novedades / estado del sistema
    re.compile(r"^(que|hay|tienes?)\s+(novedades?|de\s+nuevo|noticias?)\b"),
    re.compile(r"^novedades?\b"),
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


# ── Meta-preguntas sobre capacidades / fuentes del asistente ──────────────

# Preguntas sobre qué es / qué tiene / a qué accede GUIA. A diferencia de los
# saludos, suelen ser largas ("¿tienes acceso a alguna otra fuente además de
# Koha?"), así que NO aplican la regla del remainder — se buscan con `search`
# en cualquier posición. Deben ser específicas para NO capturar búsquedas
# legítimas ("tienes libros de X" NO matchea: no hay 'acceso'/'fuentes').
_META_CAPABILITY_PATTERNS = [
    re.compile(r"\btienes?\s+(acceso|conexion|integracion)\b"),
    re.compile(
        r"\b(que\s+)?(fuentes?|bases?\s+de\s+datos?|repositorios?|sistemas?)\s+"
        r"(tienes?|usas?|manejas?|hay|estan\s+disponibles?|disponibles?)\b"
    ),
    re.compile(r"\btienes?\s+(otras?\s+|mas\s+)?(fuentes?|repositorios?|bases?\s+de\s+datos?)\b"),
    re.compile(r"\bademas\s+de\s+(koha|ojs|dspace|alicia)\b"),
    re.compile(r"\bque\s+mas\s+(tienes?|puedes?|hay|conoces?|sabes?)\b"),
    re.compile(r"\bsolo\s+(tienes?\s+)?(koha|ojs)\b"),
    re.compile(r"\b(cuantas?\s+fuentes?|cuantos?\s+repositorios?)\b"),
    re.compile(r"\bde\s+donde\s+(sacas?|obtienes?|viene[ns]?)\b"),
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

        # 2b. Meta-preguntas sobre capacidades/fuentes del asistente.
        # Largas pero conversacionales → GREETING (el path GREETING describe el
        # inventario de fuentes). No se aplica la regla del remainder.
        for pat in _META_CAPABILITY_PATTERNS:
            if pat.search(normalized):
                return self._decision(
                    IntentCategory.GREETING,
                    Tier.T0_FAST,
                    PrivacyLevel.CLOUD_OK,
                    t0,
                    f"meta_capability: {pat.pattern[:40]}",
                )

        # 3. Saludos / cortesía
        # Solo clasificar como GREETING puro si tras el saludo no hay una
        # pregunta sustantiva. Ejemplos:
        #   "hola"                              → GREETING
        #   "hola guia"                         → GREETING
        #   "hola guia tienes libros de X?"     → NO GREETING (cae a Gate 2/3)
        #   "quien eres?"                       → GREETING (meta-pregunta corta)
        for pat in _GREETING_PATTERNS:
            m = pat.match(normalized)
            if not m:
                continue
            remainder = normalized[m.end():].strip()
            remainder_clean = re.sub(r"[^\w\s]", "", remainder)
            remainder_words = [w for w in remainder_clean.split() if w not in {"guia", "asistente"}]
            # Si tras el saludo quedan ≥3 palabras significativas, hay una
            # pregunta real — dejar que Gate 2/3 la clasifiquen.
            if len(remainder_words) >= 3:
                return None
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
