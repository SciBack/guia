"""Tests de LanguageGate y ToxicityGate (ADR-045)."""
from __future__ import annotations

import pytest


class TestLanguageGate:
    def test_español_pasa(self) -> None:
        from guia.routing.gates import LanguageGate
        gate = LanguageGate(enabled=True)
        result = gate.evaluate("¿Qué libros de matemáticas tienen?")
        assert result.passed

    def test_disabled_siempre_pasa(self) -> None:
        from guia.routing.gates import LanguageGate
        gate = LanguageGate(enabled=False)
        result = gate.evaluate("anything in any language 日本語")
        assert result.passed
        assert result.user_message is None

    def test_query_vacia_pasa(self) -> None:
        from guia.routing.gates import LanguageGate
        gate = LanguageGate(enabled=True)
        result = gate.evaluate("")
        assert result.passed


class TestToxicityGate:
    def test_query_normal_pasa(self) -> None:
        from guia.routing.gates import ToxicityGate
        gate = ToxicityGate(enabled=True, threshold=0.85)
        result = gate.evaluate("busco tesis sobre inteligencia artificial")
        assert result.passed

    def test_disabled_siempre_pasa(self) -> None:
        from guia.routing.gates import ToxicityGate
        gate = ToxicityGate(enabled=False, threshold=0.5)
        result = gate.evaluate("cualquier texto")
        assert result.passed
        assert result.reason is None

    def test_threshold_muy_alto_pasa_todo(self) -> None:
        from guia.routing.gates import ToxicityGate
        gate = ToxicityGate(enabled=True, threshold=0.9999)
        result = gate.evaluate("consulta académica normal")
        assert result.passed

    def test_query_vacia_pasa(self) -> None:
        from guia.routing.gates import ToxicityGate
        gate = ToxicityGate(enabled=True)
        result = gate.evaluate("")
        assert result.passed

    def test_gate_bloqueado_tiene_mensaje(self) -> None:
        from guia.routing.gates import ToxicityGate
        gate = ToxicityGate(enabled=True, threshold=0.0)
        gate._predict = lambda q: 1.0  # type: ignore[method-assign]
        result = gate.evaluate("cualquier texto")
        assert not result.passed
        assert result.user_message is not None
        msg = (result.user_message or "").lower()
        assert "gob.pe/iaperu" in msg or "reformula" in msg
