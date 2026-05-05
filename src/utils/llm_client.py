import time
import threading
import litellm
import re
from litellm import completion as litellm_completion
from litellm import embedding as litellm_embedding
from src.utils.logger import get_logger
from src.config import settings

# Registra preços customizados baseados na configuração central
_custom_pricing = {}
for model_id, description in settings.available_models.items():
    match = re.search(r'Input:\s*(?:\\\\\$|\\\$|\$)?([0-9.]+)/1M,\s*Output:\s*(?:\\\\\$|\\\$|\$)?([0-9.]+)/1M', description)
    if match:
        input_cost = float(match.group(1)) / 1_000_000
        output_cost = float(match.group(2)) / 1_000_000
        
        model_name = model_id.split("/")[-1] if "/" in model_id else model_id
        
        # Registra com o nome original
        _custom_pricing[model_id] = {
            "max_tokens": 32768,
            "input_cost_per_token": input_cost,
            "output_cost_per_token": output_cost,
            "lite_model_name": model_id
        }
        
        # Registra apenas com o nome do modelo (útil para retornos de API compatíveis com OpenAI)
        _custom_pricing[model_name] = {
            "max_tokens": 32768,
            "input_cost_per_token": input_cost,
            "output_cost_per_token": output_cost,
            "lite_model_name": model_name
        }
        
        # Se for dashscope/qwen, registra o alias openai/ também
        if "dashscope" in model_id.lower() or "qwen" in model_id.lower():
            _custom_pricing[f"openai/{model_name}"] = {
                "max_tokens": 32768,
                "input_cost_per_token": input_cost,
                "output_cost_per_token": output_cost,
                "lite_model_name": f"openai/{model_name}"
            }

if _custom_pricing:
    litellm.register_model(_custom_pricing)

logger = get_logger()

_api_lock = threading.Lock()
_wait_until = 0.0

def _safe_call(api_func, *args, **kwargs):
    """
    Função base para chamadas thread-safe para litellm.
    """
    global _wait_until
    max_retries = 4  # 1 tentativa inicial + 3 retentativas
    
    for attempt in range(max_retries):
        with _api_lock:
            now = time.time()
            if now < _wait_until:
                sleep_time = _wait_until - now
                logger.info(f"Chamada pendente aguardando cooldown de {sleep_time:.1f}s da API...")
                time.sleep(sleep_time)
                
        try:
            return api_func(*args, **kwargs)
            
        except Exception as e:
            if attempt < max_retries - 1:
                with _api_lock:
                    now = time.time()
                    if now >= _wait_until:
                        logger.warning(f"Erro na API detectado. Pausando TODAS as chamadas por 60 segundos. Detalhes: {e}")
                        _wait_until = now + 60.0
                
                time_to_sleep = max(0, _wait_until - time.time())
                if time_to_sleep > 0:
                    time.sleep(time_to_sleep)
            else:
                logger.error(f"Falha definitiva na API após {max_retries} tentativas: {e}")
                raise e

def safe_completion(*args, **kwargs):
    model = kwargs.get("model", "")
    if args and not model:
        model = args[0]
        
    if "dashscope" in model.lower() or "qwen" in model.lower():
        import os
        model_name = model.split("/")[-1] if "/" in model else model
        kwargs["model"] = f"openai/{model_name}"
        kwargs["api_base"] = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
        kwargs["api_key"] = os.getenv("DASHSCOPE_API_KEY")
        
        # Se o modelo original foi passado via args (posicional), removemos ele para forçar o uso dos kwargs
        if args:
            args = args[1:]
            
    return _safe_call(litellm_completion, *args, **kwargs)

def safe_embedding(*args, **kwargs):
    return _safe_call(litellm_embedding, *args, **kwargs)
