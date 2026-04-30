from pydantic import BaseModel, Field
from typing import List, Dict, Any

class ModelAllocation(BaseModel):
    agent_name: str = Field(description="Nome do agente na topologia (ex: 'revisor_1', 'avaliador')")
    model_id: str = Field(description="Identificador do modelo no LiteLLM (ex: 'gpt-4o', 'gemini/gemini-2.5-flash-lite')")

class RouterDecision(BaseModel):
    """
    Resposta estruturada do Roteador (Etapa 3)
    """
    architecture: str = Field(
        description="Topologia selecionada (ex: 'star', 'debate', 'chain', 'ensemble', 'single')"
    )
    models: List[ModelAllocation] = Field(description="Alocação de modelos LLM (mu_i) para cada agente.")
    reasoning: str = Field(description="Justificativa da escolha considerando contexto histórico e custo.")
    system_prompt: str = Field(description="O system prompt P_i gerado para os revisores, enriquecido com RAG.")
