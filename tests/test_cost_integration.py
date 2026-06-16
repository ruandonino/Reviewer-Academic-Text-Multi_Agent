import os
import sys
import unittest
from unittest.mock import patch, MagicMock

# Adiciona a raiz do projeto ao sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.orchestration.graph import build_review_graph
from src.models.section import Section
from src.models.router import RouterDecision, ModelAllocation
from src.models.review import ReviewResult, Observation, EvaluationScore
from src.config import settings
from src.utils.logger import get_logger

logger = get_logger()

# Desativa logs muito verbosos para o teste ficar limpo, a menos que haja erro
logger.remove()
logger.add(sys.stdout, level="INFO")

class TestCostIntegration(unittest.TestCase):
    def setUp(self):
        # Reinicia o grafo para cada teste
        self.app_graph = build_review_graph()
        self.target_section = Section(type="introdução", position=1, text="Texto teste para custo.")
        
        self.initial_state = {
            "section": self.target_section,
            "attempts": 0,
            "is_approved": False,
            "best_score": -1.0,
            "total_tokens": 0,
            "total_cost": 0.0
        }
        
        # Mocks padronizados
        self.mock_decision = RouterDecision(
            architecture="Single",
            models=[ModelAllocation(agent_name="revisor", model_id="mock")],
            reasoning="mock",
            system_prompt="mock"
        )
        self.mock_review = ReviewResult(general_comments="mock review", observations=[])

    @patch("src.orchestration.graph.summarize_and_index")
    @patch("src.orchestration.graph.evaluate_review")
    @patch("src.orchestration.graph.execute_architecture")
    @patch("src.orchestration.graph.route_section")
    def test_cost_accumulation_happy_path(self, mock_route, mock_exec, mock_eval, mock_sum):
        """Testa o acúmulo de custo no caminho feliz: aprovado de primeira."""
        logger.info("\n--- TESTANDO ACÚMULO DE CUSTOS (Caminho Feliz) ---")
        
        # Router gasta 100 tokens, $0.001
        mock_route.return_value = (self.mock_decision, [], 100, 0.001)
        
        # Executor gasta 500 tokens, $0.005
        mock_exec.return_value = (self.mock_review, 500, 0.005)
        
        # Avaliador gasta 50 tokens, $0.0005 e aprova
        mock_eval.return_value = (EvaluationScore(score=95.0, approved=True), 50, 0.0005)
        
        # Sumarizador gasta 20 tokens, $0.0002
        mock_sum.return_value = (None, 20, 0.0002)
        
        # Executa o grafo
        final_state = self.app_graph.invoke(self.initial_state)
        
        # Validações de Fluxo
        self.assertEqual(final_state["attempts"], 1)
        self.assertTrue(final_state["is_approved"])
        
        # Validações de Custo (100 + 500 + 50 + 20 = 670 tokens)
        self.assertEqual(final_state["total_tokens"], 670)
        # Custo: 0.001 + 0.005 + 0.0005 + 0.0002 = 0.0067
        self.assertAlmostEqual(final_state["total_cost"], 0.0067)
        
        # Valida se os valores finais foram passados pro sumarizador
        mock_sum.assert_called_once()
        _, kwargs = mock_sum.call_args
        self.assertEqual(kwargs.get("cost_tokens"), 650) # O custo ATÉ o avaliador
        self.assertAlmostEqual(kwargs.get("cost_usd"), 0.0065)


    @patch("src.orchestration.graph.summarize_and_index")
    @patch("src.orchestration.graph.evaluate_review")
    @patch("src.orchestration.graph.execute_architecture")
    @patch("src.orchestration.graph.route_section")
    def test_cumulative_cost_feedback_loop(self, mock_route, mock_exec, mock_eval, mock_sum):
        """Testa se o total_cost no final do grafo reflete a soma de TODAS as tentativas (incluindo as falhas)."""
        logger.info("\n--- TESTANDO ACÚMULO TOTAL DE CUSTOS (Feedback Loop) ---")
        
        # Router gasta 100 tokens, $0.001
        mock_route.return_value = (self.mock_decision, [], 100, 0.001)
        
        # Executor gasta 500 tokens, $0.005
        mock_exec.return_value = (self.mock_review, 500, 0.005)
        
        # Avaliador gasta 50 tokens, $0.0005. Primeira falha, segunda aprova.
        mock_eval.side_effect = [
            (EvaluationScore(score=50.0, approved=False), 50, 0.0005),
            (EvaluationScore(score=95.0, approved=True), 50, 0.0005)
        ]
        
        # Sumarizador gasta 20 tokens, $0.0002
        mock_sum.return_value = (None, 20, 0.0002)
        
        # No grafo, isso é acumulado via operator.add
        final_state = self.app_graph.invoke(self.initial_state)
        
        # A soma total deve ser 0.0134 (se aprovado na 2ª tentativa)
        self.assertAlmostEqual(final_state["total_cost"], 0.0134)
        logger.info(f"Custo total acumulado verificado: {final_state['total_cost']}")
if __name__ == "__main__":
    unittest.main(verbosity=2)
