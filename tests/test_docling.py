import os
import sys

# Adiciona a raiz do projeto ao sys.path para permitir as importações locais
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.ingestion.parsers import DoclingParser
from src.utils.logger import get_logger

logger = get_logger()

def test_docling_debugger():
    # Caminho para o seu PDF de teste (altere para um caminho real na sua máquina se necessário)
    pdf_path = "sample_tcc.pdf"
    
    # Se o arquivo não existir, cria um PDF dummy muito simples apenas para evitar que o código quebre logo de cara
    if not os.path.exists(pdf_path):
        logger.warning(f"Arquivo '{pdf_path}' não encontrado no diretório atual.")
        logger.info("Por favor, coloque um arquivo PDF válido chamado 'sample_tcc.pdf' na raiz do projeto para o teste completo.")
        return

    logger.info("=== Iniciando Depuração do DoclingParser ===")
    
    # Instancia o parser. 
    # DICA DE DEPURAÇÃO: Você pode forçar 'use_cpu=True' aqui para depurar o comportamento sem GPU
    parser = DoclingParser() 
    
    logger.info(f"O Parser utilizará CPU? -> {parser.use_cpu}")
    
    # Coloque um BREAKPOINT na linha abaixo (F9 no VS Code)
    resultado_markdown = parser.parse_pdf(pdf_path)
    
    if resultado_markdown:
        logger.info("=== Extração concluída com sucesso! ===")
        logger.info("Primeiros 500 caracteres do Markdown:")
        print(resultado_markdown[:500])
        
        # Salva o resultado para você inspecionar a qualidade da extração
        output_file = "teste_docling_output.md"
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(resultado_markdown)
        logger.info(f"Markdown salvo em '{output_file}'")
    else:
        logger.error("A extração falhou e retornou None.")

if __name__ == "__main__":
    test_docling_debugger()
