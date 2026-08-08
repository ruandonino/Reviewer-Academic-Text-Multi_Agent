import re
import time
import threading
import json
import os
import uuid
from datetime import datetime

import litellm
from litellm import completion as litellm_completion
from litellm import embedding as litellm_embedding

from src.config import settings
from src.utils.logger import get_logger


_PRICE_PATTERN = re.compile(
    r"Input:\s*(?:\\?\$)?([0-9.]+)/1M,\s*Output:\s*(?:\\?\$)?([0-9.]+)/1M"
)


def _model_pricing_aliases(model_id: str) -> list[str]:
    """Returns configured and provider-returned aliases for a model."""
    if not model_id:
        return []

    aliases = [model_id]
    if model_id.startswith("openrouter/"):
        aliases.append(model_id.removeprefix("openrouter/"))
    else:
        aliases.append(f"openrouter/{model_id}")

    versionless = re.sub(r"-20\d{6}$", "", model_id)
    if versionless != model_id:
        aliases.append(versionless)
        if versionless.startswith("openrouter/"):
            aliases.append(versionless.removeprefix("openrouter/"))
        else:
            aliases.append(f"openrouter/{versionless}")

    model_name = model_id.rsplit("/", 1)[-1]
    aliases.append(model_name)

    if model_id.startswith("dashscope/"):
        aliases.append(f"openai/{model_name}")

    if "deepseek-v4-flash" in model_id.lower():
        aliases.extend(
            [
                "openrouter/deepseek-v4-flash",
                "openrouter/deepseek/deepseek-v4-flash",
                "deepseek/deepseek-v4-flash",
            ]
        )

    return list(dict.fromkeys(aliases))


def _configured_pricing() -> dict[str, dict]:
    pricing = {}
    for model_id, description in settings.available_models.items():
        match = _PRICE_PATTERN.search(description)
        if not match:
            continue

        input_cost = float(match.group(1)) / 1_000_000
        output_cost = float(match.group(2)) / 1_000_000
        for alias in _model_pricing_aliases(model_id):
            pricing[alias] = {
                "max_tokens": 65536,
                "input_cost_per_token": input_cost,
                "output_cost_per_token": output_cost,
                "lite_model_name": alias,
            }
    return pricing


_custom_pricing = _configured_pricing()
if _custom_pricing:
    litellm.register_model(_custom_pricing)
    litellm.model_cost.update(_custom_pricing)

logger = get_logger()

_api_lock = threading.Lock()
_wait_until = 0.0
_usage_log_lock = threading.Lock()
_usage_log_path = ""
# Allow long-running synthesis calls to use a larger deadline without changing
# the default for existing executions.
API_TIMEOUT_SECONDS = int(os.getenv("LLM_API_TIMEOUT_SECONDS", "300"))


def start_usage_logging(document_id: str) -> str:
    """Starts an append-only token ledger for one document execution."""
    global _usage_log_path
    log_dir = os.path.join("logs", "token_usage")
    os.makedirs(log_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_document_id = re.sub(r"[^A-Za-z0-9_.-]+", "_", document_id)
    _usage_log_path = os.path.join(log_dir, f"usage_{safe_document_id}_{timestamp}.jsonl")
    return _usage_log_path


def get_usage_log_path() -> str:
    return _usage_log_path


def summarize_usage_log() -> dict:
    """Returns auditable token and cost totals from the current request ledger."""
    summary = {
        "requests": 0,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "cost_usd": 0.0,
        "cost_unavailable_requests": 0,
    }
    if not _usage_log_path or not os.path.exists(_usage_log_path):
        return summary

    with _usage_log_lock:
        with open(_usage_log_path, "r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                entry = json.loads(line)
                summary["requests"] += 1
                summary["prompt_tokens"] += int(entry.get("prompt_tokens") or 0)
                summary["completion_tokens"] += int(entry.get("completion_tokens") or 0)
                summary["total_tokens"] += int(entry.get("total_tokens") or 0)
                if entry.get("cost_usd") is None:
                    summary["cost_unavailable_requests"] += 1
                else:
                    summary["cost_usd"] += float(entry["cost_usd"])
    return summary

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
    kwargs.setdefault("timeout", API_TIMEOUT_SECONDS)
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
    kwargs.setdefault("timeout", API_TIMEOUT_SECONDS)
    return _safe_call(litellm_embedding, *args, **kwargs)

def _usage_value(usage, field: str) -> int:
    if not usage:
        return 0
    value = usage.get(field) if isinstance(usage, dict) else getattr(usage, field, None)
    return int(value or 0)


def _response_model(response) -> str:
    if isinstance(response, dict):
        return response.get("model", "") or ""
    return getattr(response, "model", "") or ""


def _usage_snapshot(response) -> dict:
    usage = response.get("usage") if isinstance(response, dict) else getattr(response, "usage", None)
    prompt_tokens = _usage_value(usage, "prompt_tokens")
    completion_tokens = _usage_value(usage, "completion_tokens")
    total_tokens = _usage_value(usage, "total_tokens") or prompt_tokens + completion_tokens
    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
    }


def _append_usage_log(response, requested_model: str, cost_usd: float | None, cost_source: str, error: str = "") -> None:
    if not _usage_log_path:
        return

    entry = {
        "request_id": str(uuid.uuid4()),
        "timestamp": datetime.now().isoformat(),
        "requested_model": requested_model,
        "response_model": _response_model(response),
        **_usage_snapshot(response),
        "cost_usd": cost_usd,
        "cost_source": cost_source,
        "cost_error": error or None,
    }
    try:
        with _usage_log_lock:
            with open(_usage_log_path, "a", encoding="utf-8") as handle:
                handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as log_error:
        logger.error(f"Falha ao registrar uso de tokens: {log_error}")


def calculate_completion_cost(response, model_id: str = "") -> float:
    """Uses LiteLLM first and configured prices as a deterministic fallback."""
    try:
        cost = float(litellm.completion_cost(completion_response=response))
        _append_usage_log(response, model_id, cost, "litellm")
        return cost
    except Exception as litellm_error:
        usage = _usage_snapshot(response)
        prompt_tokens = usage["prompt_tokens"]
        completion_tokens = usage["completion_tokens"]

        if prompt_tokens or completion_tokens:
            response_model = _response_model(response)
            for alias in _model_pricing_aliases(model_id) + _model_pricing_aliases(response_model):
                price = _custom_pricing.get(alias)
                if price:
                    cost = (
                        prompt_tokens * price["input_cost_per_token"]
                        + completion_tokens * price["output_cost_per_token"]
                    )
                    _append_usage_log(response, model_id, cost, "config_fallback")
                    return cost

        _append_usage_log(response, model_id, None, "unavailable", str(litellm_error))
        raise ValueError(
            f"Não foi possível calcular o custo para os modelos "
            f"'{model_id}' e '{_response_model(response)}'."
        ) from litellm_error
