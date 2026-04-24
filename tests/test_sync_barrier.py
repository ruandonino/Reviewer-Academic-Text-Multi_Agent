import os
import sys
import asyncio
import time
from unittest.mock import patch, MagicMock

# Adiciona a raiz do projeto ao sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.models.section import Section
from src.models.review import ReviewResult
from src.utils.logger import get_logger

logger = get_logger()

# --- Mocks e Variáveis de Controle ---
section_completion_times = {}
synthesizer_call_time = 0

async def mock_process_section_async(section, app_graph):
    """
    Simula o processamento de uma seção com tempos de atraso variados.
    Isso prova que seções independentes demoram tempos diferentes para serem 'Aprovadas'.
    """
    logger.info(f"[{section.type.upper()}] Iniciando revisão...")
    
    # Define tempos diferentes baseados no tipo da seção para simular que
    # uma seção precisou do 'loop de feedback' e demorou mais que as outras.
    delay = 1.0
    if section.type == "metodologia":
        delay = 3.0 # Simula que metodologia reprovou na 1ª vez e demorou mais
    elif section.type == "resultados":
        delay = 2.0
        
    await asyncio.sleep(delay)
    
    completion_time = time.time()
    section_completion_times[section.type] = completion_time
    logger.info(f"[{section.type.upper()}] Revisão APROVADA e concluída em {delay}s.")
    
    # Retorna um mock de ReviewResult
    return ReviewResult(general_comments=f"Revisão final de {section.type}", observations=[])

def mock_synthesize_final_report(reviews):
    """
    Mock do Sintetizador para registrar exatamente quando ele foi chamado.
    """
    global synthesizer_call_time
    synthesizer_call_time = time.time()
    logger.info(f"[SINTETIZADOR] Invocado com {len(reviews)} revisões.")
    return "Relatório Final Mockado"

@patch("src.agents.synthesizer_agent.synthesize_final_report", side_effect=mock_synthesize_final_report)
def test_synchronization_barrier(mock_synth):
    logger.info("=== Iniciando Teste da Barreira de Sincronização (Processamento Paralelo) ===")
    
    # Cria as seções de teste
    secoes = [
        Section(type="introdução", position=1, text="..."),
        Section(type="metodologia", position=2, text="..."),
        Section(type="resultados", position=3, text="...")
    ]
    
    app_graph_mock = MagicMock() # Não usaremos o grafo real neste teste unitário de fluxo
    
    # Função assíncrona principal do teste
    async def run_parallel_flow():
        start_time = time.time()
        
        # Dispara o processamento paralelo (Exatamente como no main.py)
        logger.info("Disparando asyncio.gather para todas as seções...")
        tasks = [mock_process_section_async(sec, app_graph_mock) for sec in secoes]
        
        # A Barreira de Sincronização: o código deve travar aqui até que a ÚLTIMA seção termine.
        revisoes_parciais = await asyncio.gather(*tasks)
        
        revisoes_validas = [r for r in revisoes_parciais if r is not None]
        
        # Etapa 8: Síntese Final
        # Esta linha SÓ PODE ser executada após todas as tarefas do gather terminarem.
        from src.agents.synthesizer_agent import synthesize_final_report
        synthesize_final_report(revisoes_validas)
        
        end_time = time.time()
        logger.info(f"Fluxo total concluído em {end_time - start_time:.2f}s")
    
    # Executa o loop de eventos
    asyncio.run(run_parallel_flow())
    
    # --- Validações (Asserts) ---
    logger.info("\n--- VALIDAÇÃO DA BARREIRA ---")
    
    # Garante que o sintetizador foi chamado
    assert mock_synth.call_count == 1, "O sintetizador não foi chamado exatamente 1 vez!"
    
    # Valida a ordem cronológica
    # O tempo que o sintetizador foi chamado DEVE ser MAIOR que o tempo de conclusão da seção mais demorada.
    last_section_to_finish = max(section_completion_times.values())
    
    for sec_type, comp_time in section_completion_times.items():
        logger.info(f"Conclusão de '{sec_type}': {comp_time}")
        
    logger.info(f"Invocação do Sintetizador: {synthesizer_call_time}")
    
    if synthesizer_call_time >= last_section_to_finish:
        logger.info("✅ SUCESSO: O Agente Sintetizador esperou pacientemente todas as seções serem aprovadas/concluídas!")
    else:
        logger.error("❌ FALHA: O Agente Sintetizador foi executado ANTES de todas as seções terminarem.")
        
    logger.info("=== Teste de Barreira Concluído ===")

if __name__ == "__main__":
    test_synchronization_barrier()