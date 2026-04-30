import os
from typing import Dict, List
from pydantic import BaseModel, Field

class Settings(BaseModel):
    # LLM Settings
    openai_api_key: str = Field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))
    gemini_api_key: str = Field(default_factory=lambda: os.getenv("GEMINI_API_KEY", ""))
    anthropic_api_key: str = Field(default_factory=lambda: os.getenv("ANTHROPIC_API_KEY", ""))

    # Model Defaults
    embedding_model: str = "gemini/gemini-embedding-2" # Modelo de embedding do Google atualizado

    # Parser Default ("mineru", "docling", "markitdown")
    default_parser: str = "mineru"

    # System Thresholds
    quality_threshold: float = 80.0
    max_attempts: int = 3

    # ChromaDB Settings
    chroma_db_dir: str = "./chroma_db_gemini2"
    chroma_collection_name: str = "reviews_history"

    # RAG Settings
    k_nearest_neighbors: int = 3

    # Available Models
    available_models: Dict[str, str] = {
        "gemini/gemma-3-27b-it": "Custo BAIXO. Modelo open-weight eficiente e rápido. Ideal para tarefas de baixa e média complexidade, como revisões normativas simples ou roteamento inicial, sendo a escolha prioritária quando o orçamento é restrito ou a seção é trivial.",
        "gemini/gemma-4-31b-it": "Custo MÉDIO. Modelo balanceado, com excelente capacidade de raciocínio lógico e grande contexto. Ideal para a maioria das tarefas de revisão acadêmica, oferecendo o melhor custo-benefício geral.",
        #"gemini/gemini-2.5-flash-lite": "Custo MÉDIO. Modelo balanceado, com excelente capacidade de raciocínio lógico e grande contexto. Ideal para a maioria das tarefas de revisão acadêmica, oferecendo o melhor custo-benefício geral.",
        "claude-3-5-sonnet-20241022": "Custo ALTO. Modelo premium com altíssima capacidade analítica, compreensão profunda de nuances semânticas e estruturais. Ideal para tarefas muito complexas, como consolidar debates de múltiplos agentes ou avaliar metodologias densas.",
        "gpt-4o": "Custo ALTO. Modelo de fronteira de alto desempenho, excelente para raciocínio lógico complexo e cumprimento estrito de regras (como normas da ABNT rigorosas). Use com moderação, apenas quando alto rigor for necessário."
    }

    # Available Architectures and their required agents
    available_architectures: Dict[str, List[str]] = {
        "single": ["revisor_unico"],
        "star": ["especialista_normas", "especialista_semantica", "consolidador"],
        "chain": ["revisor_inicial", "revisor_intermediario", "refinador"],
        "debate": ["debatedor_A", "debatedor_B", "juiz"],
        "ensemble": ["votante_1", "votante_2", "votante_3", "sintetizador_ensemble"]
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
