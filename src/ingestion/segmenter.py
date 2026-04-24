import re
from typing import List, Optional
from src.models.section import Section
from src.utils.logger import get_logger

logger = get_logger()

# Mapa de seções canônicas de acordo com o padrão estabelecido (C no Algoritmo 2)
CANONICAL_SECTIONS = [
    "título", "resumo", "abstract", "introdução", "referencial teórico", 
    "revisão da literatura", "metodologia", "desenvolvimento", 
    "resultados", "discussão", "conclusão", "considerações finais", "referências"
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
            
    # 2. Fuzzy matching (90% similaridade)
    # Remove números de seções (ex: "1. Introdução" -> "Introdução") para melhorar o match
    header_only_text = re.sub(r'^[\d\.]+\s*', '', header_clean).strip()
    
    for section_type in CANONICAL_SECTIONS:
        similarity = Levenshtein.ratio(header_only_text, section_type)
        if similarity >= threshold:
            logger.info(f"Fuzzy match detectado: '{header_only_text}' -> '{section_type}' ({similarity:.2%})")
            return section_type

    # 3. Heurísticas adicionais
    if "referência" in header_clean or "bibliografia" in header_clean:
        return "referências"
    
    return None

def segmentar_secoes(markdown_text: str) -> List[Section]:
    """
    Segmenta o documento Markdown em seções (RF01 - Algoritmo 2)
    """
    if not markdown_text:
        return []
        
    logger.info("Iniciando segmentação do documento Markdown.")
    
    # Extrair cabeçalhos (Níveis 1 e 2 geralmente)
    header_pattern = re.compile(r'^(#{1,2})\s+(.+)$', re.MULTILINE)
    
    matches = list(header_pattern.finditer(markdown_text))
    secoes: List[Section] = []
    
    for i, match in enumerate(matches):
        header_text = match.group(0)
        start_pos = match.start()
        
        # O fim do conteúdo é o início do próximo cabeçalho ou o fim do arquivo
        end_pos = matches[i+1].start() if i + 1 < len(matches) else len(markdown_text)
        
        conteudo = markdown_text[start_pos:end_pos].strip()
        tipo_canonica = mapear_para_secao_canonica(header_text)
        
        if tipo_canonica:
            s_j = Section(
                type=tipo_canonica,
                text=conteudo,
                position=i+1
            )
            secoes.append(s_j)
            logger.debug(f"Seção detectada: {tipo_canonica} (Posição {i+1})")
            
    logger.info(f"Segmentação concluída. {len(secoes)} seções canônicas extraídas.")
    return secoes
