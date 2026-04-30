import os
import sys
import time

# Adiciona a raiz do projeto ao sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.ingestion.parsers import convert_pdf_to_markdown
from src.ingestion.segmenter import segmentar_secoes
from src.models.router import RouterDecision, ModelAllocation
from src.agents.execution.executor import execute_architecture
from src.utils.logger import get_logger
from dotenv import load_dotenv

load_dotenv()
logger = get_logger()

def test_single_architecture_real_pdf(pdf_path: str):
    if not os.getenv("GEMINI_API_KEY"):
        logger.error("GEMINI_API_KEY não encontrada. O teste usando Gemini será cancelado.")
        return

    if not os.path.exists(pdf_path):
        logger.error(f"Arquivo '{pdf_path}' não encontrado na raiz do projeto.")
        return

    logger.info(f"=== Iniciando Teste: Arquitetura Single em todas as seções do PDF ===")
    logger.info(f"Arquivo alvo: {pdf_path}")

    # 1. Ingestão e Parsing
    logger.info("Etapa 1: Convertendo PDF para Markdown (pode usar cache)...")
    start_time = time.time()
    md_text = convert_pdf_to_markdown(pdf_path)
    logger.info(f"Parsing concluído em {time.time() - start_time:.2f}s")
    
    if not md_text:
        logger.error("Falha ao extrair texto do documento.")
        return

    # 2. Segmentação
    logger.info("Etapa 2: Segmentando o documento...")
    secoes = segmentar_secoes(md_text)
    logger.info(f"Total de seções encontradas: {len(secoes)}")
    
    if not secoes:
        logger.error("Nenhuma seção foi detectada no documento.")
        return

    # 3. Preparando a decisão do roteador (Fixa para Single)
    decision = RouterDecision(
        architecture="Single",
        models=[ModelAllocation(agent_name="revisor_unico", model_id="gemini/gemini-2.5-flash-lite")],
        reasoning="Teste forçado da arquitetura Single em todas as seções do documento real.",
        system_prompt="Você é um revisor acadêmico experiente. Faça uma análise rigorosa e objetiva."
    )

    # 4. Executando a arquitetura Single para cada seção
    logger.info("\nEtapa 3: Executando a revisão Single para cada seção...")
    
    resultados_por_secao = {}
    
    for i, sec in enumerate(secoes):
        logger.info(f"\n[{i+1}/{len(secoes)}] Processando Seção: {sec.type.upper()}")
        logger.info(f"Tamanho do texto: {len(sec.text)} caracteres")
        
        sec_start = time.time()
        try:
            review_result = execute_architecture(decision, sec)
            sec_time = time.time() - sec_start
            
            logger.info(f"Concluído em {sec_time:.2f}s")
            logger.info(f"Comentários gerais gerados: {len(review_result.general_comments)} caracteres")
            logger.info(f"Observações (issues) encontradas: {len(review_result.observations)}")
            
            resultados_por_secao[sec.type] = {
                "status": "Sucesso",
                "time": sec_time,
                "issues_count": len(review_result.observations)
            }
            
            # Printa uma amostra das observações para ver o resultado do novo parser XML
            if review_result.observations:
                obs = review_result.observations[0]
                logger.info(f"Exemplo de observação: [{obs.type}] {obs.issue}")
                
        except Exception as e:
            sec_time = time.time() - sec_start
            logger.error(f"Erro ao processar a seção {sec.type}: {e}")
            resultados_por_secao[sec.type] = {
                "status": "Erro",
                "time": sec_time,
                "issues_count": 0
            }

    # Resumo Final
    logger.info("\n" + "="*80)
    logger.info("RESUMO DA REVISÃO SINGLE NO PDF REAL")
    logger.info("="*80)
    logger.info(f"{'Seção':<25} | {'Status':<10} | {'Tempo (s)':<10} | {'Problemas Encontrados'}")
    logger.info("-" * 80)
    total_issues = 0
    total_time = 0
    for sec_type, data in resultados_por_secao.items():
        status = data["status"]
        t = f"{data['time']:.2f}"
        issues = data["issues_count"]
        total_issues += issues
        total_time += data['time']
        logger.info(f"{sec_type:<25} | {status:<10} | {t:<10} | {issues}")
    logger.info("-" * 80)
    logger.info(f"{'TOTAL':<25} | {'-':<10} | {total_time:.2f}s   | {total_issues}")
    logger.info("="*80)
    logger.info("=== Teste Concluído ===")

if __name__ == "__main__":
    target_pdf = "TCC_CCO-7.pdf" 
    
    if len(sys.argv) > 1:
        target_pdf = sys.argv[1]
        
    test_single_architecture_real_pdf(target_pdf)
