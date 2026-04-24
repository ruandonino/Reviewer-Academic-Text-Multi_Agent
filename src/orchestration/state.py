import operator
from typing import Annotated, Dict, Any, List, Optional
from typing_extensions import TypedDict
from src.models.section import Section
from src.models.router import RouterDecision
from src.models.review import ReviewResult, EvaluationScore

class ReviewState(TypedDict):
    """
    Estado do grafo para a revisão de UMA seção específica.
    """
    section: Section
    
    # Controle de iteração
    attempts: int
    is_approved: bool
    
    # Histórico RAG
    historical_context: List[Dict[str, Any]]
    
    # Decisão atual do Roteador
    current_decision: Optional[RouterDecision]
    
    # Revisão atual e avaliação
    current_review: Optional[ReviewResult]
    current_evaluation: Optional[EvaluationScore]
    
    # Melhor resultado até o momento (fallback if T_max reached without approval)
    best_score: float
    best_review: Optional[ReviewResult]
    best_decision: Optional[RouterDecision]
