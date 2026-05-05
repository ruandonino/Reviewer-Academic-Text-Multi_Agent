import os
import sys
import unittest
from unittest.mock import patch

# Adiciona a raiz do projeto ao sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.models.section import Section
from src.agents.router_agent import route_section
from src.utils.logger import get_logger

logger = get_logger()

# Configuração para desativar logs muito verbosos
logger.remove()
logger.add(sys.stdout, level="INFO")

class TestRouterHistoricalRouting(unittest.TestCase):
    """
    Testes de integração para validar se o LLM do Agente Roteador 
    escolhe arquiteturas e modelos corretamente com base no histórico fornecido.
    
    Atenção: Este teste realiza chamadas REAIS para a API (via LiteLLM).
    Portanto, pode haver leve não-determinismo nas respostas. As asserções 
    são flexíveis onde necessário, focando na lógica principal.
    """

    def setUp(self):
        # Verifica se temos a chave de API para rodar o modelo do roteador
        if not os.getenv("GEMINI_API_KEY"):
            self.skipTest("GEMINI_API_KEY não encontrada. Pulando teste que faz chamada real ao LLM.")

    def create_mock_history(self, architecture, score, cost, models="gemini/gemma-3-27b-it"):
        return [{
            "metadata": {
                "evaluation_score": score,
                "architecture_used": architecture,
                "models_used": models,
                "cost_usd": cost,
                "text_summary": "Resumo simulado para induzir o comportamento do roteador."
            }
        }]

    @patch("src.agents.router_agent.vector_db.retrieve_context")
    def test_scenario_1_simple_text_cheap_success(self, mock_retrieve):
        """
        Cenário 1: Texto simples e histórico mostra que 'Single' com modelo barato teve sucesso.
        Esperado: O roteador deve escolher a arquitetura 'Single' e um modelo barato para economizar.
        """
        logger.info("\n--- TESTE 1: Texto Simples + Sucesso Barato no Histórico ---")
        mock_retrieve.return_value = self.create_mock_history("Single", 95.0, 0.001)
        
        section = Section(
            type="introdução",
            position=1,
            text="Esta é uma introdução muito simples e direta. O objetivo deste trabalho é analisar dados públicos."
        )
        
        decision, history, tokens, cost = route_section(section)
        
        logger.info(f"Decisão: Arquitetura={decision.architecture}")
        logger.info(f"Modelos={decision.models}")
        logger.info(f"Justificativa={decision.reasoning}")
        
        self.assertEqual(decision.architecture.lower(), "single")
        self.assertEqual(len(decision.models), 1)

    @patch("src.agents.router_agent.vector_db.retrieve_context")
    def test_scenario_2_complex_text_debate_success(self, mock_retrieve):
        """
        Cenário 2: Texto complexo e histórico mostra que 'Single' falhou (nota 50), 
                   mas 'Debate' teve sucesso (nota 95).
        Esperado: Roteador deve escolher a arquitetura 'Debate'.
        """
        logger.info("\n--- TESTE 2: Texto Complexo + Falha no Single + Sucesso no Debate ---")
        mock_retrieve.return_value = [
            {
                "metadata": {
                    "evaluation_score": 50.0,
                    "architecture_used": "Single",
                    "models_used": "gemini/gemma-3-27b-it",
                    "cost_usd": 0.002,
                    "text_summary": "Falhou em identificar nuances metodológicas."
                }
            },
            {
                "metadata": {
                    "evaluation_score": 95.0,
                    "architecture_used": "Debate",
                    "models_used": "gemini/gemma-3-27b-it,gemini/gemma-4-31b-it",
                    "cost_usd": 0.02,
                    "text_summary": "Debate conseguiu aprofundar na complexidade metodológica."
                }
            }
        ]
        
        section = Section(
            type="metodologia",
            position=2,
            text="A metodologia adotada é mista e multifacetada, envolvendo triangulação de dados quali-quanti complexos, equações de regressão não-linear e análise fatorial exploratória. As premissas assumem heterocedasticidade."
        )
        
        decision, history, tokens, cost = route_section(section)
        
        logger.info(f"Decisão: Arquitetura={decision.architecture}")
        logger.info(f"Modelos={decision.models}")
        logger.info(f"Justificativa={decision.reasoning}")
        
        self.assertEqual(decision.architecture.lower(), "debate")
        self.assertEqual(len(decision.models), 3) # Debate exige debatedor_A, debatedor_B, juiz

    @patch("src.agents.router_agent.vector_db.retrieve_context")
    def test_scenario_3_normative_strictness_star(self, mock_retrieve):
        """
        Cenário 3: Seção com muitas regras de formatação/ABNT. 
        Histórico mostra que 'Star' (que tem especialista_normas) foi excelente.
        Esperado: Roteador deve escolher 'Star'.
        """
        logger.info("\n--- TESTE 3: Regras Rigorosas + Sucesso na Arquitetura Star ---")
        mock_retrieve.return_value = self.create_mock_history("Star", 98.0, 0.015, "gemini/gemma-4-31b-it")
        
        section = Section(
            type="referências",
            position=5,
            text="SILVA, J. A. O uso de IA. São Paulo: Editora USP, 2020. [Faltam detalhes de formatação ABNT rigorosa nesta seção]."
        )
        
        decision, history, tokens, cost = route_section(section)
        
        logger.info(f"Decisão: Arquitetura={decision.architecture}")
        logger.info(f"Modelos={decision.models}")
        logger.info(f"Justificativa={decision.reasoning}")
        
        self.assertEqual(decision.architecture.lower(), "star")
        self.assertEqual(len(decision.models), 3) # Star exige especialista_normas, especialista_semantica, consolidador

    @patch("src.agents.router_agent.vector_db.retrieve_context")
    def test_scenario_4_high_complexity_ensemble(self, mock_retrieve):
        """
        Cenário 4: Discussão e Conclusão altamente densa. Histórico aponta que apenas 
        'Ensemble' conseguiu nota alta (96). Single e Chain tiraram notas baixas (55, 60).
        Esperado: Roteador escolhe 'Ensemble' com modelos capazes.
        """
        logger.info("\n--- TESTE 4: Alta Complexidade + Ensemble como única solução ---")
        mock_retrieve.return_value = [
            {"metadata": {"evaluation_score": 55.0, "architecture_used": "Single", "cost_usd": 0.003}},
            {"metadata": {"evaluation_score": 60.0, "architecture_used": "Chain", "cost_usd": 0.009}},
            {"metadata": {"evaluation_score": 96.0, "architecture_used": "Ensemble", "cost_usd": 0.05, "models_used": "gpt-4o,claude-3-5-sonnet-20241022"}}
        ]
        
        section = Section(
            type="discussão_e_conclusão",
            position=6,
            text="Os resultados indicam uma convergência assintótica divergente do postulado de Einstein. Isso requer uma análise profunda do porquê os modelos falharam na borda de decisão. A consolidação destas descobertas com a literatura global é imperativa e complexa."
        )
        
        decision, history, tokens, cost = route_section(section)
        
        logger.info(f"Decisão: Arquitetura={decision.architecture}")
        logger.info(f"Modelos={decision.models}")
        logger.info(f"Justificativa={decision.reasoning}")
        
        self.assertEqual(decision.architecture.lower(), "ensemble")
        self.assertEqual(len(decision.models), 4) # Ensemble exige votante_1, votante_2, votante_3, sintetizador_ensemble

if __name__ == "__main__":
    unittest.main(verbosity=2)
