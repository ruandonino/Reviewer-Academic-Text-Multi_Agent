import os
from typing import Dict, List
from pydantic import BaseModel, Field

class Settings(BaseModel):
    # LLM Settings
    openai_api_key: str = Field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))
    gemini_api_key: str = Field(default_factory=lambda: os.getenv("GEMINI_API_KEY", ""))
    dashscope_api_key: str = Field(default_factory=lambda: os.getenv("DASHSCOPE_API_KEY", ""))
    anthropic_api_key: str = Field(default_factory=lambda: os.getenv("ANTHROPIC_API_KEY", ""))

    # Model Defaults
    embedding_model: str = "gemini/gemini-embedding-2" # Modelo de embedding do Google atualizado
    #router_model: str = "gemini/gemma-3-27b-it"
    router_model: str = "gemini/gemini-2.5-flash-lite"
    evaluator_model: str = "gemini/gemini-2.5-flash-lite"
    synthesizer_model: str = "gemini/gemini-2.5-flash-lite"

    # Parser Default ("mineru", "docling", "markitdown")
    default_parser: str = "mineru"

    # System Thresholds
    quality_threshold: float = 85.0
    max_attempts: int = 3

    # ChromaDB Settings
    chroma_db_dir: str = "./chroma_db_gemini2"
    chroma_collection_name: str = "reviews_history"

    # RAG Settings
    k_nearest_neighbors: int = 3

    # Available Models
    
    # Available Architectures and their required agents
    available_architectures: Dict[str, List[str]] = {
        "single": ["revisor_unico"],
        "star": ["especialista_normas", "especialista_semantica", "consolidador"],
        "chain": ["revisor_inicial", "revisor_intermediario", "refinador"],
        "debate": ["debatedor_A", "debatedor_B", "juiz"],
        "ensemble": ["votante_1", "votante_2", "votante_3", "sintetizador_ensemble"]
    }

    available_models: Dict[str, str] = {
        "gemini/gemma-4-31b-it": "Custo BAIXO. (Input: \$0.0/1M, Output: \$0.0/1M tokens). Modelo open-weight eficiente e rápido. Indicado para tarefas de baixa e média complexidade.",
        
        "gemini/gemini-2.5-flash-lite": "Custo BAIXO. (Input: \$0.10/1M, Output: \$0.40/1M tokens). Modelo ultra-rápido do Google focado em eficiência. Ideal para tarefas que exigem alta velocidade de resposta e baixo custo operacional.",
        
        #"gemini/gemini-3.1-pro-preview": "Custo ALTO. (Input: \$2.00/1M, Output: \$12.00/1M tokens). Modelo de fronteira do Google com altíssima capacidade de raciocínio complexo e janela de contexto massiva. Indicado para tarefas que exigem análise aprofundada, síntese de grandes volumes de informação e alto rigor.",
        
        "gemini/gemini-3.1-flash-lite-preview": "Custo MÉDIO. (Input: \$0.25/1M, Output: \$1.50/1M tokens). Modelo ágil de nova geração, otimizado para balancear velocidade e inteligência. Versátil para uma ampla gama de tarefas e processamento contínuo de dados.",
        
        "openai/gpt-4.1-nano": "Custo BAIXO. (Input: \$0.10/1M, Output: \$0.40/1M tokens). Modelo rápido e leve da OpenAI, oferecendo bom desempenho com custo reduzido. Útil para tarefas rápidas e de baixa complexidade.",
        
        #"openai/gpt-5.5": "Custo ALTO. (Input: \$5.00/1M, Output: \$15.00/1M tokens). Modelo de fronteira da OpenAI com o mais alto nível de inteligência. Excelente para raciocínio lógico profundo e tarefas que demandam máxima precisão e qualidade.",
        
        "openai/gpt-5.4-mini": "Custo MÉDIO. (Input: \$0.75/1M, Output: \$4.50/1M tokens). Modelo intermediário da OpenAI de alto desempenho, oferecendo um balanço ideal entre qualidade e custo. Adequado para uma variedade de tarefas de complexidade moderada.",
        
        #"anthropic/claude-haiku-4-5": "Custo ALTO. (Input: \$1.00/1M, Output: \$5.00/1M tokens). Modelo extremamente ágil da Anthropic, otimizado para velocidade de resposta. Ótimo para tarefas que exigem baixa latência e processamento de textos longos.",
        
        #"anthropic/claude-sonnet-4-6": "Custo ALTO. (Input: \$3.00/1M, Output: \$15.00/1M tokens). Modelo premium da Anthropic com altíssima capacidade analítica e compreensão profunda de nuances. Excelente para tarefas complexas que exigem raciocínio sofisticado.",
        
        "dashscope/qwen3.5-flash-2026-02-23": "Custo BAIXO. (Input: \$0.05/1M, Output: \$0.20/1M tokens). Modelo robusto da Alibaba Cloud, eficiente para tarefas gerais e análises diversificadas com baixo custo.",
        
        #"dashscope/qwen3.6-35b-a3b": "Custo MÉDIO. (Input: \$0.25/1M, Output: \$1.48/1M tokens). Modelo avançado da família Qwen, oferecendo maior capacidade de compreensão de contexto em relação à versão Turbo. Excelente custo-benefício para tarefas que exigem um nível superior de detalhamento."
    }

    def validate_prompts_structure(self):
        prompts_dir = os.path.join("src", "prompts")
        if not os.path.exists(prompts_dir):
            return

        for section in os.listdir(prompts_dir):
            section_path = os.path.join(prompts_dir, section)
            if not os.path.isdir(section_path):
                continue

            for arch_name, agents in self.available_architectures.items():
                arch_path = os.path.join(section_path, arch_name)
                if not os.path.exists(arch_path):
                    raise ValueError(f"ERRO DE CONFIGURAÇÃO: Arquitetura '{arch_name}' definida no config.py, mas a pasta correspondente não foi encontrada em '{arch_path}'.")

                for agent in agents:
                    agent_file = os.path.join(arch_path, f"{agent}.md")
                    if not os.path.exists(agent_file):
                        raise ValueError(f"ERRO DE CONFIGURAÇÃO: Agente '{agent}' configurado na arquitetura '{arch_name}', mas o arquivo de prompt não existe em '{agent_file}'.")

settings = Settings()
settings.validate_prompts_structure()
