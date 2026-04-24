import os
import sys
import time

# Adiciona a raiz do projeto ao sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.models.section import Section
from src.models.review import ReviewResult, Observation
from src.models.router import RouterDecision, ModelAllocation
from src.agents.summarizer_agent import summarize_and_index
from src.memory.vector_db import vector_db
from src.utils.logger import get_logger
from dotenv import load_dotenv

load_dotenv()
logger = get_logger()

def test_summarizer_integration():
    if not os.getenv("GEMINI_API_KEY"):
        logger.error("GEMINI_API_KEY não encontrada. O teste do Sumarizador usando Gemini será cancelado.")
        return

    logger.info("=== Iniciando Teste de Integração do Agente Sumarizador ===")

    # 1. Criação dos dados de entrada (Mocks que representam o fim da Etapa 5)
    
    # Uma seção original um pouco longa para testar a sumarização
    target_section = Section(
        type="referencial teórico",
        position=2,
        text="""
A inteligência artificial (IA) tem um longo histórico de desenvolvimentos que culminaram nos atuais Grandes Modelos de Linguagem (LLMs).
No início, os sistemas especialistas dependiam de regras rígidas e lógicas simbólicas. No entanto, com o aumento da capacidade computacional
e da disponibilidade de dados, as Redes Neurais Artificiais (RNAs) ganharam destaque, em especial a arquitetura Transformer apresentada por
Vaswani et al. (2017). Esta arquitetura, baseada puramente em mecanismos de atenção (self-attention), permitiu o processamento paralelo de
sequências de texto e revolucionou o processamento de linguagem natural (PLN).
Os sistemas multiagentes (SMAs) consistem em múltiplos agentes computacionais que interagem entre si para resolver problemas complexos.
A combinação de LLMs com SMAs permite que diferentes modelos assumam papéis distintos, como revisor, crítico ou validador, aumentando a
acurácia das respostas e mitigando o fenômeno de alucinação frequentemente observado em modelos de linguagem autônomos.
        """
    )

    # A revisão final aprovada
    approved_review = ReviewResult(
        general_comments="O referencial teórico está bem fundamentado, mas carece de algumas citações mais recentes sobre SMAs e LLMs.",
        observations=[
            Observation(
                quote="mitigando o fenômeno de alucinação",
                issue="A afirmação é forte e precisa de uma citação recente de um estudo que comprove essa mitigação via SMAs.",
                suggestion="Adicione uma citação (ex: Wang et al., 2023) ao final do parágrafo.",
                type="Normativa"
            )
        ]
    )

    # A decisão de arquitetura usada
    router_decision = RouterDecision(
        architecture="Debate",
        models=[
            ModelAllocation(agent_name="debatedor_1", model_id="gemini/gemini-2.5-flash-lite"),
            ModelAllocation(agent_name="debatedor_2", model_id="gemini/gemma-3-27b-it"),
            ModelAllocation(agent_name="juiz", model_id="gemini/gemini-2.5-flash-lite")
        ],
        reasoning="Arquitetura de debate escolhida para revisão mais profunda e imparcial.",
        system_prompt="Atue como revisor acadêmico."
    )

    final_score = 90.0
    cost_tokens = 5432
    cost_usd = 0.054

    # 2. Executando o Agente Sumarizador (A Etapa 6 real)
    logger.info("Chamando summarize_and_index...")
    start_time = time.time()
    
    record = summarize_and_index(
        section=target_section,
        review=approved_review,
        decision=router_decision,
        score=final_score,
        cost_tokens=cost_tokens,
        cost_usd=cost_usd
    )
    
    end_time = time.time()

    # 3. Validando o Output e o VectorDB
    logger.info("\n--- RESULTADOS DA SUMARIZAÇÃO ---")
    logger.info(f"Tempo de geração e indexação: {end_time - start_time:.2f}s")
    logger.info(f"ID Gerado: {record.id}")
    logger.info(f"Resumo Gerado (LLM):\n{record.text_summary}\n")
    
    # Testando se o registro foi de fato pro banco vetorial consultando ele próprio!
    logger.info("--- TESTANDO A RECUPERAÇÃO (RAG) DO NOVO REGISTRO ---")
    logger.info("Consultando o banco vetorial para o texto recém-inserido...")
    
    history_retrieved = vector_db.retrieve_context(target_section.text, target_section.type, k=1)
    
    if history_retrieved:
        found_meta = history_retrieved[0].get("metadata", {})
        found_id = history_retrieved[0].get("id")
        
        logger.info(f"Registro recuperado com sucesso!")
        logger.info(f"ID Recuperado: {found_id} (Correto? {found_id == record.id})")
        logger.info(f"Score Recuperado: {found_meta.get('evaluation_score')} (Correto? {found_meta.get('evaluation_score') == 90.0})")
        logger.info(f"Arquitetura Recuperada: {found_meta.get('architecture_used')} (Correto? {found_meta.get('architecture_used') == 'Debate'})")
        
    else:
        logger.error("Falha! O registro não pôde ser recuperado do ChromaDB.")

    logger.info("\n=== Teste de Integração do Sumarizador Concluído ===")

if __name__ == "__main__":
    test_summarizer_integration()