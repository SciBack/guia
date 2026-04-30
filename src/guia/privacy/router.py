"""PrivacyRouter — combina niveles de fuentes + PII para decidir privacidad (P2.2).

Algoritmo MAX-LEVEL-WINS (ADR-036, sección "Política correcta"):

    final = MAX(
        level_query,    # PII detectada en la query
        level_sources,  # MAX(level por cada source en sources_used)
        level_docs,     # PII detectada en los docs recuperados
    )

Si final >= L2_PERSONAL → force_local=True. El LLM debe ser local; ningún
proveedor cloud (Claude, OpenAI, DeepSeek) recibe datos L2 o superiores,
sin excepción.

Detección PII rápida (sin LLM) usando regex peruanos:
- DNI: 8 dígitos
- Código estudiante: 8-9 dígitos contiguos
- Email institucional (@upeu.edu.pe, otros .edu.pe)

Para PII más sofisticada (NER multilingüe, nombres de personas) ver P2.3.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from guia.privacy.levels import DataLevel
from guia.privacy.registry import max_level_for_sources


# ── Patrones PII rápidos (sin LLM) ────────────────────────────────────────

# DNI peruano: 8 dígitos exactos, no precedido/seguido por dígitos
_DNI_RE = re.compile(r"(?<!\d)\d{8}(?!\d)")

# Email institucional .edu.pe (universidad peruana)
_EMAIL_INST_RE = re.compile(r"\b[\w.+-]+@[\w-]+\.edu\.pe\b", re.IGNORECASE)

# Posesivos personales (señal de que la query es L2_PERSONAL aunque no haya
# una identificación explícita: 'mis notas', 'mi deuda', 'mi promedio')
_PERSONAL_POSSESSIVES_RE = re.compile(
    r"\b(mis?|mi|mi\s+propi[ao])\s+(nota|notas|calificacion|calificaciones|"
    r"promedio|deuda|saldo|cuenta|prestamo|prestamos|libros|matricula|"
    r"horario|credito|creditos|expediente|historia|perfil|password|contrasena)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class PrivacyVerdict:
    """Resultado de la evaluación de privacidad de una query (ADR-036)."""

    final_level: DataLevel
    """MAX(level_query, level_sources, level_docs)."""

    force_local: bool
    """True si final_level >= L2_PERSONAL: el LLM debe ser local."""

    pii_in_query: bool = False
    """True si se detectó DNI / email institucional / posesivos personales."""

    pii_in_docs: bool = False
    """True si se detectó PII en el contexto recuperado."""

    level_query: DataLevel = DataLevel.L0_PUBLIC
    level_sources: DataLevel = DataLevel.L0_PUBLIC
    level_docs: DataLevel = DataLevel.L0_PUBLIC

    reason: str = ""
    """Texto breve para audit log y debug."""


def _detect_pii(text: str) -> tuple[bool, list[str]]:
    """Detecta PII en un texto. Retorna (has_pii, lista de patrones matched)."""
    matches: list[str] = []
    if _DNI_RE.search(text):
        matches.append("dni")
    if _EMAIL_INST_RE.search(text):
        matches.append("email_inst")
    if _PERSONAL_POSSESSIVES_RE.search(text):
        matches.append("personal_possessive")
    return bool(matches), matches


class PrivacyRouter:
    """Evalúa la política de privacidad de una query.

    Stateless. Latencia <1ms (regex sobre query corta + tabla lookup).
    """

    def evaluate(
        self,
        query: str,
        sources_used: list[str],
        retrieved_docs_text: str = "",
    ) -> PrivacyVerdict:
        """Calcula el final_level y force_local.

        Args:
            query: Texto del usuario.
            sources_used: Lista de fuentes a consultar/consultadas (e.g. ['dspace','koha-loans']).
            retrieved_docs_text: Texto concatenado de los docs recuperados (para PII).

        Returns:
            PrivacyVerdict con la decisión final.
        """
        # 1. Nivel por sources tocadas
        level_sources = max_level_for_sources(sources_used)

        # 2. Nivel por PII en query
        pii_query, query_matches = _detect_pii(query)
        level_query = DataLevel.L2_PERSONAL if pii_query else DataLevel.L0_PUBLIC

        # 3. Nivel por PII en docs (más limitado: solo DNI/email)
        pii_docs = False
        level_docs = DataLevel.L0_PUBLIC
        if retrieved_docs_text:
            if _DNI_RE.search(retrieved_docs_text) or _EMAIL_INST_RE.search(
                retrieved_docs_text
            ):
                pii_docs = True
                level_docs = DataLevel.L2_PERSONAL

        # 4. MAX-LEVEL-WINS
        final = max(level_query, level_sources, level_docs)
        force_local = final >= DataLevel.L2_PERSONAL

        # 5. Reason para audit
        reason_parts = [f"sources:{level_sources.name}"]
        if pii_query:
            reason_parts.append(f"pii_query:{','.join(query_matches)}")
        if pii_docs:
            reason_parts.append("pii_docs")
        reason_parts.append(f"final:{final.name}")

        return PrivacyVerdict(
            final_level=final,
            force_local=force_local,
            pii_in_query=pii_query,
            pii_in_docs=pii_docs,
            level_query=level_query,
            level_sources=level_sources,
            level_docs=level_docs,
            reason=" / ".join(reason_parts),
        )
