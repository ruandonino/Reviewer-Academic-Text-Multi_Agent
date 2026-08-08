import asyncio
import os
import sys
import time
from dotenv import load_dotenv
from src.ingestion.parsers import convert_pdf_to_markdown
from src.ingestion.segmenter import segmentar_secoes
from src.orchestration.graph import build_review_graph
from src.agents.synthesizer_agent import synthesize_final_report
from src.utils.logger import get_logger
from src.utils.section_mapping import resolve_section_key
from src.utils.llm_client import get_usage_log_path, start_usage_logging, summarize_usage_log

load_dotenv(override=True)
logger = get_logger()

from src.models.review import ReviewResult

async def process_section_async(section, app_graph):
    """
    Processa uma seção individual de forma assíncrona usando o LangGraph.
    """
    logger.info(f"==> Iniciando processamento para seção: {section.type} (Posição {section.position})")
    
    section_started_at = time.monotonic()

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
        return (
            section,
            best_review,
            final_state.get("total_cost", 0.0),
            final_state.get("total_tokens", 0),
            round(time.monotonic() - section_started_at, 3),
        )
        
    except Exception as e:
        logger.error(f"Erro catastrófico ao processar seção {section.type}: {e}")
        fallback_review = ReviewResult(
            general_comments=f"Erro crítico no processamento da seção {section.type}: {str(e)}",
            observations=[]
        )
        return (
            section,
            fallback_review,
            0.0,
            0,
            round(time.monotonic() - section_started_at, 3),
        )

async def main():
    process_started_at = time.monotonic()
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
    usage_log_path = start_usage_logging(name_without_ext)

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
    reviews_input = [(r[0], r[1]) for r in revisoes_validas]
    relatorio_final, synth_tokens, synth_cost = synthesize_final_report(reviews_input)
    
    logger.info("=== RELATÓRIO FINAL ===")
    if os.getenv("PRINT_FINAL_REPORT", "").lower() in {"1", "true", "yes"}:
        try:
            print(relatorio_final)
        except UnicodeEncodeError:
            try:
                encoding = sys.stdout.encoding or "utf-8"
                print(relatorio_final.encode(encoding, errors="replace").decode(encoding))
            except Exception:
                logger.warning("Não foi possível imprimir o relatório final no console devido a problemas de codificação.")
    else:
        logger.info("Relatório final preparado; saída completa no console desabilitada.")
    
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
            "time_seconds": sec_time,
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
        "sections_breakdown": section_costs,
        "token_usage_log": get_usage_log_path(),
        "token_breakdown": summarize_usage_log()
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
    
    suffix = os.getenv("RUN_SUFFIX", "")
    report_filename = f"relatorio_final_{name_without_ext}{suffix}.md"
    json_filename = f"relatorio_final_{name_without_ext}{suffix}.json"
    
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
        html_filename = f"relatorio_final_{name_without_ext}{suffix}.html"
        with open(html_filename, "w", encoding="utf-8") as f:
            f.write(styled_html)
        logger.info(f"Relatório HTML salvo em '{html_filename}'")
    except Exception as e:
        logger.error(f"Falha ao gerar relatório HTML: {e}")
    
    # Geração do JSON no formato TCC_CCO-7.json
    import json
    import re
    
    parsed_sections = {}
    general_semantica = []

    # O campo ``general`` do JSON representa apenas as recomendações finais do relatório.
    # A Visão Geral é contextual e permanece exclusivamente no Markdown.
    suggestions_match = re.search(
        r'(?im)^###\s+Sugest.*Gerais.*$',
        relatorio_final,
    )
    if suggestions_match:
        suggestions_text = relatorio_final[suggestions_match.end():]
        next_heading = re.search(r'(?m)^#{1,3}\s+', suggestions_text)
        if next_heading:
            suggestions_text = suggestions_text[:next_heading.start()]

        for suggestion in re.findall(
            r'(?ms)^\s*(?:\d+\.\s+|[-*+]\s+)(.*?)(?=^\s*(?:\d+\.\s+|[-*+]\s+)|\Z)',
            suggestions_text,
        ):
            suggestion = suggestion.strip()
            if suggestion:
                general_semantica.append(
                    f"Problema: Recomendações Gerais de Melhoria\nSugestão: {suggestion}"
                )

    section_2_match = re.search(r'## 2\..*?(?=## 3\.)', relatorio_final, re.DOTALL | re.IGNORECASE)
    if section_2_match:
        section_2_text = section_2_match.group(0)
        parts = re.split(r'\n\s*(?:###|##)\s+\d+\.\d+\s+', section_2_text)
        for part in parts[1:]:
            lines = part.split('\n')
            json_key = resolve_section_key(lines[0])
            if not json_key:
                continue
                
            obs_normativa = []
            obs_semantica = []
            
            matches = list(re.finditer(
                r'\*\*Problema[^*]*\*\*\s*(.*?)\s*(?:[-*]\s*)?\*\*Sugest[^*]*\*\*\s*(.*?)\s*(?:[-*]\s*)?\*\*Tipo[^*]*\*\*\s*(.*?)(?=\s*(?:[-*]\s*)?\*\*Problema[^*]*\*\*|\Z)',
                part,
                re.DOTALL | re.IGNORECASE
            ))
            for match in matches:
                try:
                    prob = match.group(1).strip()
                    sug = match.group(2).strip()
                    tipo = match.group(3).strip().lower()
                    
                    # Clean trailing bullet punctuation or spaces
                    prob = re.sub(r'\s*[\*_-]+\s*$', '', prob).strip()
                    sug = re.sub(r'\s*[\*_-]+\s*$', '', sug).strip()
                    tipo = re.sub(r'[^a-z]', '', tipo)
                    
                    suggestion_text = f"Problema: {prob}\nSugestão: {sug}"
                    if "normativa" in tipo:
                        obs_normativa.append(suggestion_text)
                    else:
                        obs_semantica.append(suggestion_text)
                except Exception as e:
                    pass

            parsed_sections[json_key] = {
                "observacao_normativa": obs_normativa,
                "observacao_semantica": obs_semantica
            }

    # Aceita sínteses com níveis de cabeçalho diferentes e sem a seção final.
    detailed_start = re.search(r'(?m)^#{2,4}\s+2\.\s+', relatorio_final)
    if detailed_start:
        detailed_text = relatorio_final[detailed_start.end():]
        detailed_end = re.search(r'(?m)^#{2,4}\s+3\.\s+', detailed_text)
        if detailed_end:
            detailed_text = detailed_text[:detailed_end.start()]

        headings = list(re.finditer(
            r'(?m)^#{3,4}\s+(?:2\.\d+\s+)?(.+?)\s*$', detailed_text
        ))
        if headings:
            parsed_sections = {}
            for index, heading in enumerate(headings):
                json_key = resolve_section_key(heading.group(1))
                if not json_key:
                    continue

                next_start = headings[index + 1].start() if index + 1 < len(headings) else len(detailed_text)
                section_text = detailed_text[heading.end():next_start]
                obs_normativa = []
                obs_semantica = []
                for match in re.finditer(
                    r'\*\*Problema[^*]*\*\*\s*(.*?)\s*(?:[-*]\s*)?\*\*Sugest[^*]*\*\*\s*(.*?)\s*(?:[-*]\s*)?\*\*Tipo[^*]*\*\*\s*(.*?)(?=\s*(?:[-*]\s*)?\*\*Problema[^*]*\*\*|\Z)',
                    section_text,
                    re.DOTALL | re.IGNORECASE,
                ):
                    prob = re.sub(r'\s*[\*_-]+\s*$', '', match.group(1)).strip()
                    sug = re.sub(r'\s*[\*_-]+\s*$', '', match.group(2)).strip()
                    tipo = re.sub(r'[^a-z]', '', match.group(3).lower())
                    observation = f"Problema: {prob}\nSugestão: {sug}"
                    if "normativa" in tipo:
                        obs_normativa.append(observation)
                    else:
                        obs_semantica.append(observation)

                parsed_sections[json_key] = {
                    "observacao_normativa": obs_normativa,
                    "observacao_semantica": obs_semantica,
                }
            
    corpo_do_trabalho = {}
    for sec, rev, sec_cost, sec_tokens, sec_time in revisoes_validas:
        json_key = resolve_section_key(sec.type) or sec.type
        
        parsed_data = parsed_sections.get(json_key, {"observacao_normativa": [], "observacao_semantica": []})
        
        corpo_do_trabalho[json_key] = {
            "presente": True,
            "pagina_inicio": 1,
            "pagina_fim": 1,
            "texto": sec.text[:500] + "..." if len(sec.text) > 500 else sec.text,
            "review_metrics": {
                "total_cost_usd": sec_cost,
                "total_tokens": sec_tokens,
                "total_time_seconds": sec_time,
            },
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
            "num_paginas": 0,
            "total_tokens": global_cost["grand_total_tokens"],
            "total_cost_usd": global_cost["grand_total_cost_usd"],
            "total_time_seconds": round(time.monotonic() - process_started_at, 3)
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
