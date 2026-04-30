"""PrivacyRouter — placeholder, implementación real en P2.2."""

from __future__ import annotations

from dataclasses import dataclass

from guia.privacy.levels import DataLevel


@dataclass(frozen=True)
class PrivacyVerdict:
    """Resultado de la evaluación de privacidad. Real en P2.2."""

    final_level: DataLevel
    """MAX(level_query, level_sources, level_docs)."""

    force_local: bool
    """True si final_level >= L2_PERSONAL: el LLM debe ser local."""

    pii_in_query: bool = False
    pii_in_docs: bool = False
    reason: str = ""


class PrivacyRouter:
    """Stub — implementación real en P2.2."""

    def evaluate(
        self,
        query: str,
        sources_used: list[str],
        retrieved_docs_text: str = "",
    ) -> PrivacyVerdict:
        from guia.privacy.registry import max_level_for_sources

        source_level = max_level_for_sources(sources_used)
        return PrivacyVerdict(
            final_level=source_level,
            force_local=source_level >= DataLevel.L2_PERSONAL,
            reason=f"sources_max:{source_level.name}",
        )
