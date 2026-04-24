import os
import sys
import time

# Adiciona a raiz do projeto ao sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.models.section import Section
from src.models.router import RouterDecision, ModelAllocation
from src.agents.execution.executor import execute_architecture
from src.utils.logger import get_logger
from dotenv import load_dotenv

load_dotenv()
logger = get_logger()

def test_executor_architectures():
    # Verifica se a chave do Gemini está presente (usaremos modelos do Gemini para os testes)
    if not os.getenv("GEMINI_API_KEY"):
        logger.error("GEMINI_API_KEY não encontrada. Teste cancelado.")
        return

    logger.info("=== Iniciando Teste de Integração do Executor Multiagente ===")

    # Seção Alvo Genérica para os testes
    target_section = Section(
        type="introdução",
        position=1,
        text="Este trabalho apresenta um sistema de inteligência artificial. A IA é muito boa. O sistema usa agentes."
    )

    # System prompt genérico
    sys_prompt = "Você é um revisor. Aponte erros no texto e sugira melhorias. Seja extremamente conciso."

    # Modelos disponíveis para o teste
    # Usaremos gemma-3-27b-it agora que o JSON parsing manual foi implementado no executor
    MODEL_1 = "gemini/gemma-3-27b-it"
    MODEL_2 = "gemini/gemma-3-27b-it"
    
    # 1. Teste: Arquitetura SINGLE
    logger.info("\n--- Testando Arquitetura: SINGLE ---")
    decision_single = RouterDecision(
        architecture="Single",
        models=[ModelAllocation(agent_name="revisor_unico", model_id=MODEL_2)],
        reasoning="Teste Single",
        system_prompt=sys_prompt
    )
    start = time.time()
    res_single = execute_architecture(decision_single, target_section)
    logger.info(f"Tempo: {time.time() - start:.2f}s")
    logger.info(f"Comentários: {res_single.general_comments}")
    logger.info(f"Observações geradas: {len(res_single.observations)}")

    # 2. Teste: Arquitetura STAR
    logger.info("\n--- Testando Arquitetura: STAR ---")
    decision_star = RouterDecision(
        architecture="Star",
        models=[
            ModelAllocation(agent_name="especialista_normas", model_id=MODEL_2),
            ModelAllocation(agent_name="especialista_semantica", model_id=MODEL_2),
            ModelAllocation(agent_name="consolidador", model_id=MODEL_1)
        ],
        reasoning="Teste Star",
        system_prompt=sys_prompt
    )
    start = time.time()
    res_star = execute_architecture(decision_star, target_section)
    logger.info(f"Tempo: {time.time() - start:.2f}s")
    logger.info(f"Comentários: {res_star.general_comments}")
    logger.info(f"Observações geradas: {len(res_star.observations)}")

    # 3. Teste: Arquitetura CHAIN
    logger.info("\n--- Testando Arquitetura: CHAIN ---")
    decision_chain = RouterDecision(
        architecture="Chain",
        models=[
            ModelAllocation(agent_name="revisor_inicial", model_id=MODEL_2),
            ModelAllocation(agent_name="refinador", model_id=MODEL_2)
        ],
        reasoning="Teste Chain",
        system_prompt=sys_prompt
    )
    start = time.time()
    res_chain = execute_architecture(decision_chain, target_section)
    logger.info(f"Tempo: {time.time() - start:.2f}s")
    logger.info(f"Comentários: {res_chain.general_comments}")
    logger.info(f"Observações geradas: {len(res_chain.observations)}")

    # 4. Teste: Arquitetura DEBATE
    logger.info("\n--- Testando Arquitetura: DEBATE ---")
    decision_debate = RouterDecision(
        architecture="Debate",
        models=[
            ModelAllocation(agent_name="debatedor_A", model_id=MODEL_2),
            ModelAllocation(agent_name="debatedor_B", model_id=MODEL_2),
            ModelAllocation(agent_name="juiz", model_id=MODEL_1)
        ],
        reasoning="Teste Debate",
        system_prompt=sys_prompt
    )
    start = time.time()
    res_debate = execute_architecture(decision_debate, target_section)
    logger.info(f"Tempo: {time.time() - start:.2f}s")
    logger.info(f"Comentários: {res_debate.general_comments}")
    logger.info(f"Observações geradas: {len(res_debate.observations)}")

    # 5. Teste: Arquitetura ENSEMBLE
    logger.info("\n--- Testando Arquitetura: ENSEMBLE ---")
    decision_ensemble = RouterDecision(
        architecture="Ensemble",
        models=[
            ModelAllocation(agent_name="votante_1", model_id=MODEL_2),
            ModelAllocation(agent_name="votante_2", model_id=MODEL_2),
            ModelAllocation(agent_name="votante_3", model_id=MODEL_2)
        ],
        reasoning="Teste Ensemble",
        system_prompt=sys_prompt
    )
    start = time.time()
    res_ensemble = execute_architecture(decision_ensemble, target_section)
    logger.info(f"Tempo: {time.time() - start:.2f}s")
    logger.info(f"Comentários: {res_ensemble.general_comments}")
    logger.info(f"Observações geradas: {len(res_ensemble.observations)}")

    logger.info("\n=== Teste de Integração do Executor Concluído ===")

if __name__ == "__main__":
    test_executor_architectures()