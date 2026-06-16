import os
import sys
import time

# Adiciona a raiz do projeto ao sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.models.review import ReviewResult, Observation
from src.agents.synthesizer_agent import synthesize_final_report
from src.utils.logger import get_logger
from dotenv import load_dotenv

load_dotenv()
logger = get_logger()

from src.models.section import Section

def test_synthesizer_integration():
    if not os.getenv("GEMINI_API_KEY"):
        logger.error("GEMINI_API_KEY não encontrada. O teste do Sintetizador usando Gemini será cancelado.")
        return

    logger.info("=== Iniciando Teste de Integração do Agente Sintetizador ===")

    # Criação de um array de revisões simuladas, como se viessem de múltiplas seções processadas.
    
    review_intro = ReviewResult(
        general_comments="A introdução (Seção 1) contextualiza bem o tema, mas apresenta falhas normativas nas citações e um problema semântico na definição do escopo.",
        observations=[
            Observation(
                quote="Segundo (Silva 2021)",
                issue="A formatação da citação indireta está incorreta segundo as normas da ABNT.",
                suggestion="Utilize 'Segundo Silva (2021)'.",
                type="Normativa"
            ),
            Observation(
                quote="Este trabalho foca na inteligência artificial.",
                issue="A afirmação de escopo é muito ampla e não delimita exatamente o que será estudado.",
                suggestion="Especifique que o trabalho foca no uso de Sistemas Multiagentes para revisão de textos.",
                type="Semântica"
            )
        ]
    )

    review_method = ReviewResult(
        general_comments="A seção de metodologia (Seção 3) está razoável, porém carece de fundamentação teórica para as escolhas de arquitetura.",
        observations=[
            Observation(
                quote="Usamos LangGraph para os agentes",
                issue="Falta citar bibliografia que embase o uso de grafos para orquestração de agentes.",
                suggestion="Adicione uma citação referenciando a literatura atual de orquestração de LLMs.",
                type="Normativa"
            ),
            Observation(
                quote="A amostra foi de 10 testes",
                issue="O tamanho da amostra é insuficiente para generalização sem justificativa.",
                suggestion="Justifique o tamanho da amostra ou aumente o número de testes qualitativos.",
                type="Semântica"
            )
        ]
    )

    review_conclusion = ReviewResult(
        general_comments="A conclusão (Seção 5) está sólida, mas não cita as limitações.",
        observations=[
            Observation(
                quote="O sistema superou as expectativas e resolveu todos os problemas.",
                issue="A afirmação é excessivamente conclusiva e ignora possíveis limitações.",
                suggestion="Inclua um parágrafo sobre as limitações encontradas (ex: custo de tokens).",
                type="Semântica"
            )
        ]
    )

    # Lista de revisões parciais com seções correspondentes
    reviews_list = [
        (Section(type="introdução", position=1, text="Texto introdução"), review_intro),
        (Section(type="metodologia", position=2, text="Texto metodologia"), review_method),
        (Section(type="conclusão", position=3, text="Texto conclusão"), review_conclusion)
    ]

    logger.info("Invocando synthesize_final_report...")
    start_time = time.time()
    
    # Executando a etapa 8 real
    final_report, _, _ = synthesize_final_report(reviews_list)
    
    end_time = time.time()

    logger.info(f"\n--- RESULTADO DA SÍNTESE FINAL (Tempo: {end_time - start_time:.2f}s) ---")
    logger.info("\n" + final_report)

    logger.info("\n=== Teste de Integração do Sintetizador Concluído ===")

if __name__ == "__main__":
    test_synthesizer_integration()