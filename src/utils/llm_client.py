import time
import threading
from litellm import completion as litellm_completion
from litellm import embedding as litellm_embedding
from src.utils.logger import get_logger

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
    return _safe_call(litellm_completion, *args, **kwargs)

def safe_embedding(*args, **kwargs):
    return _safe_call(litellm_embedding, *args, **kwargs)
