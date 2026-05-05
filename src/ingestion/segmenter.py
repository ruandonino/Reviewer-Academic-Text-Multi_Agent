import re
from typing import List, Optional
from src.models.section import Section
from src.utils.logger import get_logger

logger = get_logger()

# Mapa de seções canônicas de acordo com o padrão estabelecido (C no Algoritmo 2)
CANONICAL_SECTIONS = [
    "título", "resumo", "introdução", "referencial teórico", 
    "revisão da literatura", "metodologia", 
    "resultados", "discussão e conclusão", "referências"
]

def normalizar_texto(texto: str) -> str:
    """Normaliza o texto para facilitar o mapeamento."""
    return texto.strip().lower()

import Levenshtein

def mapear_para_secao_canonica(header: str, threshold: float = 0.8) -> Optional[str]:
    """
    Mapeia um título de seção Markdown para uma categoria canônica usando busca exata e fuzzy matching.
    """
    header_clean = normalizar_texto(re.sub(r'^#+\s*', '', header))
    
    # 1. Tentativa de busca exata ou por palavra-chave (Alta prioridade)
    for section_type in CANONICAL_SECTIONS:
        if section_type in header_clean:
            return section_type
            
    # Heurísticas para Desenvolvimento, Materiais e Métodos -> Metodologia
    if "desenvolvimento" in header_clean or "materiais e métodos" in header_clean or "materiais e metodos" in header_clean:
        return "metodologia"
        
    # Heurísticas para Discussão e Conclusão -> Discussão e Conclusão
    if "discuss" in header_clean or "conclus" in header_clean:
        return "discussão e conclusão"

    # 2. Fuzzy matching (90% similaridade)
    # Remove números de seções (ex: "1. Introdução" -> "Introdução") para melhorar o match
    header_only_text = re.sub(r'^[\d\.]+\s*', '', header_clean).strip()
    
    for section_type in CANONICAL_SECTIONS:
        similarity = Levenshtein.ratio(header_only_text, section_type)
        if similarity >= threshold:
            logger.info(f"Fuzzy match detectado: '{header_only_text}' -> '{section_type}' ({similarity:.2%})")
            return section_type

    # 3. Heurísticas adicionais
    if "referência" in header_clean or "bibliografia" in header_clean or "trabalhos relacionados" in header_clean:
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

    for i, match in enumerate(matches):
        # match.group(2) é o texto do heading #, match.group(3) é o texto do negrito **
        header_text = match.group(2) if match.group(2) else match.group(3)
        start_pos = match.start()
        
        # O fim do conteúdo é o início do próximo cabeçalho ou o fim do arquivo
        end_pos = matches[i+1].start() if i + 1 < len(matches) else len(markdown_text)
        
        conteudo = markdown_text[start_pos:end_pos].strip()
        tipo_canonica = mapear_para_secao_canonica(header_text)
        
        if tipo_canonica:
            secao_ativa_tipo = tipo_canonica
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
                logger.debug(f"Subseção sem pai '{header_text}' criada como fallback 'título'.")
            
    logger.info(f"Segmentação concluída. {len(secoes)} seções canônicas extraídas.")
    return secoes
