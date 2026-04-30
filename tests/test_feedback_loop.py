import os
import sys
import asyncio
from unittest.mock import patch

# Adiciona a raiz do projeto ao sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.orchestration.graph import build_review_graph
from src.models.section import Section
from src.models.router import RouterDecision, ModelAllocation
from src.models.review import ReviewResult, Observation, EvaluationScore
from src.agents.synthesizer_agent import synthesize_final_report
from src.utils.logger import get_logger

logger = get_logger()

# --- Variáveis Globais para Controle dos Mocks ---
attempt_counter = 0

# --- Mocks Estáticos ---
MOCK_DECISION = RouterDecision(
    architecture="Single",
    models=[ModelAllocation(agent_name="revisor_unico", model_id="mock-model")],
    reasoning="Decisão mockada para teste de fluxo.",
    system_prompt="Prompt mockado."
)

MOCK_REVIEW_RUIM = ReviewResult(
    general_comments="Revisão Ruim (Tentativa 1)",
    observations=[Observation(quote="A", issue="B", suggestion="C", type="Normativa")]
)

MOCK_REVIEW_BOA = ReviewResult(
    general_comments="Revisão Boa (Tentativa 2)",
    observations=[Observation(quote="X", issue="Y", suggestion="Z", type="Semântica")]
)

def mock_route_section(section):
    logger.info(f"[MOCK] Roteador invocado para a seção: {section.type}")
    return MOCK_DECISION, []

def mock_execute_architecture(decision, section):
    global attempt_counter
    logger.info(f"[MOCK] Executor invocado (Tentativa {attempt_counter + 1})")
    # Retorna revisão ruim na primeira vez, boa na segunda
    if attempt_counter == 0:
        return MOCK_REVIEW_RUIM
    return MOCK_REVIEW_BOA

def mock_evaluate_review(section, review):
    global attempt_counter
    logger.info(f"[MOCK] Avaliador invocado (Tentativa {attempt_counter + 1})")
    attempt_counter += 1
    
    if attempt_counter == 1:
        # Reprova na primeira tentativa
        logger.warning("[MOCK] Simulando nota BAIXA (50.0) -> Deve forçar o retorno ao Roteador.")
        return EvaluationScore(score=50.0, approved=False)
    else:
        # Aprova na segunda tentativa
        logger.info("[MOCK] Simulando nota ALTA (95.0) -> Deve seguir para o Sumarizador.")
        return EvaluationScore(score=95.0, approved=True)

def mock_summarize_and_index(section, review, decision, score, cost_tokens=0, cost_usd=0.0):
    logger.info(f"[MOCK] Sumarizador invocado! Nota final salva: {score}")
    # Retorna None apenas para mock
    return None

def mock_synthesize_report(reviews):
    logger.info(f"[MOCK] Sintetizador invocado com {len(reviews)} revisões aprovadas.")
    return "# Relatório Final Mockado\nTudo ocorreu bem."


@patch("src.orchestration.graph.route_section", side_effect=mock_route_section)
@patch("src.orchestration.graph.execute_architecture", side_effect=mock_execute_architecture)
@patch("src.orchestration.graph.evaluate_review", side_effect=mock_evaluate_review)
@patch("src.orchestration.graph.summarize_and_index", side_effect=mock_summarize_and_index)
@patch("src.agents.synthesizer_agent.completion") # Mock do LiteLLM no sintetizador para teste rápido
def test_feedback_mechanism(mock_comp, mock_sum, mock_eval, mock_exec, mock_route):
    global attempt_counter
    attempt_counter = 0

    logger.info("=== Iniciando Teste de Integração: Mecanismo de Feedback (LangGraph) ===")

    # 1. Instancia o Grafo
    app_graph = build_review_graph()

    # 2. Cria a Seção de Teste
    target_section = Section(type="metodologia", position=1, text="Texto teste.")

    initial_state = {
        "section": target_section,
        "attempts": 0,
        "is_approved": False,
        "best_score": -1.0
    }

    # 3. Executa o fluxo (A mágica do Loop acontece aqui)
    logger.info("--- Iniciando execução do Grafo ---")
    final_state = app_graph.invoke(initial_state)
    logger.info("--- Execução do Grafo Concluída ---")

    # 4. Verificações do Estado Final
    attempts_made = final_state.get("attempts")
    best_score = final_state.get("best_score")
    is_approved = final_state.get("is_approved")
    best_review = final_state.get("best_review")

    logger.info(f"\n--- VERIFICAÇÃO DE ESTADO ---")
    logger.info(f"Tentativas realizadas: {attempts_made} (Esperado: 2)")
    logger.info(f"Nota final (Best Score): {best_score} (Esperado: 95.0)")
    logger.info(f"Foi aprovado no final? {is_approved} (Esperado: True)")
    
    if best_review and best_review.general_comments == "Revisão Boa (Tentativa 2)":
        logger.info("A revisão salva no estado final é corretamente a da segunda tentativa.")
    else:
        logger.error("A revisão salva não é a esperada!")

    # 5. Etapa 8: Simula a passagem das revisões validadas para o Sintetizador Final
    logger.info("\n--- Testando o Agente Sintetizador (Etapa 8) ---")
    # Para o teste do sintetizador real sem API, vamos mockar a resposta do LiteLLM
    class MockMsg: content = "# Relatório Final Unificado\nO texto precisa de melhorias gerais."
    class MockChoice: message = MockMsg()
    class MockResp: choices = [MockChoice()]
    mock_comp.return_value = MockResp()
    
    final_report = synthesize_final_report([best_review])
    logger.info(f"Relatório Gerado:\n{final_report}")

    logger.info("\n=== Teste do Mecanismo de Feedback Concluído ===")

if __name__ == "__main__":
    test_feedback_mechanism()