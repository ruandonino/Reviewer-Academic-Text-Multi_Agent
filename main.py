import asyncio
import os
import sys
from dotenv import load_dotenv
from src.ingestion.parsers import convert_pdf_to_markdown
from src.ingestion.segmenter import segmentar_secoes
from src.orchestration.graph import build_review_graph
from src.agents.synthesizer_agent import synthesize_final_report
from src.utils.logger import get_logger

load_dotenv(override=True)
logger = get_logger()

from src.models.review import ReviewResult

async def process_section_async(section, app_graph):
    """
    Processa uma seção individual de forma assíncrona usando o LangGraph.
    """
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
            
        logger.info(f"<== Processamento concluído para seção: {section.type}")
        return (section, best_review, final_state.get("total_cost", 0.0), final_state.get("total_tokens", 0))
        
    except Exception as e:
        logger.error(f"Erro catastrófico ao processar seção {section.type}: {e}")
        fallback_review = ReviewResult(
            general_comments=f"Erro crítico no processamento da seção {section.type}: {str(e)}",
            observations=[]
        )
        return (section, fallback_review, 0.0, 0)

async def main():
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
    reviews_only = [r[1] for r in revisoes_validas]
    relatorio_final, synth_tokens, synth_cost = synthesize_final_report(reviews_only)
    
    logger.info("=== RELATÓRIO FINAL ===")
    print(relatorio_final)
    
    # --- CÁLCULO E LOG DE CUSTOS ---
    costs_dir = os.path.join("logs", "costs")
    os.makedirs(costs_dir, exist_ok=True)
    
    section_costs = {}
    total_sections_cost = 0.0
    total_sections_tokens = 0
    
    for sec, rev, sec_cost, sec_tokens in revisoes_validas:
        section_costs[sec.type] = {
            "tokens": sec_tokens,
            "cost_usd": sec_cost
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
    
    cost_filename = os.path.join(costs_dir, f"cost_{name_without_ext}.json")
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
        "resumo": "resumo",
        "introdução": "introducao",
        "referencial teórico": "revisao_bibliografica",
        "revisão da literatura": "revisao_bibliografica",
        "metodologia": "metodologia",
        "resultados": "resultados",
        "discussão e conclusão": "conclusao",
        "referências": "referencias"
    }
    
    parsed_sections = {}
    general_semantica = []

    # Extrair Visão Geral
    section_1_match = re.search(r'## 1\. Visão Geral.*?(?=## 2\.)', relatorio_final, re.DOTALL | re.IGNORECASE)
    if section_1_match:
        section_1_text = section_1_match.group(0)
        # Buscar qualquer bullet point que não seja de seção
        bullets = re.findall(r'\*\s*\*\*(.*?):\*\*\s*(.*?)(?=\n\s*\*|$)', section_1_text, re.DOTALL | re.IGNORECASE)
        for title, text in bullets:
            general_semantica.append(f"Problema: Visão Geral - {title.strip()}\nSugestão: {text.strip()}")

    # Extrair Revisões Detalhadas
    section_2_match = re.search(r'## 2\..*?(?=## 3\.)', relatorio_final, re.DOTALL | re.IGNORECASE)
    if section_2_match:
        section_2_text = section_2_match.group(0)
        parts = re.split(r'\n###\s+', section_2_text)
        for part in parts[1:]:
            lines = part.split('\n')
            sec_title_line = lines[0].lower()
            
            matched_sec_type = None
            for sec_type in section_mapping.keys():
                if sec_type in sec_title_line:
                    matched_sec_type = sec_type
                    break
            
            if not matched_sec_type:
                continue
                
            obs_normativa = []
            obs_semantica = []
            
            prob_matches = re.finditer(r'\*\*Problema:\*\*(.*?)(?=\n\s*\*\s*\*\*Sugestão:\*\*)', part, re.DOTALL | re.IGNORECASE)
            sug_matches = list(re.finditer(r'\*\*Sugestão:\*\*(.*?)(?=\n\s*\*\s*\*\*Tipo:\*\*)', part, re.DOTALL | re.IGNORECASE))
            tipo_matches = list(re.finditer(r'\*\*Tipo:\*\*(.*?)(?=\n\s*\*\s*\*\*Trecho:\*\*|\n\s*\*\s*\*\*Problema:\*\*|$)', part, re.DOTALL | re.IGNORECASE))
            
            for i, prob_match in enumerate(prob_matches):
                try:
                    prob = prob_match.group(1).strip()
                    sug = sug_matches[i].group(1).strip()
                    tipo = tipo_matches[i].group(1).strip().lower()
                    
                    suggestion_text = f"Problema: {prob}\nSugestão: {sug}"
                    if "normativa" in tipo:
                        obs_normativa.append(suggestion_text)
                    else:
                        obs_semantica.append(suggestion_text)
                except Exception as e:
                    pass
                    
            parsed_sections[section_mapping[matched_sec_type]] = {
                "observacao_normativa": obs_normativa,
                "observacao_semantica": obs_semantica
            }
            
    corpo_do_trabalho = {}
    for sec, rev, sec_cost, sec_tokens in revisoes_validas:
        json_key = section_mapping.get(sec.type, sec.type)
        
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
        
    json_report = {
        "metadata": {
            "tcc_id": name_without_ext,
            "instituicao": "UNIVERSIDADE",
            "curso": "CURSO",
            "area_conhecimento": "AREA",
            "ano": 2025,
            "norma_referencia": "ABNT",
            "idioma": "pt-BR",
            "num_paginas": 0
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
