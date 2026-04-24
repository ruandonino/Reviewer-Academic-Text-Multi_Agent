import os
import sys
import time

# Adiciona a raiz do projeto ao sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.ingestion.parsers import MinerUParser
from src.ingestion.segmenter import segmentar_secoes
from src.utils.logger import get_logger

logger = get_logger()

def test_mineru_isolated(pdf_path: str):
    if not os.path.exists(pdf_path):
        logger.error(f"Arquivo '{pdf_path}' não encontrado.")
        return

    logger.info(f"=== Iniciando Teste Isolado do MinerU com: {pdf_path} ===")
    
    # Instancia o parser
    parser = MinerUParser() 
    
    logger.info(f"Configuração: use_cpu={parser.use_cpu}")
    
    results = {}
    parser_name = "mineru"

    start_time = time.time()
    try:
        # 1. Executa a conversão (Etapa de Ingestão)
        markdown_content = parser.parse_pdf(pdf_path)
        end_time = time.time()
        
        execution_time = end_time - start_time
        
        if markdown_content:
            # 2. Simula a Etapa de Segmentação (O que os agentes realmente recebem)
            secoes = segmentar_secoes(markdown_content)
            
            # Salva o resultado em um arquivo específico para conferência
            output_name = f"debug_mineru_{os.path.basename(pdf_path)}.md"
            with open(output_name, "w", encoding="utf-8") as f:
                f.write(markdown_content)
            
            char_count = len(markdown_content)
            logger.info(f"SUCESSO: {parser_name} finalizou em {execution_time:.2f} segundos.")
            logger.info(f"Seções detectadas: {len(secoes)}")
            
            # Log das seções para verificar a qualidade da segmentação
            for sec in secoes:
                logger.debug(f"  - [{sec.type}] {len(sec.text)} chars")

            results[parser_name] = {
                "status": "Sucesso",
                "time": execution_time,
                "chars": char_count,
                "sections_count": len(secoes),
                "sections_list": [s.type for s in secoes]
            }
        else:
            logger.error(f"FALHA: {parser_name} retornou conteúdo vazio.")
            results[parser_name] = {"status": "Falha (Vazio)", "time": execution_time}
            
    except Exception as e:
        end_time = time.time()
        logger.error(f"ERRO CRÍTICO no parser {parser_name}: {e}")
        results[parser_name] = {"status": f"Erro: {str(e)[:50]}", "time": end_time - start_time}

    # Resumo Final Detalhado (Igual ao test_parsers_real.py)
    logger.info("\n" + "="*80)
    logger.info("RESUMO DO TESTE: QUALIDADE DA ENTRADA PARA OS AGENTES (MINERU ISOLADO)")
    logger.info("="*80)
    logger.info(f"{'Parser':<12} | {'Status':<10} | {'Tempo (s)':<10} | {'Seções':<8} | {'Lista de Seções Detectadas'}")
    logger.info("-" * 80)
    for name, data in results.items():
        if data["status"] == "Sucesso":
            status = "OK"
            t = f"{data['time']:.2f}"
            sec_count = data["sections_count"]
            sec_list = ", ".join(data["sections_list"])
            logger.info(f"{name:<12} | {status:<10} | {t:<10} | {sec_count:<8} | {sec_list}")
        else:
            logger.info(f"{name:<12} | {data['status']:<10} | {data['time']:.2f} | - | -")
    logger.info("="*80)

if __name__ == "__main__":
    # Padrão caso não passe argumento
    target_pdf = "TCC_CCO-7.pdf" 
    
    if len(sys.argv) > 1:
        target_pdf = sys.argv[1]
        
    test_mineru_isolated(target_pdf)
