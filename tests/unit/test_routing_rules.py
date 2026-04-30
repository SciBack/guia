"""Tests del RuleBasedRouter (Gate 1, P1.2 paso 2)."""

from __future__ import annotations

import pytest

from guia.routing import Gate, IntentCategory, PrivacyLevel, Tier
from guia.routing.rules import RuleBasedRouter


@pytest.fixture
def router() -> RuleBasedRouter:
    return RuleBasedRouter()


# ── Saludos / cortesía → GREETING + T0_FAST + CLOUD_OK ────────────────────


@pytest.mark.parametrize(
    "query",
    [
        "hola",
        "Hola!",
        "Buenos días",
        "BUENAS NOCHES",
        "buenas tardes",
        "gracias",
        "Muchas gracias!",
        "adiós",
        "hasta luego",
        "ok",
        "perfecto.",
        "entendido",
        "sí, gracias",
        "no, gracias",
        "¿cómo estás?",
        "qué tal",
        "¿qué eres tú?",
        "¿qué puedes hacer?",
        "¿en qué me puedes ayudar?",
    ],
)
def test_greetings_match_gate1(router: RuleBasedRouter, query: str) -> None:
    d = router.decide(query)
    assert d is not None, f"saludo no detectado: {query!r}"
    assert d.intent == IntentCategory.GREETING
    assert d.tier == Tier.T0_FAST
    assert d.privacy == PrivacyLevel.CLOUD_OK
    assert d.gate_used == Gate.RULES
    assert d.confidence == 1.0


# ── Campus personal → CAMPUS_PERSONAL + ALWAYS_LOCAL (no se negocia) ──────


@pytest.mark.parametrize(
    "query",
    [
        "¿cuáles son mis notas del semestre?",
        "muéstrame mis calificaciones",
        "¿cuál es mi promedio ponderado?",
        "¿cuánto debo en biblioteca?",
        "¿tengo deuda pendiente?",
        "mi estado de cuenta",
        "¿cuál es mi saldo?",
        "mis libros prestados",
        "¿tengo libros vencidos?",
        "préstamos vencidos",
        "mis cursos matriculados",
        "mi horario de esta semana",
        "mi carga académica",
        "¿cuántos créditos me faltan para graduarme?",
        "mi perfil institucional",
        "mi correo institucional",
        "mi contraseña institucional",
    ],
)
def test_campus_personal_forces_local(router: RuleBasedRouter, query: str) -> None:
    d = router.decide(query)
    assert d is not None, f"campus_personal no detectado: {query!r}"
    assert d.intent == IntentCategory.CAMPUS_PERSONAL
    assert d.privacy == PrivacyLevel.ALWAYS_LOCAL, f"DEBE forzar local: {query!r}"
    assert d.tier == Tier.T1_STD
    assert d.gate_used == Gate.RULES


# ── Comandos directos ─────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "query",
    [
        "/help",
        "/reset",
        "/lang es",
        "/clear",
    ],
)
def test_commands_match_gate1(router: RuleBasedRouter, query: str) -> None:
    d = router.decide(query)
    assert d is not None
    assert d.intent == IntentCategory.COMMAND
    assert d.tier == Tier.T0_FAST


# ── Queries que NO deben matchear (Gate 1 retorna None) ───────────────────


@pytest.mark.parametrize(
    "query",
    [
        "busca tesis sobre machine learning",
        "¿hay artículos de educación virtual en OJS?",
        "explícame el reglamento de investigación",
        "compara metodologías de tesis sobre IA",
        "¿qué dice el calendario académico para mayo?",  # campus_generico, Gate 2
        "¿está disponible Cálculo de Stewart?",  # research_simple
    ],
)
def test_non_trivial_queries_pass_through(router: RuleBasedRouter, query: str) -> None:
    """Queries que requieren análisis semántico no deben matchear Gate 1."""
    d = router.decide(query)
    assert d is None, f"Gate 1 NO debería decidir esto: {query!r} → {d}"


# ── Edge cases ────────────────────────────────────────────────────────────


def test_normalization_handles_accents(router: RuleBasedRouter) -> None:
    """Acentos no afectan el matching."""
    d_with = router.decide("¿Cuáles son mis notas?")
    d_without = router.decide("cuales son mis notas")
    assert d_with is not None and d_without is not None
    assert d_with.intent == d_without.intent == IntentCategory.CAMPUS_PERSONAL


def test_normalization_handles_extra_whitespace(router: RuleBasedRouter) -> None:
    """Espacios extra colapsados."""
    d = router.decide("   buenos    días   ")
    assert d is not None
    assert d.intent == IntentCategory.GREETING


def test_priority_command_over_text(router: RuleBasedRouter) -> None:
    """Si una query empieza con /, se trata como comando aunque contenga texto."""
    d = router.decide("/help mis notas")
    assert d is not None
    assert d.intent == IntentCategory.COMMAND


def test_priority_campus_personal_over_greeting(router: RuleBasedRouter) -> None:
    """Si una query mezcla saludo + campus_personal, gana campus_personal (más restrictivo)."""
    d = router.decide("hola, ¿cuál es mi promedio?")
    assert d is not None
    # El primer pattern que matchea gana — pero los patterns de campus_personal
    # están priorizados explícitamente sobre los de greeting en el orden del router.
    assert d.intent == IntentCategory.CAMPUS_PERSONAL
    assert d.privacy == PrivacyLevel.ALWAYS_LOCAL


def test_latency_under_1ms_typical(router: RuleBasedRouter) -> None:
    """Gate 1 debe ser <1ms para queries típicas."""
    d = router.decide("hola")
    assert d is not None
    assert d.latency_ms < 5.0  # margen amplio para CI lentos


def test_empty_string_returns_none(router: RuleBasedRouter) -> None:
    """Query vacía no matchea."""
    assert router.decide("") is None
    assert router.decide("   ") is None
