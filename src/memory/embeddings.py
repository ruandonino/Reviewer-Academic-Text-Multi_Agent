from typing import Tuple
from src.utils.llm_client import safe_embedding as embedding
from src.config import settings
from src.utils.logger import get_logger

logger = get_logger()

def gerar_embedding(texto: str) -> Tuple[list[float], int, float]:
    """
    Gera o embedding para um texto usando LiteLLM (Etapa 2/6).
    Retorna (vetor, tokens, cost).
    """
    try:
        model_name = settings.embedding_model.split("/")[-1]
        response = embedding(
            model=f"openai/{model_name}",
            api_base=settings.embedding_api_base,
            api_key=settings.dashscope_api_key,
            input=[texto],
            encoding_format="float"
        )
        
        # Access embedding from data[0] object
        # Some models return objects, others return dicts in litellm, we handle both
        data_obj = response.data[0]
        if isinstance(data_obj, dict):
            vector = data_obj['embedding']
        else:
            vector = data_obj.embedding
            
        tokens = response.usage.total_tokens if hasattr(response, 'usage') and response.usage else 0
        
        # Custo configurado em config.py por 1.000.000 de tokens
        cost = (tokens / 1_000_000) * settings.embedding_cost_per_million_tokens
            
        return vector, tokens, cost
    except Exception as e:
        logger.error(f"Erro ao gerar embedding: {e}")
        return [], 0, 0.0
