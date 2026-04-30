import asyncio
import os
import sys
from dotenv import load_dotenv
from src.ingestion.parsers import convert_pdf_to_markdown
from src.ingestion.segmenter import segmentar_secoes
from src.orchestration.graph import build_review_graph
from src.agents.synthesizer_agent import synthesize_final_report
from src.utils.logger import get_logger

load_dotenv()
logger = get_logger()

async def process_section_async(section, app_graph):
    """
    Processa uma seção individual de forma assíncrona usando o LangGraph.
    """
    logger.info(f"==> Iniciando processamento para seção: {section.type} (Posição {section.position})")
    
    initial_state = {
        "section": section,
        "attempts": 0,
        "is_approved": False,
        "best_score": -1.0
    }
    
    # Run the graph
    final_state = await app_graph.ainvoke(initial_state)
    
    # Retorna a melhor revisão obtida
    best_review = final_state.get("best_review")
    logger.info(f"<== Processamento concluído para seção: {section.type}")
    return best_review

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
    revisoes_validas = [r for r in revisoes_parciais if r is not None]
    
    # Etapa 8: Síntese Final
    logger.info("Etapa 8: Síntese Final")
    relatorio_final = synthesize_final_report(revisoes_validas)
    
    logger.info("=== RELATÓRIO FINAL ===")
    print(relatorio_final)
    
    base_name = os.path.basename(pdf_path)
    name_without_ext = os.path.splitext(base_name)[0]
    report_filename = f"relatorio_final_{name_without_ext}.md"
    
    with open(report_filename, "w", encoding="utf-8") as f:
        f.write(relatorio_final)
    logger.info(f"Relatório salvo em '{report_filename}'")

if __name__ == "__main__":
    asyncio.run(main())
