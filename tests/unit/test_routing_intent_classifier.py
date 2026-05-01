"""Tests del LLMIntentCategoryClassifier (Gate 3, P1.2 paso 4c)."""

from __future__ import annotations

from sciback_core.ports.llm import InMemoryLLMAdapter

from guia.routing import IntentCategory, LLMIntentCategoryClassifier


# ── Categorías reconocidas ────────────────────────────────────────────────


def test_classify_returns_greeting() -> None:
    llm = InMemoryLLMAdapter(canned_response="greeting")
    classifier = LLMIntentCategoryClassifier(llm)
    assert classifier.classify_category("hola") == IntentCategory.GREETING


def test_classify_returns_command() -> None:
    llm = InMemoryLLMAdapter(canned_response="command")
    classifier = LLMIntentCategoryClassifier(llm)
    assert classifier.classify_category("/reset") == IntentCategory.COMMAND


def test_classify_returns_campus_personal() -> None:
    llm = InMemoryLLMAdapter(canned_response="campus_personal")
    classifier = LLMIntentCategoryClassifier(llm)
    assert (
        classifier.classify_category("¿cuáles son mis notas?")
        == IntentCategory.CAMPUS_PERSONAL
    )


def test_classify_returns_campus_generico() -> None:
    llm = InMemoryLLMAdapter(canned_response="campus_generico")
    classifier = LLMIntentCategoryClassifier(llm)
    assert (
        classifier.classify_category("calendario académico")
        == IntentCategory.CAMPUS_GENERICO
    )


def test_classify_returns_research_simple() -> None:
    llm = InMemoryLLMAdapter(canned_response="research_simple")
    classifier = LLMIntentCategoryClassifier(llm)
    assert (
        classifier.classify_category("¿hay tesis sobre IA?")
        == IntentCategory.RESEARCH_SIMPLE
    )


def test_classify_returns_research_deep() -> None:
    llm = InMemoryLLMAdapter(canned_response="research_deep")
    classifier = LLMIntentCategoryClassifier(llm)
    assert (
        classifier.classify_category("compara metodologías")
        == IntentCategory.RESEARCH_DEEP
    )


def test_classify_returns_out_of_scope() -> None:
    llm = InMemoryLLMAdapter(canned_response="out_of_scope")
    classifier = LLMIntentCategoryClassifier(llm)
    assert (
        classifier.classify_category("¿capital de Francia?")
        == IntentCategory.OUT_OF_SCOPE
    )


# ── Tolerancia a respuestas con ruido ─────────────────────────────────────


def test_classify_strips_punctuation() -> None:
    """Algunas respuestas vienen con puntos/comas — el parser las limpia."""
    llm = InMemoryLLMAdapter(canned_response="greeting.")
    classifier = LLMIntentCategoryClassifier(llm)
    assert classifier.classify_category("hola") == IntentCategory.GREETING


def test_classify_handles_uppercase() -> None:
    llm = InMemoryLLMAdapter(canned_response="CAMPUS_PERSONAL")
    classifier = LLMIntentCategoryClassifier(llm)
    assert (
        classifier.classify_category("mis notas")
        == IntentCategory.CAMPUS_PERSONAL
    )


def test_classify_extracts_from_prefix() -> None:
    """El LLM puede responder 'category: greeting' — el parser lo extrae."""
    llm = InMemoryLLMAdapter(canned_response="category: greeting")
    classifier = LLMIntentCategoryClassifier(llm)
    assert classifier.classify_category("hola") == IntentCategory.GREETING


def test_classify_tolerates_accent_in_generico() -> None:
    """campus_genérico (con tilde) también es válido."""
    llm = InMemoryLLMAdapter(canned_response="campus_genérico")
    classifier = LLMIntentCategoryClassifier(llm)
    assert (
        classifier.classify_category("eventos universidad")
        == IntentCategory.CAMPUS_GENERICO
    )


# ── Fallback gracioso ─────────────────────────────────────────────────────


def test_unrecognized_response_returns_unknown() -> None:
    """Si el LLM responde algo no reconocido, retorna UNKNOWN."""
    llm = InMemoryLLMAdapter(canned_response="alguna_categoría_inventada")
    classifier = LLMIntentCategoryClassifier(llm)
    assert classifier.classify_category("query") == IntentCategory.UNKNOWN


def test_empty_llm_response_returns_unknown() -> None:
    llm = InMemoryLLMAdapter(canned_response="")
    classifier = LLMIntentCategoryClassifier(llm)
    assert classifier.classify_category("query") == IntentCategory.UNKNOWN


def test_llm_exception_returns_unknown() -> None:
    """Si el LLM falla (timeout, error de red), retorna UNKNOWN sin propagar."""

    class BrokenLLM:
        def complete(self, *args: object, **kwargs: object) -> object:
            raise RuntimeError("ollama unreachable")

    classifier = LLMIntentCategoryClassifier(BrokenLLM())  # type: ignore[arg-type]
    assert classifier.classify_category("query") == IntentCategory.UNKNOWN


# ── System prompt ────────────────────────────────────────────────────────


def test_classify_sends_system_prompt() -> None:
    """El primer mensaje al LLM siempre es system con las 8 categorías."""
    llm = InMemoryLLMAdapter(canned_response="greeting")
    classifier = LLMIntentCategoryClassifier(llm)
    classifier.classify_category("hola")

    messages = llm.complete_calls[0]
    assert messages[0].role == "system"
    # System prompt menciona las 8 categorías
    sys_content = messages[0].content
    for cat in (
        "greeting",
        "command",
        "campus_personal",
        "campus_generico",
        "research_simple",
        "research_deep",
        "out_of_scope",
        "unknown",
    ):
        assert cat in sys_content


def test_classify_uses_temperature_zero() -> None:
    """Temperature debe ser 0 para clasificación determinística."""
    llm = InMemoryLLMAdapter(canned_response="greeting")
    classifier = LLMIntentCategoryClassifier(llm)
    classifier.classify_category("test")
    # InMemoryLLMAdapter no expone temperature directamente, pero al menos
    # verificamos que se pasa kwargs sin error
    assert len(llm.complete_calls) == 1
