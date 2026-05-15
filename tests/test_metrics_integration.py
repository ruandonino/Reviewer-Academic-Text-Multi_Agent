import unittest
import time
import sys
import os

# Adiciona a raiz do projeto ao sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from unittest.mock import patch, MagicMock
from src.orchestration.graph import build_review_graph
from src.models.section import Section
from src.models.router import RouterDecision, ModelAllocation
from src.models.review import ReviewResult, EvaluationScore

class TestMetricsIntegration(unittest.TestCase):
    def setUp(self):
        self.app_graph = build_review_graph()
        self.section = Section(type="metodologia", position=2, text="Metodologia teste.")
        self.initial_state = {
            "section": self.section,
            "attempts": 0,
            "is_approved": False,
            "best_score": -1.0,
            "total_tokens": 0,
            "total_cost": 0.0
        }
        self.mock_decision = RouterDecision(
            architecture="Single",
            models=[ModelAllocation(agent_name="revisor", model_id="mock")],
            reasoning="mock",
            system_prompt="mock"
        )
        self.mock_review = ReviewResult(general_comments="mock", observations=[])

    @patch("src.orchestration.graph.summarize_and_index")
    @patch("src.orchestration.graph.evaluate_review")
    @patch("src.orchestration.graph.execute_architecture")
    @patch("src.orchestration.graph.route_section")
    def test_metrics_accumulation(self, mock_route, mock_exec, mock_eval, mock_sum):
        """Testa se custos e tokens são acumulados corretamente, incluindo embedding."""
        
        # Router: 100 tokens, 0.001
        mock_route.return_value = (self.mock_decision, [], 100, 0.001)
        
        # Exec: 500 tokens, 0.005
        mock_exec.return_value = (self.mock_review, 500, 0.005)
        
        # Eval: 50 tokens, 0.0005
        mock_eval.return_value = (EvaluationScore(score=90.0, approved=True), 50, 0.0005)
        
        # Summarizer (Embedding): 20 tokens, 0.0002
        mock_sum.return_value = (None, 20, 0.0002)

        # Invoca o grafo (patch time para simular tempo)
        with patch("time.time", side_effect=[0.0, 1.5, 3.0, 4.5, 6.0]):
            final_state = self.app_graph.invoke(self.initial_state)

        # Tokens: 100(R) + 500(E) + 50(Eval) + 20(Sum/Emb) = 670
        self.assertEqual(final_state["total_tokens"], 670)
        # Cost: 0.001 + 0.005 + 0.0005 + 0.0002 = 0.0067
        self.assertAlmostEqual(final_state["total_cost"], 0.0067)
        
        # Verifica se o sumarizador recebeu o valor acumulado corretamente
        _, kwargs = mock_sum.call_args
        self.assertEqual(kwargs.get("cost_tokens"), 650) # R+E+Eval
        self.assertAlmostEqual(kwargs.get("cost_usd"), 0.0065)

if __name__ == "__main__":
    unittest.main()
