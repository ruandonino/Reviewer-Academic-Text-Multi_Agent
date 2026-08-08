import re
from typing import List, Optional
from src.models.section import Section
from src.utils.logger import get_logger

logger = get_logger()

# Mapa de seções canônicas de acordo com o padrão estabelecido (C no Algoritmo 2)
CANONICAL_SECTIONS = [
    "título", "resumo", "introdução", "revisão bibliográfica", "metodologia", 
    "resultados", "discussão e conclusão", "referências"
]

def normalizar_texto(texto: str) -> str:
    """Normaliza o texto para facilitar o mapeamento."""
    return texto.strip().lower()

import Levenshtein

def mapear_para_secao_canonica(header: str, threshold: float = 0.8, is_first_header: bool = False, doc_title: str = "") -> Optional[str]:
    """
    Mapeia um título de seção Markdown para uma categoria canônica usando busca exata e fuzzy matching.
    """
    header_clean = normalizar_texto(re.sub(r'^#+\s*', '', header))
    
    if doc_title:
        # Se for o título do documento, não mapeia para nenhuma seção
        if Levenshtein.ratio(header_clean, doc_title) >= 0.85 or doc_title in header_clean or header_clean in doc_title:
            return None

    # Heurística de profundidade de numeração:
    # Se o cabeçalho começar com uma numeração de 3 ou mais níveis (ex: 3.4.3 ou 1.2.3.4),
    # consideramo-lo uma subseção profunda e NÃO mapeamos para uma seção canônica.
    numbering_match = re.match(r'^([\d\.]+)', header_clean)
    if numbering_match:
        num_str = numbering_match.group(1).strip('.')
        parts = [p for p in num_str.split('.') if p]
        if len(parts) >= 3:
            return None
    
    # 1. Verificações de alta prioridade para evitar conflitos (ex: "discussão dos resultados" -> discussão, não resultados)
    # "Considerações iniciais" é uma seção introdutória, NÃO uma conclusão — excluída explicitamente.
    if "considerações iniciais" in header_clean or "consideracoes iniciais" in header_clean:
        return None

    # A heading such as "Resultados e Discussão" begins the results section;
    # its discussion component must not merge it with the later conclusion.
    if "resultado" in header_clean and "conclus" not in header_clean:
        return "resultados"

    if "discuss" in header_clean or "conclus" in header_clean or "considerações" in header_clean or "consideracoes" in header_clean:
        if "discussão dos resultados" in header_clean:
            return "resultados"
        if "considerações" in header_clean or "consideracoes" in header_clean:
            return "considerações finais"
        return "discussão e conclusão"

    # Heurísticas para Desenvolvimento, Materiais e Métodos -> Metodologia
    if ("desenvolvimento" in header_clean or "materiais e métodos" in header_clean or
            "materiais e metodos" in header_clean or "design" in header_clean or
            "development" in header_clean or
            "estratégias de desenvolvimento" in header_clean or
            "estrategias de desenvolvimento" in header_clean or
            ("materiais" in header_clean and "métodos" in header_clean) or
            ("materiais" in header_clean and "metodos" in header_clean)):
        return "metodologia"

    # English exact match mapping
    english_mapping = {
        "abstract": "resumo",
        "introduction": "introdução",
        "background": "revisão bibliográfica",
        "related work": "revisão bibliográfica",
        "methodology": "metodologia",
        "results": "resultados",
        "conclusion": "discussão e conclusão",
        "references": "referências"
    }
    for eng_key, pt_val in english_mapping.items():
        if eng_key in header_clean:
            return pt_val
            
    # 2. Tentativa de busca por palavra-chave canônica
    # Para evitar falsos positivos em títulos longos contendo palavras genéricas,
    # exigimos que a palavra-chave corresponda apenas se o cabeçalho for curto (<= 4 palavras após remover números).
    header_only_text = re.sub(r'^[\d\.]+\s*', '', header_clean).strip()
    words_count = len(header_only_text.split())

    if words_count <= 4:
        # Busca exata para variações de revisão bibliográfica / referencial teórico
        if "referencial teórico" in header_clean or "referencial teorico" in header_clean or \
           "revisão da literatura" in header_clean or "revisao da literatura" in header_clean or \
           "revisão bibliográfica" in header_clean or "revisao bibliografica" in header_clean or \
           "fundamentação teórica" in header_clean or "fundamentacao teorica" in header_clean:
            return "revisão bibliográfica"
            
        for section_type in CANONICAL_SECTIONS:
            # Para "referências", fazemos busca exata de palavra
            if section_type == "referências" and "referência" in header_clean:
                return "referências"
            if section_type in header_clean:
                return section_type

    # Heurísticas para Resultados, Avaliação, Experimentos, Validação -> Resultados
    # Só mapeamos se o título contiver estas palavras E for um cabeçalho curto
    if words_count <= 4:
        if "resultado" in header_clean or "avaliação" in header_clean or "avaliacao" in header_clean or "experimento" in header_clean or "validação" in header_clean or "validacao" in header_clean or "teste" in header_clean:
            if is_first_header and ("avalia" in header_clean):
                pass
            else:
                return "resultados"
        
    # 3. Fuzzy matching (90% similaridade) no texto sem numeração
    for section_type in CANONICAL_SECTIONS:
        similarity = Levenshtein.ratio(header_only_text, section_type)
        if similarity >= threshold:
            logger.info(f"Fuzzy match detectado: '{header_only_text}' -> '{section_type}' ({similarity:.2%})")
            return section_type

    # 4. Outras heurísticas
    if "trabalhos relacionados" in header_clean:
        return "revisão bibliográfica"
    if "referência" in header_clean or "bibliografia" in header_clean:
        return "referências"
    
    return None

def segmentar_secoes(markdown_text: str) -> List[Section]:
    """
    Segmenta o documento Markdown em seções (RF01 - Algoritmo 2)
    Melhorado para não perder texto de subseções e capturar o título inicial.
    """
    if not markdown_text:
        return []
        
    logger.info("Iniciando segmentação do documento Markdown.")
    
    # Extrair título do documento (primeira linha não-vazia)
    non_empty_lines = [line.strip() for line in markdown_text.split('\n') if line.strip()]
    doc_title = normalizar_texto(non_empty_lines[0]) if non_empty_lines else ""
    
    # Extrair cabeçalhos (Níveis 1 a 3 ou texto em negrito sozinho na linha)
    header_pattern = re.compile(r'^(#{1,3})\s+(.+)$|^\*\*(.+)\*\*$', re.MULTILINE)
    
    matches = list(header_pattern.finditer(markdown_text))
    secoes: List[Section] = []
    
    # Tratamento para o texto ANTES do primeiro cabeçalho (geralmente Título, Resumo inicial, etc.)
    if matches and matches[0].start() > 0:
        texto_inicial = markdown_text[0:matches[0].start()].strip()
        if texto_inicial:
            # Assumimos que o primeiro texto solto pertence ao "título" se não houver mapeamento melhor
            s_inicial = Section(type="título", text=texto_inicial, position=1)
            secoes.append(s_inicial)
            logger.debug("Seção inicial detectada antes do primeiro cabeçalho (mapeada para 'título').")
    elif not matches:
        # Se não há cabeçalhos no documento inteiro, retornamos o documento todo como título
        secoes.append(Section(type="título", text=markdown_text.strip(), position=1))
        return secoes

    secao_ativa_tipo = "título" if (matches and matches[0].start() > 0) else None
    secao_ativa_nivel = 0      # markdown heading level (# count) of the active canonical section
    secao_ativa_num_depth = 0  # numeric prefix depth of the active canonical section
    secao_ativa_root = None    # first integer of the numeric prefix (e.g. "4.7" -> "4")

    def _num_info(header_raw: str):
        """Return (depth, root) where depth = number of numeric parts, root = first part (str) or None."""
        clean = normalizar_texto(re.sub(r'^#+\s*', '', header_raw))
        m = re.match(r'^([\d\.]+)', clean)
        if m:
            parts = [p for p in m.group(1).strip('.').split('.') if p]
            return len(parts), parts[0] if parts else None
        return 0, None

    for i, match in enumerate(matches):
        # match.group(1) = '#' chars, match.group(2) = heading text, match.group(3) = **bold** text
        header_text = match.group(2) if match.group(2) else match.group(3)

        # Determine heading depth (bold text treated as deepest sub-level)
        nivel_atual = len(match.group(1)) if match.group(1) else 4
        num_depth_atual, num_root_atual = _num_info(header_text)

        start_pos = match.start()
        
        # O fim do conteúdo é o início do próximo cabeçalho ou o fim do arquivo
        end_pos = matches[i+1].start() if i + 1 < len(matches) else len(markdown_text)
        
        conteudo = markdown_text[start_pos:end_pos].strip()
        tipo_canonica = mapear_para_secao_canonica(header_text, is_first_header=(i == 0), doc_title=doc_title)

        # ── Subsection guard ────────────────────────────────────────────────
        # Brazilian TCC documents often use ## for EVERY heading, so markdown
        # level comparison alone is insufficient.  We use two complementary
        # heuristics:
        #
        # 1. deeper_by_level: the heading has more # chars than the one that
        #    opened the current canonical section.
        #
        # 2. same_chapter_root: the heading shares the SAME first integer as
        #    the one that opened the current canonical section, AND has a deeper
        #    numeric prefix.  Example:
        #      Active: "4 DESENVOLVIMENTO"  root="4" depth=1
        #      Incoming: "4.7 Considerações Finais"  root="4" depth=2
        #    → same root "4", deeper depth → it is a SUBSECTION of chapter 4,
        #      not a new canonical section.
        #
        # Note: a heading with a DIFFERENT root (e.g. "6 CONCLUSÕES", root="6")
        # is always treated as a potential new canonical section.
        if tipo_canonica and secao_ativa_nivel > 0 and secao_ativa_tipo != "título" and tipo_canonica != "considerações finais":
            deeper_by_level = nivel_atual > secao_ativa_nivel

            same_chapter_root = (
                num_root_atual is not None and
                secao_ativa_root is not None and
                num_root_atual == secao_ativa_root and
                num_depth_atual >= 2 and
                nivel_atual >= secao_ativa_nivel
            )

            if deeper_by_level or same_chapter_root:
                logger.debug(
                    f"Subseção '{header_text}' (nível={nivel_atual}, depth={num_depth_atual}, root={num_root_atual}) "
                    f"ignorada como canônica — seção ativa '{secao_ativa_tipo}' "
                    f"(nível={secao_ativa_nivel}, depth={secao_ativa_num_depth}, root={secao_ativa_root})."
                )
                tipo_canonica = None
        # ────────────────────────────────────────────────────────────────────

        if tipo_canonica:
            secao_ativa_tipo = tipo_canonica
            secao_ativa_nivel = nivel_atual
            secao_ativa_num_depth = num_depth_atual
            secao_ativa_root = num_root_atual
            existing_section = next((s for s in secoes if s.type == tipo_canonica), None)
            if existing_section:
                existing_section.text += "\n\n" + conteudo
                logger.debug(f"Seção anexada à existente: {tipo_canonica} (Posição Original {i+1})")
            else:
                s_j = Section(
                    type=tipo_canonica,
                    text=conteudo,
                    position=len(secoes) + 1
                )
                secoes.append(s_j)
                logger.debug(f"Seção detectada: {tipo_canonica} (Posição {i+1})")
        else:
            # Se não é canônica, anexa à última seção ativa
            if secao_ativa_tipo:
                existing_section = next((s for s in secoes if s.type == secao_ativa_tipo), None)
                if existing_section:
                    existing_section.text += "\n\n" + conteudo
                    logger.debug(f"Subseção '{header_text}' não-canônica anexada à seção ativa: {secao_ativa_tipo}")
            else:
                # Se não temos seção ativa ainda, cria uma como "título" fallback
                s_fallback = Section(type="título", text=conteudo, position=len(secoes) + 1)
                secoes.append(s_fallback)
                secao_ativa_tipo = "título"
                secao_ativa_nivel = nivel_atual
                secao_ativa_num_depth = num_depth_atual
                secao_ativa_root = num_root_atual
                logger.debug(f"Subseção sem pai '{header_text}' criada como fallback 'título'.")
            
    logger.info(f"Segmentação concluída. {len(secoes)} seções canônicas extraídas.")
    return secoes
