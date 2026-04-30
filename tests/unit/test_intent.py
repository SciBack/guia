"""Tests del IntentClassifier."""

from __future__ import annotations

from sciback_core.ports.llm import InMemoryLLMAdapter

from guia.domain.chat import Intent
from guia.services.intent import IntentClassifier


def test_classify_research_intent() -> None:
    """Clasifica correctamente intent de investigación."""
    llm = InMemoryLLMAdapter(canned_response="research")
    classifier = IntentClassifier(llm)
    intent = classifier.classify_sync("¿Qué tesis hay sobre machine learning?")
    assert intent == Intent.RESEARCH


def test_classify_campus_intent() -> None:
    """Clasifica correctamente intent de campus."""
    llm = InMemoryLLMAdapter(canned_response="campus")
    classifier = IntentClassifier(llm)
    intent = classifier.classify_sync("¿Tengo alguna deuda en biblioteca?")
    assert intent == Intent.CAMPUS


def test_classify_general_intent() -> None:
    """Clasifica correctamente intent general."""
    llm = InMemoryLLMAdapter(canned_response="general")
    classifier = IntentClassifier(llm)
    intent = classifier.classify_sync("¿Dónde está el comedor universitario?")
    assert intent == Intent.GENERAL


def test_classify_out_of_scope() -> None:
    """Clasifica correctamente intent fuera de alcance."""
    llm = InMemoryLLMAdapter(canned_response="out_of_scope")
    classifier = IntentClassifier(llm)
    intent = classifier.classify_sync("¿Cuál es la capital de Francia?")
    assert intent == Intent.OUT_OF_SCOPE


def test_classify_unknown_response_defaults_to_general() -> None:
    """Si el LLM responde algo inesperado, el default es GENERAL."""
    llm = InMemoryLLMAdapter(canned_response="no_se_qué")
    classifier = IntentClassifier(llm)
    intent = classifier.classify_sync("query cualquiera")
    assert intent == Intent.GENERAL


def test_classify_strips_punctuation() -> None:
    """El classifier limpia puntuación de la respuesta del LLM."""
    llm = InMemoryLLMAdapter(canned_response="research.")
    classifier = IntentClassifier(llm)
    intent = classifier.classify_sync("¿Hay publicaciones sobre DSpace?")
    assert intent == Intent.RESEARCH


def test_classify_calls_llm_once() -> None:
    """Verifica que se realiza exactamente 1 llamada al LLM por clasificación."""
    llm = InMemoryLLMAdapter(canned_response="general")
    classifier = IntentClassifier(llm)
    classifier.classify_sync("test query")
    assert len(llm.complete_calls) == 1


def test_classify_sends_system_prompt() -> None:
    """El primer mensaje siempre es un system prompt."""
    llm = InMemoryLLMAdapter(canned_response="research")
    classifier = IntentClassifier(llm)
    classifier.classify_sync("consulta de prueba")
    messages = llm.complete_calls[0]
    assert messages[0].role == "system"
    assert "research" in messages[0].content.lower()
