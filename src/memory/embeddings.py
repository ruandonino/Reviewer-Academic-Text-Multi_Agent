from typing import Tuple
from src.utils.llm_client import safe_embedding as embedding
from src.utils.llm_client import calculate_completion_cost, safe_completion as completion
from src.config import settings
from src.utils.logger import get_logger

logger = get_logger()

def _estimate_tokens(text: str) -> int:
    """Estimativa rápida: ~3.5 caracteres por token."""
    return len(text) // 3

def gerar_embedding(texto: str) -> Tuple[list[float], int, float]:
    """
    Gera o embedding para um texto usando LiteLLM (Etapa 2/6).
    Se o texto for maior que 8192 tokens, sumariza-o antes de enviar para evitar erro 400.
    Retorna (vetor, tokens, cost).
    """
    total_cost = 0.0
    
    # Verifica o limite de tokens (vamos usar 8000 como margem de segurança)
    estimated_tokens = _estimate_tokens(texto)
    if estimated_tokens > 8000:
        logger.warning(f"Texto muito longo para embedding (estimativa: {estimated_tokens} tokens). Sumarizando antes...")
        try:
            prompt = f"Resuma o texto abaixo detalhadamente para que ele possa ser indexado em um banco de dados vetorial, mantendo os conceitos chave, mas reduzindo o tamanho total para no máximo 6000 tokens.\n\nTexto:\n{texto}"
            
            # Usando um modelo rápido para resumir, como o configurado para o sintetizador
            response_comp = completion(
                model=settings.synthesizer_model,
                messages=[{"role": "user", "content": prompt}]
            )
            texto = response_comp.choices[0].message.content.strip()
            
            # Adiciona o custo da sumarização prévia
            try:
                comp_cost = calculate_completion_cost(response_comp, settings.synthesizer_model)
                total_cost += comp_cost
            except Exception as cost_error:
                logger.warning(f"Não foi possível calcular o custo da sumarização para embedding: {cost_error}")
                
            logger.info("Texto sumarizado com sucesso para o embedding.")
        except Exception as e:
            logger.error(f"Erro ao tentar sumarizar texto longo para embedding: {e}")
            # Se falhar a sumarização, tenta enviar truncado como último recurso
            texto = texto[:28000] # ~8000 tokens

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
        emb_cost = (tokens / 1_000_000) * settings.embedding_cost_per_million_tokens
        total_cost += emb_cost
            
        return vector, tokens, total_cost
    except Exception as e:
        logger.error(f"Erro ao gerar embedding: {e}")
        return [], 0, 0.0
