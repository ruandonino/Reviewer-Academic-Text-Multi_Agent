import asyncio
import os
import sys
from dotenv import load_dotenv

load_dotenv(override=True)

from src.ingestion.parsers import convert_pdf_to_markdown
from src.ingestion.segmenter import segmentar_secoes
from src.orchestration.graph import build_review_graph
from src.agents.synthesizer_agent import synthesize_final_report
from src.utils.logger import get_logger

logger = get_logger()

from src.models.review import ReviewResult

import time

async def process_section_async(section, app_graph):
    """
    Processa uma seção individual de forma assíncrona usando o LangGraph.
    """
    import time
    start_time = time.time()
    logger.info(f"==> Iniciando processamento para seção: {section.type} (Posição {section.position})")
    
    initial_state = {
        "section": section,
        "attempts": 0,
        "is_approved": False,
        "best_score": -1.0,
        "best_review": None,
        "total_cost": 0.0,
        "total_tokens": 0
    }
    
    try:
        # Run the graph
        final_state = await app_graph.ainvoke(initial_state)
        
        # Retorna a melhor revisão obtida e os custos
        best_review = final_state.get("best_review")
        
        if best_review is None:
            logger.warning(f"Seção {section.type} finalizou sem gerar best_review. Criando fallback.")
            best_review = ReviewResult(
                general_comments=f"A revisão desta seção ({section.type}) não pôde ser concluída devido a uma falha interna no orquestrador.",
                observations=[]
            )
            
        elapsed_time = time.time() - start_time
        logger.info(f"<== Processamento concluído para seção: {section.type} em {elapsed_time:.2f}s")
        return (section, best_review, final_state.get("total_cost", 0.0), final_state.get("total_tokens", 0), elapsed_time)
        
    except Exception as e:
        elapsed_time = time.time() - start_time
        logger.error(f"Erro catastrófico ao processar seção {section.type}: {e}")
        fallback_review = ReviewResult(
            general_comments=f"Erro crítico no processamento da seção {section.type}: {str(e)}",
            observations=[]
        )
        return (section, fallback_review, 0.0, 0, elapsed_time)

async def main():
    import time
    global_start_time = time.time()
    logger.info("Iniciando Sistema Multiagente de Revisão Acadêmica")
    
    # Verifica API Key para LiteLLM
    if not os.getenv("GEMINI_API_KEY"):
        logger.error("GEMINI_API_KEY não definida. O sistema requer uma chave de API do Google Gemini para usar os LLMs e Embeddings.")
        logger.error("Crie um arquivo .env com GEMINI_API_KEY=sua_chave")
        return

    # Caminho do PDF (Demonstração ou CLI argument)
    pdf_path = "sample_tcc.pdf"
    if len(sys.argv) > 1:
        pdf_path = sys.argv[1]
    
    # Etapa 1: Ingestão e Parsing
    logger.info(f"Etapa 1: Ingestão do PDF {pdf_path}")
    
    # Fallback to a mock text if file doesn't exist for demo purposes
    if not os.path.exists(pdf_path):
        logger.warning(f"Arquivo {pdf_path} não encontrado. Usando texto de demonstração.")
        md_text = """
# Introdução
Este é um trabalho sobre sistemas multiagentes. O objetivo é criar um framework escalável.
        
# Metodologia
Nós utilizamos LangGraph e LiteLLM para construir o sistema. A arquitetura é baseada em RAG.
        
# Conclusão
O sistema demonstrou eficácia na detecção de erros semânticos.
"""
    else:
        # Usa o parser padrão configurado em src/config.py (settings.default_parser)
        md_text = convert_pdf_to_markdown(pdf_path)
        
    if not md_text:
        logger.error("Falha ao extrair texto do documento.")
        return
        
    secoes = segmentar_secoes(md_text)
    
    if not secoes:
        logger.error("Nenhuma seção detectada.")
        return
        
    base_name = os.path.basename(pdf_path)
    name_without_ext = os.path.splitext(base_name)[0]

    for sec in secoes:
        sec.document_id = name_without_ext
        
    # Inicializa o Grafo
    app_graph = build_review_graph()
    
    import src.orchestration.graph as og
    og.first_pass_total = len(secoes)
    og.first_pass_routers_done = 0
    og.router_barrier_event.clear()
    
    # Processamento sem limite de concorrência simultâneo
    logger.info("Iniciando processamento das seções (Sem limite de concorrência).")
    
    tasks = []
    for sec in secoes:
        tasks.append(process_section_async(sec, app_graph))
    
    revisoes_parciais = await asyncio.gather(*tasks)
    
    # Filtra None (casos de erro extremo)
    revisoes_validas = [r for r in revisoes_parciais if r is not None and r[1] is not None]
    
    # Etapa 8: Síntese Final
    logger.info("Etapa 8: Síntese Final")
    reviews_with_sections = [(r[0], r[1]) for r in revisoes_validas]
    relatorio_final, synth_tokens, synth_cost = synthesize_final_report(reviews_with_sections)
    
    logger.info("=== RELATÓRIO FINAL ===")
    try:
        print(relatorio_final)
    except Exception as e:
        logger.warning(f"Não foi possível imprimir o relatório no console devido a restrições de encoding: {e}")

    
    # --- CÁLCULO E LOG DE CUSTOS ---
    costs_dir = os.path.join("logs", "costs")
    os.makedirs(costs_dir, exist_ok=True)
    
    section_costs = {}
    total_sections_cost = 0.0
    total_sections_tokens = 0
    
    for sec, rev, sec_cost, sec_tokens, sec_time in revisoes_validas:
        section_costs[sec.type] = {
            "tokens": sec_tokens,
            "cost_usd": sec_cost,
            "time_seconds": sec_time
        }
        total_sections_cost += sec_cost
        total_sections_tokens += sec_tokens
        
    global_cost = {
        "section_reviews_total_cost": total_sections_cost,
        "section_reviews_total_tokens": total_sections_tokens,
        "synthesizer_cost": synth_cost,
        "synthesizer_tokens": synth_tokens,
        "grand_total_cost_usd": total_sections_cost + synth_cost,
        "grand_total_tokens": total_sections_tokens + synth_tokens,
        "sections_breakdown": section_costs
    }
    
    base_name = os.path.basename(pdf_path)
    name_without_ext = os.path.splitext(base_name)[0]
    
    import datetime
    timestamp_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    cost_filename = os.path.join(costs_dir, f"cost_{name_without_ext}_{timestamp_str}.json")
    with open(cost_filename, "w", encoding="utf-8") as f:
        import json
        json.dump(global_cost, f, indent=2, ensure_ascii=False)
    logger.info(f"Relatório de Custos salvo em '{cost_filename}'")
    
    report_filename = f"relatorio_final_{name_without_ext}.md"
    json_filename = f"relatorio_final_{name_without_ext}.json"
    
    with open(report_filename, "w", encoding="utf-8") as f:
        f.write(relatorio_final)
    logger.info(f"Relatório salvo em '{report_filename}'")
    
    # Geração do HTML
    try:
        import marko
        html_body = marko.convert(relatorio_final)
        
        styled_html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Relatório de Revisão Acadêmica - {name_without_ext}</title>
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
        @media print {{ body {{ background-color: white; }} .report-card {{ box-shadow: none; padding: 0; }} }}
    </style>
</head>
<body>
    <div class="report-card">
        {html_body}
    </div>
</body>
</html>"""
        html_filename = f"relatorio_final_{name_without_ext}.html"
        with open(html_filename, "w", encoding="utf-8") as f:
            f.write(styled_html)
        logger.info(f"Relatório HTML salvo em '{html_filename}'")
    except Exception as e:
        logger.error(f"Falha ao gerar relatório HTML: {e}")
    
    # Geração do JSON no formato TCC_CCO-7.json
    import json
    import re
    
    section_mapping = {
        "título": "titulo",
        "title": "titulo",
        "resumo": "resumo",
        "abstract": "resumo",
        "introdução": "introducao",
        "introduction": "introducao",
        "referêncial teórico": "revisao_bibliografica",
        "referencial teórico": "revisao_bibliografica",
        "revisão da literatura": "revisao_bibliografica",
        "background": "revisao_bibliografica",
        "related work": "revisao_bibliografica",
        "metodologia": "metodologia",
        "desenvolvimento": "metodologia",
        "methodology": "metodologia",
        "development": "metodologia",
        "design": "metodologia",
        "resultados": "resultados",
        "results": "resultados",
        "discussão": "conclusao",
        "discussion": "conclusao",
        "discussão e conclusão": "conclusao",
        "conclusão": "conclusao",
        "conclusion": "conclusao",
        "referências": "referencias",
        "references": "referencias"
    }
    
    parsed_sections = {}
    general_semantica = []

    # Extrair Visão Geral
    # Procura por "Visão Geral", com ou sem número, e para no primeiro cabeçalho de Revisões Detalhadas ou Seção
    section_1_match = re.search(r'##\s*(?:1\.\s*)?Visão Geral.*?(?=##\s*(?:2\.\s*)?Revisões Detalhadas|###\s*Seção:)', relatorio_final, re.DOTALL | re.IGNORECASE)
    if section_1_match:
        section_1_text = section_1_match.group(0)
        # Buscar qualquer bullet point que não seja de seção
        bullets = re.findall(r'\*\s*\*\*(.*?):\*\*\s*(.*?)(?=\n\s*\*|$)', section_1_text, re.DOTALL | re.IGNORECASE)
        for title, text in bullets:
            general_semantica.append(f"Problema: Visão Geral - {title.strip()}\nSugestão: {text.strip()}")

    # Extrair Revisões Detalhadas
    # Procura desde as revisões detalhadas (ou da primeira Seção) até a Conclusão da Revisão (ou Aspectos Positivos) ou fim do arquivo
    section_2_match = re.search(r'(?:##\s*(?:2\.\s*)?Revisões Detalhadas por Seção|###\s*Seção:\s*T[ÍI]TULO)(.*?)(?:##\s*(?:3\.\s*)?Conclusão da Revisão|###\s*Aspectos Positivos|$)', relatorio_final, re.DOTALL | re.IGNORECASE)
    
    if section_2_match:
        # Se encontrou pelo "### Seção: TÍTULO", o match.group(1) perde o título, então vamos juntar
        section_2_text = relatorio_final[section_2_match.start():section_2_match.end()]
        
        # Split por subseções H3 ou H4
        parts = re.split(r'\n(?:####|###)\s+', section_2_text)
        for part in parts:
            if not part.strip():
                continue
            lines = part.split('\n')
            sec_title_line = lines[0].lower()
            
            matched_sec_type = None
            for sec_key, json_key in section_mapping.items():
                if re.search(rf'{re.escape(sec_key)}', sec_title_line, re.IGNORECASE):
                    matched_sec_type = sec_key
                    break
            
            if not matched_sec_type:
                continue
                
            obs_normativa = []
            obs_semantica = []
            
            # Regex robusto que busca os blocos de problemas, sugestões e tipos
            # Captura o texto entre as etiquetas, lidando com quebras de linha e identação
            pattern_blocks = re.compile(
                r'Problema:\s*(.*?)\s*Sugestão:\s*(.*?)\s*Tipo:\s*(.*?)(?=Trecho:|Problema:|$)',
                re.DOTALL | re.IGNORECASE
            )
            
            for match in pattern_blocks.finditer(part):
                prob = match.group(1).strip().strip('*').strip()
                sug = match.group(2).strip().strip('*').strip()
                tipo = match.group(3).strip().lower().split('\n')[0].strip().strip('*').strip()
                
                suggestion_text = f"Problema: {prob}\nSugestão: {sug}"
                if "normativa" in tipo:
                    if suggestion_text not in obs_normativa:
                        obs_normativa.append(suggestion_text)
                else:
                    if suggestion_text not in obs_semantica:
                        obs_semantica.append(suggestion_text)
                    
            mapped_key = section_mapping[matched_sec_type]
            if mapped_key not in parsed_sections:
                parsed_sections[mapped_key] = {
                    "observacao_normativa": [],
                    "observacao_semantica": []
                }
                
            for obs in obs_normativa:
                if obs not in parsed_sections[mapped_key]["observacao_normativa"]:
                    parsed_sections[mapped_key]["observacao_normativa"].append(obs)
            for obs in obs_semantica:
                if obs not in parsed_sections[mapped_key]["observacao_semantica"]:
                    parsed_sections[mapped_key]["observacao_semantica"].append(obs)
            
    corpo_do_trabalho = {}
    for sec, rev, sec_cost, sec_tokens, sec_time in revisoes_validas:
        json_key = section_mapping.get(sec.type, sec.type)
        
        parsed_data = parsed_sections.get(json_key, {"observacao_normativa": [], "observacao_semantica": []})
        
        # If the key already exists (e.g., from a different chunk of the same section), append to it, but don't overwrite the base data
        if json_key in corpo_do_trabalho:
            corpo_do_trabalho[json_key]["texto"] += "\n...\n" + (sec.text[:500] + "..." if len(sec.text) > 500 else sec.text)
            corpo_do_trabalho[json_key]["revisor"][0]["1"]["cost_usd"] += sec_cost
            corpo_do_trabalho[json_key]["revisor"][0]["1"]["time_seconds"] += sec_time
        else:
            corpo_do_trabalho[json_key] = {
                "presente": True,
                "pagina_inicio": 1,
                "pagina_fim": 1,
                "texto": sec.text[:500] + "..." if len(sec.text) > 500 else sec.text,
                "revisor": [
                    {
                        "1": {
                            "observacao_normativa": parsed_data["observacao_normativa"],
                            "observacao_semantica": parsed_data["observacao_semantica"],
                            "cost_usd": sec_cost,
                            "time_seconds": sec_time
                        }
                    }
                ]
            }
        
    global_elapsed_time = time.time() - global_start_time
    
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
            "total_tokens": global_cost["grand_total_tokens"],
            "total_cost_usd": global_cost["grand_total_cost_usd"],
            "total_time_seconds": global_elapsed_time
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
    
    with open(json_filename, "w", encoding="utf-8") as f:
        json.dump(json_report, f, indent=2, ensure_ascii=False)
    logger.info(f"Relatório JSON salvo em '{json_filename}'")

if __name__ == "__main__":
    asyncio.run(main())
