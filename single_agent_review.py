import os
import sys
import asyncio
import re
import json
from dotenv import load_dotenv
import marko

# Configura o path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.ingestion.parsers import convert_pdf_to_markdown
from src.ingestion.segmenter import segmentar_secoes
from src.utils.llm_client import calculate_completion_cost, safe_completion
from src.config import settings
from src.utils.logger import get_logger
from src.utils.section_mapping import resolve_section_key

load_dotenv(override=True)
logger = get_logger()

# Vamos usar um modelo com boa janela de contexto, por padrão o mesmo do sintetizador
REVIEW_MODEL = settings.synthesizer_model

def review_entire_pdf(pdf_path: str, model_name: str = "gemini/gemini-2.5-flash-lite"):
    import time
    start_time = time.time()
    logger.info(f"Iniciando revisão de agente único para o arquivo: {pdf_path} com modelo: {model_name}")
    
    if not os.path.exists(pdf_path):
        logger.error(f"Arquivo {pdf_path} não encontrado.")
        return
        
    logger.info("Extraindo texto do PDF...")
    md_text = convert_pdf_to_markdown(pdf_path)
    
    if not md_text:
        logger.error("Falha ao extrair texto do documento.")
        return
        
    logger.info(f"Texto extraído com sucesso. Tamanho: {len(md_text)} caracteres.")
    
    # Segmenta as seções apenas para preencher o JSON formatado no final (o prompt recebe o texto inteiro)
    secoes = segmentar_secoes(md_text)
    
    prompt = f"""
Você é um revisor acadêmico experiente. Sua tarefa é ler o texto completo do trabalho acadêmico abaixo e fornecer uma revisão detalhada, crítica e estruturada.

## REGRAS DE OURO (LEIA ANTES DE COMEÇAR):
**RESTRIÇÃO:** NÃO aponte, mencione ou corrija erros de digitação, ortografia, acentuação, concordância ou gramática. O foco é estritamente no conteúdo.
**RESTRIÇÃO:** As seções da revisão gerada não serem (Título, Resumo, Introdução, Referêncial Teórico, Metodologia, Resultados, Conclusão e Referências.) será considerada uma falha grave na sua tarefa.

## Diretrizes da Revisão:
1. **Visão Geral:** Dê um parecer geral sobre o trabalho, destacando a relevância do tema, clareza da escrita e estrutura.
2. Revisões Detalhadas por Seção. Você DEVE obrigatoriamente incluir na sua análise as seguintes seções: Título, Resumo, Introdução, Referêncial Teórico, Metodologia, Resultados, Conclusão e Referências. Para cada observação, apresente explicitamente no formato de lista:
   - Problema (Issue)
   - Sugestão (Suggestion)
   - Tipo (Normativa (Relacionado a normas como APA e ABNT ou erros ortográficos) ou Semântica)
3. **Conclusão da Revisão:** Liste os pontos fortes e os pontos críticos que exigem maior atenção do autor.

# Relatório Final de Revisão Acadêmica

## 1. Visão Geral do Documento e Integração entre Seções
* **[Nome do Ponto]:** [Análise geral]

## 2. Revisões Detalhadas por Seção
[Dentro de cada seção, liste as observações estritamente neste formato:]
* **Problema:** [Explique o problema]
  **Sugestão:** [Explique a sugestão]
  **Tipo:** [Normativa ou Semântica]
[Repita a estrutura de marcadores acima para cada observação]

## 3. Conclusão da Revisão
[Escreva a conclusão do relatório]

## Texto do Trabalho Acadêmico:
{md_text}
"""

    logger.info(f"Enviando texto para o modelo {model_name} (isso pode demorar devido ao tamanho do texto)...")
    
    try:
        response = safe_completion(
            model=model_name,
            messages=[{"role": "user", "content": prompt}]
        )
        
        review_content = response.choices[0].message.content.strip()
        
        # Opcional: extrair custo
        tokens = response.usage.total_tokens if hasattr(response, 'usage') and response.usage else 0
        try:
            cost = calculate_completion_cost(response, model_name)
        except Exception:
            cost = 0.0
            
        logger.info(f"Revisão concluída! Tokens utilizados: {tokens}. Custo estimado: ${cost:.4f}")
        
        base_name = os.path.basename(pdf_path)
        name_without_ext = os.path.splitext(base_name)[0]
        safe_model_name = model_name.replace("/", "_")
        suffix = os.getenv("RUN_SUFFIX", "")
        
        # Salva o Markdown
        md_filename = f"review_{name_without_ext}_{safe_model_name}{suffix}.md"
        with open(md_filename, "w", encoding="utf-8") as f:
            f.write(review_content)
        logger.info(f"Relatório Markdown salvo em: {md_filename}")
        
        # Gera o HTML
        try:
            html_body = marko.convert(review_content)
            styled_html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Revisão de Agente Único - {name_without_ext} - {safe_model_name}</title>
    <style>
        body {{ font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; line-height: 1.6; color: #333; max-width: 1000px; margin: 0 auto; padding: 20px; background-color: #f5f7fa; }}
        .report-card {{ background: white; padding: 40px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.05); }}
        h1 {{ color: #1a365d; border-bottom: 3px solid #3182ce; padding-bottom: 10px; }}
        h2 {{ color: #2c5282; margin-top: 40px; border-bottom: 1px solid #e2e8f0; padding-bottom: 8px; }}
        h3 {{ color: #2b6cb0; margin-top: 25px; }}
        ul {{ padding-left: 20px; }}
        li {{ margin-bottom: 12px; }}
        strong {{ color: #2d3748; }}
        blockquote {{ border-left: 4px solid #3182ce; margin: 0; padding-left: 20px; color: #4a5568; font-style: italic; }}
        hr {{ border: 0; height: 1px; background: #e2e8f0; margin: 30px 0; }}
    </style>
</head>
<body>
    <div class="report-card">
        {html_body}
    </div>
</body>
</html>"""
            html_filename = f"review_{name_without_ext}_{safe_model_name}{suffix}.html"
            with open(html_filename, "w", encoding="utf-8") as f:
                f.write(styled_html)
            logger.info(f"Relatório HTML salvo em: {html_filename}")
        except Exception as e:
            logger.error(f"Falha ao gerar HTML: {e}")
            
        # Geração do JSON no formato esperado
        parsed_sections = {}
        general_semantica = []

        # Extrair Visão Geral
        section_1_match = re.search(r'##\s*(?:1\.\s*)?Visão Geral.*?(?=##\s*(?:2\.\s*)?Revisões Detalhadas|###\s*Seção:)', review_content, re.DOTALL | re.IGNORECASE)
        if section_1_match:
            section_1_text = section_1_match.group(0)
            bullets = re.findall(r'\*\s*\*\*(.*?):\*\*\s*(.*?)(?=\n\s*\*|$)', section_1_text, re.DOTALL | re.IGNORECASE)
            for title, text in bullets:
                general_semantica.append(f"Problema: Visão Geral - {title.strip()}\nSugestão: {text.strip()}")

        # Extrair Revisões Detalhadas
        section_2_match = re.search(r'(?:##\s*(?:2\.\s*)?Revisões Detalhadas por Seção|###\s*Seção:\s*T[ÍI]TULO)(.*?)(?:##\s*(?:3\.\s*)?Conclusão da Revisão|###\s*Aspectos Positivos|$)', review_content, re.DOTALL | re.IGNORECASE)
        if section_2_match:
            section_2_text = review_content[section_2_match.start():section_2_match.end()]
            parts = re.split(r'\n(?:####|###|##)\s+', section_2_text)
            for part in parts:
                if not part.strip():
                    continue
                    
                lines = part.split('\n')
                json_key = resolve_section_key(lines[0])
                if not json_key:
                    # Se não achou seção canônica, tenta capturar no "geral" ou ignora
                    continue
                    
                obs_normativa = parsed_sections.setdefault(json_key, {}).setdefault("observacao_normativa", [])
                obs_semantica = parsed_sections.setdefault(json_key, {}).setdefault("observacao_semantica", [])
                
                # Regex para buscar Problema -> Sugestão -> Tipo
                blocks_matches = re.finditer(
                    r'(?:\*\*Trecho:\*\*.*?)?\*\*Problema:\*\*(.*?)\*\*Sugestão:\*\*(.*?)\*\*Tipo:\*\*(.*?)(?=\n\s*(?:\*\s*)?\*\*Problema:\*\*|$)', 
                    part, 
                    re.DOTALL | re.IGNORECASE
                )
                
                for match in blocks_matches:
                    prob = match.group(1).strip()
                    sug = match.group(2).strip()
                    tipo = match.group(3).strip().lower()
                    tipo = tipo.split('\n')[0].strip()
                    
                    suggestion_text = f"Problema: {prob}\nSugestão: {sug}"
                    if "normativa" in tipo:
                        if suggestion_text not in obs_normativa:
                            obs_normativa.append(suggestion_text)
                    else:
                        if suggestion_text not in obs_semantica:
                            obs_semantica.append(suggestion_text)
        
        # Extrair especificamente a seção 3 (Conclusão da Revisão) para general_semantica
        section_3_match = re.search(r'## 3\. Conclusão da Revisão(.*?)(?=$)', review_content, re.DOTALL | re.IGNORECASE)
        if section_3_match:
            general_semantica.append(f"Problema: Conclusão da Revisão\nSugestão: {section_3_match.group(1).strip()}")
                
        corpo_do_trabalho = {}
        # Preenche com as seções segmentadas (apenas para ter o texto no JSON)
        for sec in secoes:
            json_key = resolve_section_key(sec.type) or sec.type
            parsed_data = parsed_sections.get(json_key, {"observacao_normativa": [], "observacao_semantica": []})
            
            corpo_do_trabalho[json_key] = {
                "presente": True,
                "pagina_inicio": 1,
                "pagina_fim": 1,
                "texto": sec.text[:500] + "..." if len(sec.text) > 500 else sec.text,
                "revisor": [
                    {
                        "1": parsed_data
                    }
                ]
            }
            
        elapsed_time = time.time() - start_time
        
        json_report = {
            "metadata": {
                "tcc_id": name_without_ext,
                "instituicao": "UNIVERSIDADE",
                "curso": "CURSO",
                "area_conhecimento": "AREA",
                "ano": 2025,
                "norma_referencia": "ABNT",
                "idioma": "pt-BR",
                "num_paginas": 0,
                "total_tokens": tokens,
                "total_cost_usd": cost,
                "total_time_seconds": elapsed_time
            },
            "corpo_do_trabalho": corpo_do_trabalho,
            "general": {
                "revisor": [
                    {
                        "1": {
                            "observacao_normativa": [],
                            "observacao_semantica": general_semantica
                        }
                    }
                ]
            }
        }
        
        json_filename = f"review_{name_without_ext}_{safe_model_name}{suffix}.json"
        with open(json_filename, "w", encoding="utf-8") as f:
            json.dump(json_report, f, indent=2, ensure_ascii=False)
        logger.info(f"Relatório JSON salvo em '{json_filename}'")
            
    except Exception as e:
        logger.error(f"Erro ao processar o LLM: {e}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python single_agent_review.py <caminho_para_o_pdf> [modelo]")
    else:
        pdf = sys.argv[1]
        model = sys.argv[2] if len(sys.argv) > 2 else "gemini/gemini-2.5-flash-lite"
        review_entire_pdf(pdf, model)
