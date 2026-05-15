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

class TestLangGraphOrchestration(unittest.TestCase):
    def setUp(self):
        # Reinicia o grafo para cada teste
        self.app_graph = build_review_graph()
        self.target_section = Section(type="introdução", position=1, text="Texto teste.")
        
        self.initial_state = {
            "section": self.target_section,
            "attempts": 0,
            "is_approved": False,
            "best_score": -1.0
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
    def test_happy_path(self, mock_route, mock_exec, mock_eval, mock_sum):
        """Testa o caminho feliz: aprovado de primeira."""
        logger.info("\n--- TESTANDO CAMINHO FELIZ (Aprovado na 1ª tentativa) ---")
        
        # Configura os mocks
        mock_route.return_value = (self.mock_decision, [])
        mock_exec.return_value = self.mock_review
        # Retorna aprovação na primeira chamada
        mock_eval.return_value = EvaluationScore(score=90.0, approved=True)
        
        # Executa o grafo
        final_state = self.app_graph.invoke(self.initial_state)
        
        # Validações
        self.assertEqual(final_state["attempts"], 1)
        self.assertTrue(final_state["is_approved"])
        self.assertEqual(final_state["best_score"], 90.0)
        
        # Garante que cada nó foi chamado exatamente 1 vez
        mock_route.assert_called_once()
        mock_exec.assert_called_once()
        mock_eval.assert_called_once()
        mock_sum.assert_called_once()

    @patch("src.orchestration.graph.summarize_and_index")
    @patch("src.orchestration.graph.evaluate_review")
    @patch("src.orchestration.graph.execute_architecture")
    @patch("src.orchestration.graph.route_section")
    def test_feedback_loop(self, mock_route, mock_exec, mock_eval, mock_sum):
        """Testa o ciclo de feedback: reprovado na 1ª, aprovado na 2ª."""
        logger.info("\n--- TESTANDO FEEDBACK LOOP (Aprovado na 2ª tentativa) ---")
        
        # Configura os mocks
        mock_route.return_value = (self.mock_decision, [])
        mock_exec.return_value = self.mock_review
        
        # Primeira chamada reprova, segunda aprova
        mock_eval.side_effect = [
            EvaluationScore(score=50.0, approved=False),
            EvaluationScore(score=85.0, approved=True)
        ]
        
        # Executa o grafo
        final_state = self.app_graph.invoke(self.initial_state)
        
        # Validações
        self.assertEqual(final_state["attempts"], 2)
        self.assertTrue(final_state["is_approved"])
        self.assertEqual(final_state["best_score"], 85.0)
        
        # O roteador, executor e avaliador devem ter rodado 2 vezes
        self.assertEqual(mock_route.call_count, 2)
        self.assertEqual(mock_exec.call_count, 2)
        self.assertEqual(mock_eval.call_count, 2)
        # O sumarizador só roda no final (1 vez)
        mock_sum.assert_called_once()

    @patch("src.orchestration.graph.summarize_and_index")
    @patch("src.orchestration.graph.evaluate_review")
    @patch("src.orchestration.graph.execute_architecture")
    @patch("src.orchestration.graph.route_section")
    def test_max_attempts_fallback(self, mock_route, mock_exec, mock_eval, mock_sum):
        """Testa o limite de tentativas (T_max): reprovado 3 vezes."""
        logger.info(f"\n--- TESTANDO LIMITE DE TENTATIVAS ({settings.max_attempts}x reprovações) ---")
        
        # Configura os mocks
        mock_route.return_value = (self.mock_decision, [])
        mock_exec.return_value = self.mock_review
        
        # Todas as chamadas reprovam. Vamos simular notas diferentes para ver se ele guarda a melhor.
        # Tentativa 1: nota 60
        # Tentativa 2: nota 75 (Melhor tentativa!)
        # Tentativa 3: nota 50
        mock_eval.side_effect = [
            EvaluationScore(score=60.0, approved=False),
            EvaluationScore(score=75.0, approved=False),
            EvaluationScore(score=50.0, approved=False)
        ]
        
        # Executa o grafo
        final_state = self.app_graph.invoke(self.initial_state)
        
        # Validações
        self.assertEqual(final_state["attempts"], settings.max_attempts)
        self.assertFalse(final_state["is_approved"])
        
        # O sistema DEVE ter armazenado a nota 75.0 como best_score, mesmo tendo tirado 50.0 na última
        self.assertEqual(final_state["best_score"], 75.0)
        
        # Os nós em loop devem ter rodado 3 vezes
        self.assertEqual(mock_route.call_count, settings.max_attempts)
        self.assertEqual(mock_exec.call_count, settings.max_attempts)
        self.assertEqual(mock_eval.call_count, settings.max_attempts)
        
        # E o sumarizador deve ter rodado 1 vez, com os dados da melhor tentativa (best_review)
        mock_sum.assert_called_once()

if __name__ == "__main__":
    unittest.main(verbosity=2)
