from src.utils.llm_client import safe_embedding as embedding
from src.config import settings
from src.utils.logger import get_logger

logger = get_logger()

def gerar_embedding(texto: str) -> list[float]:
    """
    Gera o embedding para um texto usando LiteLLM (Etapa 2/6).
    """
    try:
        response = embedding(
            model=settings.embedding_model,
            input=texto
        )
        vector = response.data[0]['embedding']
        return vector
    except Exception as e:
        logger.error(f"Erro ao gerar embedding: {e}")
        return []
