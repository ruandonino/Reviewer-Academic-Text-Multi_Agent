import json
from typing import List, Dict, Any, Tuple
from litellm import completion
from src.models.section import Section
from src.models.router import RouterDecision, ModelAllocation
from src.memory.vector_db import vector_db
from src.config import settings
from src.utils.logger import get_logger

logger = get_logger()

# Modelo de decisão padrão para o roteador
ROUTER_MODEL = "gemini/gemma-3-27b-it" # Pode ser parametrizado

def mount_router_prompt(section: Section, history: List[Dict[str, Any]]) -> str:
    """
    Monta o prompt para o agente roteador com RAG (Etapa 3)
    """
    history_text = "Nenhum histórico disponível."
    if history:
        history_texts = []
        for i, h in enumerate(history):
            meta = h.get("metadata", {})
            history_texts.append(f"Registro {i+1}:\n"
                                 f"- Nota obtida: {meta.get('evaluation_score')}\n"
                                 f"- Arquitetura: {meta.get('architecture_used')}\n"
                                 f"- Resumo: {meta.get('text_summary')}\n")
        history_text = "\n".join(history_texts)

    prompt = f"""
Você é o Agente Roteador de um sistema multiagente de revisão acadêmica.
Sua tarefa é analisar a seção atual e o histórico de execuções similares para decidir a melhor arquitetura e os melhores modelos (LLMs) para realizar a revisão.

## Seção Atual
Tipo: {section.type}
Texto:
{section.text[:1000]}... [truncado para contexto]

## Histórico de Revisões Semelhantes (RAG)
{history_text}

## Arquiteturas Disponíveis
- Single: Um único agente revisor. (Baixo custo, para seções simples).
- Star: Um agente revisor principal e agentes auxiliares para aspectos específicos.
- Debate: Agentes debatem os apontamentos antes de consolidar.
- Chain: Revisão sequencial onde cada agente refina o trabalho do anterior.
- Ensemble: Múltiplas revisões independentes consolidadas por um votante.

## Modelos Disponíveis
- gemini/gemma-3-27b-it: Custo BAIXO. Modelo open-weight eficiente e rápido. Ideal para tarefas de baixa e média complexidade, como revisões normativas simples ou roteamento inicial, sendo a escolha prioritária quando o orçamento é restrito ou a seção é trivial.
- gemini/gemini-2.5-flash-lite: Custo MÉDIO. Modelo balanceado, com excelente capacidade de raciocínio lógico e grande contexto. Ideal para a maioria das tarefas de revisão acadêmica, oferecendo o melhor custo-benefício geral.
- claude-3-5-sonnet-20241022: Custo ALTO. Modelo premium com altíssima capacidade analítica, compreensão profunda de nuances semânticas e estruturais. Ideal para tarefas muito complexas, como consolidar debates de múltiplos agentes ou avaliar metodologias densas.
- gpt-4o: Custo ALTO. Modelo de fronteira de alto desempenho, excelente para raciocínio lógico complexo e cumprimento estrito de regras (como normas da ABNT rigorosas). Use com moderação, apenas quando alto rigor for necessário.

Retorne EXATAMENTE um JSON válido com a seguinte estrutura:
{{
    "architecture": "Single" | "Star" | "Debate" | "Chain" | "Ensemble",
    "models": [
        {{"agent_name": "revisor_principal", "model_id": "gemini/gemma-3-27b-it"}}
    ],
    "reasoning": "Sua justificativa baseada no histórico e complexidade.",
    "system_prompt": "O system prompt que será passado para os agentes revisores focado nesta seção."
}}
"""
    return prompt

def route_section(section: Section) -> Tuple[RouterDecision, List[Dict[str, Any]]]:
    """
    Executa as Etapas 2 e 3: Recuperação e Decisão do Roteador
    """
    logger.info(f"Iniciando roteamento para seção: {section.type}")
    
    # Etapa 2: RAG
    history = vector_db.retrieve_context(section.text, section.type, settings.k_nearest_neighbors)
    
    # Etapa 3: Prompt Engineering e Inferência
    prompt = mount_router_prompt(section, history)
    
    try:
        response = completion(
            model=ROUTER_MODEL,
            messages=[{"role": "user", "content": prompt}]
        )
        
        content = response.choices[0].message.content.strip()
        
        # Limpa formatação Markdown se o modelo retornar ```json ... ```
        if content.startswith("```json"):
            content = content[7:-3].strip()
        elif content.startswith("```"):
            content = content[3:-3].strip()
            
        decision_dict = json.loads(content)
        decision = RouterDecision(**decision_dict)
        
        logger.info(f"Roteador decidiu arquitetura: {decision.architecture}")
        return decision, history
    except Exception as e:
        logger.error(f"Erro no Agente Roteador: {e}")
        # Fallback seguro
        fallback = RouterDecision(
            architecture="Single",
            models=[ModelAllocation(agent_name="revisor_1", model_id="gemini/gemma-3-27b-it")],
            reasoning="Fallback devido a erro de inferência.",
            system_prompt="Revise a seção prestando atenção em clareza, norma culta e fluxo lógico."
        )
        return fallback, []
