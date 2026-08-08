import re
import unicodedata


SECTION_KEY_MAPPING = {
    "titulo": "titulo",
    "title": "titulo",
    "resumo": "resumo",
    "abstract": "resumo",
    "introducao": "introducao",
    "introduction": "introducao",
    "referencial teorico": "revisao_bibliografica",
    "revisao da literatura": "revisao_bibliografica",
    "revisao bibliografica": "revisao_bibliografica",
    "background": "revisao_bibliografica",
    "related work": "revisao_bibliografica",
    "metodologia": "metodologia",
    "desenvolvimento": "metodologia",
    "methodology": "metodologia",
    "development": "metodologia",
    "design": "metodologia",
    "resultados": "resultados",
    "results": "resultados",
    "discussao e conclusao": "conclusao",
    "discussao": "conclusao",
    "discussion": "conclusao",
    "conclusao": "conclusao",
    "conclusion": "conclusao",
    "consideracoes finais": "conclusao",
    "referencias": "referencias",
    "references": "referencias",
}


def normalize_section_label(label: str) -> str:
    """Normaliza títulos de seção para comparações independentes de grafia."""
    normalized = unicodedata.normalize("NFKD", label or "")
    normalized = "".join(char for char in normalized if not unicodedata.combining(char))
    normalized = normalized.lower()
    normalized = re.sub(r"^\s*\d+(?:\.\d+)*\.?\s*", "", normalized)
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip()


def resolve_section_key(label: str) -> str | None:
    """Retorna a chave canônica do relatório para um título ou tipo de seção."""
    normalized = normalize_section_label(label)

    # Composite headings such as "Resultados (Discussão e Conclusão)" must
    # retain the conclusion classification instead of matching "resultados"
    # first during the generic alias scan below.
    if "discussao e conclusao" in normalized or "conclusao" in normalized:
        return "conclusao"

    if normalized in SECTION_KEY_MAPPING:
        return SECTION_KEY_MAPPING[normalized]

    for alias, section_key in SECTION_KEY_MAPPING.items():
        if re.search(rf"(?<!\w){re.escape(alias)}(?!\w)", normalized):
            return section_key

    return None
