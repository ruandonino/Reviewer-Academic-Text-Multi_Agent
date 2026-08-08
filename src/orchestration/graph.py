from langgraph.graph import StateGraph, END
from src.orchestration.state import ReviewState
from src.agents.router_agent import route_section
from src.agents.execution.executor import execute_architecture
from src.agents.evaluator_agent import evaluate_review
from src.agents.summarizer_agent import summarize_and_index
from src.config import settings
from src.utils.logger import get_logger
import time
import threading

logger = get_logger()

# --- Sincronização do Roteador ---
first_pass_total = 0
first_pass_routers_done = 0
router_lock = threading.Lock()
router_barrier_event = threading.Event()

# --- Nós do Grafo ---

def router_node(state: ReviewState) -> dict:
    """Nó do Agente Roteador"""
    global first_pass_routers_done
    
    section = state["section"]
    decision, history, tokens, cost = route_section(section)
    
    # Barreira de Sincronização pós-roteador para evitar Rate Limit na 1ª passagem
    if state.get("attempts", 0) == 0 and first_pass_total > 0:
        with router_lock:
            first_pass_routers_done += 1
            if first_pass_routers_done == first_pass_total:
                from src.agents.router_agent import ROUTER_MODEL
                if "gemma" in ROUTER_MODEL.lower():
                    logger.info("Todos os roteadores da 1ª passagem finalizaram. Aguardando 60s para evitar Rate Limit do modelo Roteador (Gemma)...")
                    time.sleep(60)
                router_barrier_event.set()
        
        # Faz as threads (seções) esperarem até que a última destrave o evento
        router_barrier_event.wait()
    
    return {
        "current_decision": decision,
        "historical_context": history,
        "attempts": state.get("attempts", 0) + 1,
        "total_tokens": tokens,
        "total_cost": cost
    }

def execution_node(state: ReviewState) -> dict:
    """Nó de Execução Multiagente"""
    section = state["section"]
    decision = state["current_decision"]
    
    if not decision:
        raise ValueError("Decisão do roteador ausente.")
        
    review, tokens, cost = execute_architecture(decision, section)
    return {
        "current_review": review,
        "total_tokens": tokens,
        "total_cost": cost
    }

def evaluator_node(state: ReviewState) -> dict:
    """Nó do Agente Avaliador"""
    section = state["section"]
    review = state["current_review"]
    decision = state["current_decision"]
    
    if not review:
        raise ValueError("Revisão ausente.")
        
    score, tokens, cost = evaluate_review(section, review)

    # --- Indexação de TODAS as tentativas ---
    # Indexamos a tentativa atual no banco vetorial para o histórico do Roteador
    accumulated_tokens = state.get("total_tokens", 0) + tokens
    accumulated_cost = state.get("total_cost", 0.0) + cost

    _, sum_tokens, sum_cost = summarize_and_index(
        section=section,
        review=review,
        decision=decision,
        score=score.score,
        cost_tokens=accumulated_tokens,
        cost_usd=accumulated_cost,
    )

    total_node_tokens = tokens + sum_tokens
    total_node_cost = cost + sum_cost

    # Atualiza o melhor score se necessário
    best_score = state.get("best_score", -1.0)
    best_review = state.get("best_review")
    best_decision = state.get("best_decision")

    if score.score > best_score:
        best_score = score.score
        best_review = review
        best_decision = decision

    return {
        "current_evaluation": score,
        "is_approved": score.approved,
        "best_score": best_score,
        "best_review": best_review,
        "best_decision": best_decision,
        "total_tokens": total_node_tokens,
        "total_cost": total_node_cost
    }

def summarizer_node(state: ReviewState) -> dict:
    """Nó do Agente Sumarizador (Fim do processo de sucesso)
    Calls summarize_and_index with the best review information.
    """
    # Extract best attempt data from state
    section = state["section"]
    best_review = state.get("best_review")
    best_decision = state.get("best_decision")
    best_score = state.get("best_score")
    total_tokens = state.get("total_tokens", 0)
    total_cost = state.get("total_cost", 0.0)

    # Call summarization and indexing (patched in tests)
    _, sum_tokens, sum_cost = summarize_and_index(
        section=section,
        review=best_review,
        decision=best_decision,
        score=best_score,
        cost_tokens=total_tokens,
        cost_usd=total_cost,
    )

    return {
        "total_tokens": sum_tokens,
        "total_cost": sum_cost,
    }


# --- Arestas Condicionais ---

def evaluation_router(state: ReviewState) -> str:
    """Decide se volta pro roteador ou finaliza"""
    if state["is_approved"]:
        logger.info("Revisão aprovada. Indo para sumarização.")
        return "summarize"
    
    if state["attempts"] >= settings.max_attempts:
        logger.warning(f"Limite de tentativas ({settings.max_attempts}) alcançado. Indo para sumarização com a melhor tentativa.")
        return "summarize"
        
    logger.info("Revisão reprovada. Retornando ao Roteador para nova tentativa. Aguardando 30s para evitar rate limits...")
    time.sleep(30)
    return "retry"

# --- Construção do Grafo ---

def build_review_graph() -> StateGraph:
    workflow = StateGraph(ReviewState)
    
    workflow.add_node("Router", router_node)
    workflow.add_node("Executor", execution_node)
    workflow.add_node("Evaluator", evaluator_node)
    workflow.add_node("Summarizer", summarizer_node)
    
    workflow.set_entry_point("Router")
    
    workflow.add_edge("Router", "Executor")
    workflow.add_edge("Executor", "Evaluator")
    
    workflow.add_conditional_edges(
        "Evaluator",
        evaluation_router,
        {
            "summarize": "Summarizer",
            "retry": "Router"
        }
    )
    
    workflow.add_edge("Summarizer", END)
    
    return workflow.compile()
