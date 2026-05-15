import os
import sys
import uuid

# Adds the project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.models.summary import SummaryRecord
from src.models.review import ReviewResult, Observation
from src.memory.vector_db import vector_db
from src.memory import embeddings
from src.utils.logger import get_logger

logger = get_logger()

from typing import Tuple

# Mocking embedding function to run test without requiring OpenAI API Key
def mock_gerar_embedding(texto: str) -> Tuple[list[float], int, float]:
    """Mock for generating embedding based on text length (dummy vector)"""
    import math
    vector = [float(len(texto)) * math.sin(i) for i in range(1536)]
    # Normalize
    norm = math.sqrt(sum([x**2 for x in vector]))
    if norm == 0:
        return [0.0] * 1536, 10, 0.001
    return [x / norm for x in vector], 10, 0.001

def run_test():
    # Override the embedding generator se não houver chave
    if not os.getenv("OPENAI_API_KEY"):
        logger.warning("OPENAI_API_KEY não encontrada. Usando mock de embeddings para testar o RAG.")
        # Patch local na instancia e no modulo global
        embeddings.gerar_embedding = mock_gerar_embedding
        import src.memory.vector_db
        src.memory.vector_db.gerar_embedding = mock_gerar_embedding
    
    logger.info("=== Início do Teste do Sistema RAG ===")
    
    # 1. Criação de registros mockados para o Histórico (Memory)
    review_mock = ReviewResult(
        general_comments="Comentário geral mockado para testes de contexto.",
        observations=[
            Observation(
                quote="Trecho mock",
                issue="Problema na norma",
                suggestion="Sugerido arrumar isso",
                type="Normativa"
            )
        ]
    )
    
    record_1 = SummaryRecord(
        id=str(uuid.uuid4()),
        section_type="introdução",
        text_content="Este trabalho discute a implementação de sistemas multiagentes baseados em LangGraph. Focamos em avaliação iterativa e roteamento.",
        text_summary="O texto introduz o uso de sistemas multiagentes e LangGraph para avaliação de textos.",
        approved_review=review_mock,
        architecture_used="Single",
        models_used=["gpt-4o"],
        evaluation_score=85.0,
        cost_tokens=1500,
        cost_usd=0.015
    )

    record_2 = SummaryRecord(
        id=str(uuid.uuid4()),
        section_type="introdução",
        text_content="Nesta pesquisa, apresentamos uma solução de revisão acadêmica usando inteligência artificial e vetores semânticos com ChromaDB.",
        text_summary="Apresentação de IA e bancos de dados vetoriais para revisão acadêmica.",
        approved_review=review_mock,
        architecture_used="Ensemble",
        models_used=["gemini/gemini-2.5-flash-lite", "claude-3-5-sonnet-20241022"],
        evaluation_score=95.0,
        cost_tokens=3000,
        cost_usd=0.030
    )
    
    record_3 = SummaryRecord(
        id=str(uuid.uuid4()),
        section_type="metodologia",
        text_content="Para a extração, utilizamos o Docling e o MarkItDown para gerar o Markdown a partir de arquivos PDF estruturados.",
        text_summary="Utilização de bibliotecas Python para parsing de PDFs em Markdown.",
        approved_review=review_mock,
        architecture_used="Single",
        models_used=["gpt-4o"],
        evaluation_score=78.0,
        cost_tokens=1200,
        cost_usd=0.012
    )
    
    # 2. Indexando no VectorDB
    logger.info("Indexando registros mockados...")
    vector_db.index_record(record_1)
    vector_db.index_record(record_2)
    vector_db.index_record(record_3)
    
    logger.info("---")
    
    # 3. Testando a Recuperação (Retrieve)
    query_text = "Esta introdução visa descrever os conceitos de agentes baseados em LangGraph e avaliação de textos usando IA."
    query_type = "introdução"
    
    logger.info(f"Buscando contexto para o tipo '{query_type}'...")
    historico = vector_db.retrieve_context(query_text, query_type, k=2)
    
    logger.info(f"Resultados Recuperados: {len(historico)}")
    for i, h in enumerate(historico):
        meta = h.get('metadata', {})
        logger.info(f"[{i+1}] ID: {h.get('id')}")
        logger.info(f"    Resumo: {meta.get('text_summary')}")
        logger.info(f"    Score: {meta.get('evaluation_score')} | Arquitetura: {meta.get('architecture_used')}")
        
    # Verificar a filtragem: não deve retornar o "record_3" (metodologia)
    all_intro = all(h.get('metadata', {}).get('section_type') == "introdução" for h in historico)
    if not all_intro:
        logger.error("Falha na filtragem por categoria! Resultado inesperado.")
    else:
        logger.info("Filtro por categoria funcionou corretamente.")
    
    logger.info("=== Teste do RAG Concluído com Sucesso ===")

if __name__ == "__main__":
    run_test()
