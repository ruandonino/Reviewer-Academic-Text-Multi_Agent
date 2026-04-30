from pydantic import BaseModel, Field
from typing import List, Optional

class Observation(BaseModel):
    quote: str = Field(description="A referência ou o trecho que apresenta a falha.")
    issue: str = Field(description="Descrição do problema normativo ou semântico identificado.")
    suggestion: str = Field(description="Sugestão acionável de melhoria.")
    type: str = Field(description="Tipo da observação: 'Normativa' ou 'Semântica'", enum=["Normativa", "Semântica"])

class ReviewResult(BaseModel):
    """
    Estrutura da revisão produzida (rev_i)
    """
    general_comments: str = Field(description="Visão geral e comentários transversais da seção.")
    observations: List[Observation] = Field(description="Lista de apontamentos detalhados.")

class EvaluationScore(BaseModel):
    """
    Resultado do Agente Avaliador (Etapa 5)
    """
    score: float = Field(description="Nota contínua de 0 a 100", ge=0.0, le=100.0)
    approved: bool = Field(description="Indicador se a nota é >= ao limiar theta.")
