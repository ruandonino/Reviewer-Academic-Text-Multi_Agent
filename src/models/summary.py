from pydantic import BaseModel, Field
from typing import List, Dict, Any
from .review import ReviewResult

class SummaryRecord(BaseModel):
    """
    Registro para o banco vetorial e memória episódica (Etapa 6)
    """
    id: str = Field(description="Identificador único da execução (UUID).")
    section_type: str = Field(description="O tipo canônico da seção para filtragem (tipo_i).")
    text_content: str = Field(description="O texto integral da seção (texto_i) usado para busca vetorial.")
    text_summary: str = Field(description="Síntese semântica compacta do conteúdo textual.")
    approved_review: ReviewResult = Field(description="A revisão aprovada na íntegra (rev_i).")
    architecture_used: str = Field(description="Topologia multiagente empregada (alpha_i).")
    models_used: List[str] = Field(description="Identificadores dos modelos LLM alocados (mu_i).")
    evaluation_score: float = Field(description="Nota de qualidade atribuída pelo Avaliador (nota_i).")
    cost_tokens: int = Field(description="Custo computacional acumulado expresso em tokens consumidos.")
    cost_usd: float = Field(description="Custo monetário estimado em dólares.")
