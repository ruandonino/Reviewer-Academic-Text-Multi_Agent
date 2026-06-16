import os
import json
import uuid
import datetime
import operator
from typing import List, Dict, Any, Optional, Tuple
from typing_extensions import TypedDict, Annotated
from src.utils.llm_client import safe_completion as completion
from langgraph.graph import StateGraph, END, START

from src.models.section import Section
from src.models.router import RouterDecision, ModelAllocation
from src.models.review import ReviewResult, Observation
from src.utils.logger import get_logger

logger = get_logger()

# --- Logging e Leitura de Prompts ---

def _save_agent_log(document_id: str, execution_id: str, section_type: str, architecture: str, model_id: str, agent_name: str, content_json: Any):
    """Salva a resposta do agente agrupada por ID de execução e separada pelo nome do agente."""
    log_dir = os.path.join("logs", "agents_responses")
    os.makedirs(log_dir, exist_ok=True)
    
    doc_prefix = f"{document_id}_" if document_id else ""
    filename = f"exec_{doc_prefix}{section_type}_{execution_id}.json"
    filepath = os.path.join(log_dir, filename)
    
    log_entry = {
        "timestamp": datetime.datetime.now().isoformat(),
        "model_id": model_id,
        "response": content_json
    }
    
    try:
        if os.path.exists(filepath):
            with open(filepath, "r", encoding="utf-8") as f:
                logs = json.load(f)
        else:
            logs = {
                "execution_id": execution_id,
                "section_type": section_type,
                "architecture": architecture,
                "agents": {}
            }
            
        if agent_name in logs["agents"]:
            if not isinstance(logs["agents"][agent_name], list):
                logs["agents"][agent_name] = [logs["agents"][agent_name]]
            logs["agents"][agent_name].append(log_entry)
        else:
            logs["agents"][agent_name] = log_entry
        
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(logs, f, indent=4, ensure_ascii=False)
            
        logger.debug(f"Resposta do agente '{agent_name}' adicionada ao log: {filepath}")
    except Exception as e:
        logger.error(f"Falha ao salvar log do agente: {e}")


def load_agent_prompt(agent_name: str, router_instructions: str, section_type: str, architecture: str) -> str:
    """Carrega o system prompt do agente a partir do arquivo markdown organizados por seção e arquitetura."""
    base_dir = os.path.join("src", "prompts")
    
    # Normaliza nomes para pastas
    safe_section = section_type.lower().replace(" ", "_")
    if safe_section in ["revisão_da_literatura", "revisão_bibliográfica", "revisao_bibliografica", "background", "related_work"]:
        safe_section = "referencial_teórico"
    safe_arch = architecture.lower()
    
    # Caminho ideal: src/prompts/{section_type}/{architecture}/{agent_name}.md
    ideal_dir = os.path.join(base_dir, safe_section, safe_arch)
    os.makedirs(ideal_dir, exist_ok=True)
    
    filepath = os.path.join(ideal_dir, f"{agent_name}.md")
    
    if not os.path.exists(filepath):
        logger.warning(f"Prompt não encontrado em '{filepath}'. Tentando default da arquitetura.")
        filepath = os.path.join(ideal_dir, "default.md")
        
        if not os.path.exists(filepath):
            logger.warning(f"Prompt default não encontrado em '{ideal_dir}'. Usando default global.")
            filepath = os.path.join(base_dir, "default.md")
            os.makedirs(base_dir, exist_ok=True)
            
            if not os.path.exists(filepath):
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write("Você é um agente revisor acadêmico.\n\nDiretrizes Específicas para esta Seção:\n{router_instructions}")
                
    with open(filepath, "r", encoding="utf-8") as f:
        template = f.read()
        
    if "{router_instructions}" in template:
        prompt = template.replace("{router_instructions}", router_instructions)
    elif "<output_formatting>" in template:
        prompt = template.replace("<output_formatting>", f"Diretrizes Específicas para esta Seção pelo Roteador:\n{router_instructions}\n\n<output_formatting>")
    else:
        prompt = f"{template}\n\nDiretrizes Específicas para esta Seção:\n{router_instructions}"
        
    return prompt


import re
import random
import time

def _call_llm_for_review(model_id: str, system_prompt: str, section: Section, execution_id: str, agent_name: str, architecture: str, additional_context: str = "") -> Tuple[ReviewResult, int, float]:
    """Função utilitária agnóstica de provedor usando LiteLLM"""
    prompt = f"""
<dynamic_context>
Você receberá os dados do usuário nas seguintes tags:
<texto_submetido>
Tipo de seção: {section.type}
{section.text}
</texto_submetido>

<contexto_adicional_router_e_pares>
{additional_context}
</contexto_adicional_router_e_pares>

</dynamic_context>

{system_prompt}
"""
    try:
        # Jitter maior para evitar Rate Limits em chamadas paralelas
        time.sleep(random.uniform(2.0, 5.0))
        
        response = completion(
            model=model_id,
            messages=[{"role": "user", "content": prompt}]
        )
        content = response.choices[0].message.content.strip()
        
        tokens = response.usage.total_tokens if hasattr(response, 'usage') and response.usage else 0
        from litellm import completion_cost
        try:
            cost = completion_cost(completion_response=response)
        except Exception:
            logger.warning(f"Não foi possível calcular o custo do Agente para o modelo {model_id}")
            cost = 0.0
            
        # Parse the new markdown format
        scratchpad_match = re.search(r'<scratchpad>(.*?)</scratchpad>', content, re.DOTALL | re.IGNORECASE)
        general_comments = scratchpad_match.group(1).strip() if scratchpad_match else "Sem comentários gerais."
        
        observations = []
        blocks = re.split(r'\*\*Trecho:\*\*', content)
        for block in blocks[1:]: # O primeiro bloco contém o scratchpad e texto anterior
            try:
                # Divide pelo marcador "**Problema:**"
                if '* **Problema:**' in block:
                    quote_part, rest = block.split('* **Problema:**', 1)
                elif '**Problema:**' in block:
                    quote_part, rest = block.split('**Problema:**', 1)
                else:
                    continue
                    
                quote = quote_part.strip().strip('"').strip()
                
                # Divide pelo marcador "**Sugestão:**"
                if '* **Sugestão:**' in rest:
                    issue_part, rest = rest.split('* **Sugestão:**', 1)
                elif '**Sugestão:**' in rest:
                    issue_part, rest = rest.split('**Sugestão:**', 1)
                else:
                    continue
                    
                issue = issue_part.strip()
                
                # Divide pelo marcador "**Tipo:**"
                if '* **Tipo:**' in rest:
                    suggestion_part, type_part = rest.split('* **Tipo:**', 1)
                elif '**Tipo:**' in rest:
                    suggestion_part, type_part = rest.split('**Tipo:**', 1)
                else:
                    continue
                    
                suggestion = suggestion_part.strip()
                obs_type = type_part.strip().split('\n')[0].strip() # Pega a primeira linha do tipo
                
                observations.append({
                    "quote": quote,
                    "issue": issue,
                    "suggestion": suggestion,
                    "type": obs_type
                })
            except Exception as e:
                logger.warning(f"Erro ao parsear bloco de observação para o agente {agent_name}: {e}")
                
        review_dict = {
            "general_comments": general_comments,
            "observations": observations
        }
        
        # Salva o log agrupado por execução e separado por agente
        doc_id = getattr(section, 'document_id', '') or ""
        _save_agent_log(doc_id, execution_id, section.type, architecture, model_id, agent_name, {
            "raw_response": content,
            "parsed": review_dict
        })
        
        return ReviewResult(**review_dict), tokens, cost
    except Exception as e:
        logger.error(f"Erro na execução do modelo {model_id} (Agente: {agent_name}): {e}")
        return ReviewResult(general_comments=f"Erro na execução do agente {agent_name}: {e}", observations=[]), 0, 0.0


# --- Estado do Subgrafo (LangGraph) ---

def merge_dicts(a: dict, b: dict) -> dict:
    if a is None: a = {}
    if b is None: b = {}
    c = a.copy()
    c.update(b)
    return c

class ExecutionState(TypedDict):
    section: Section
    decision: RouterDecision
    execution_id: str
    agent_reviews: Annotated[Dict[str, ReviewResult], merge_dicts]
    current_chain_review: Optional[ReviewResult]
    final_review: Optional[ReviewResult]
    total_tokens: Annotated[int, operator.add]
    total_cost: Annotated[float, operator.add]


# --- Construtor Dinâmico do LangGraph ---

def build_execution_graph(decision: RouterDecision) -> StateGraph:
    workflow = StateGraph(ExecutionState)
    
    models = decision.models
    if not models:
        models = [ModelAllocation(agent_name="revisor_unico", model_id="gemini/gemini-2.5-flash-lite")]

    # Fábrica de Nós (Cada nó é um agente carregando seu prompt dinamicamente)
    def create_agent_node(model_alloc: ModelAllocation, role: str):
        def node_func(state: ExecutionState):
            logger.info(f"Executando nó do agente: {model_alloc.agent_name} (Papel: {role})")
            prompt = load_agent_prompt(model_alloc.agent_name, state["decision"].system_prompt, state["section"].type, state["decision"].architecture)
            
            additional_context = ""
            if role == "chain_refiner" and state.get("current_chain_review"):
                prev_rev = state['current_chain_review']
                obs_json = json.dumps([obs.model_dump() for obs in prev_rev.observations], ensure_ascii=False)
                additional_context = f"A revisão do seu colega anterior foi:\nComentários: {prev_rev.general_comments}\nObservações: {obs_json}\nRefine e melhore esta revisão."
            elif role in ["judge", "synthesizer", "consolidator"]:
                contexts = []
                for name, rev in state.get("agent_reviews", {}).items():
                    obs_json = json.dumps([obs.model_dump() for obs in rev.observations], ensure_ascii=False)
                    contexts.append(f"## Revisão do Agente {name}:\nComentários: {rev.general_comments}\nObservações: {obs_json}")
                additional_context = "Revisões independentes para consolidar e julgar:\n" + "\n".join(contexts)

            res, tokens, cost = _call_llm_for_review(
                model_id=model_alloc.model_id,
                system_prompt=prompt,
                section=state["section"],
                execution_id=state["execution_id"],
                agent_name=model_alloc.agent_name,
                architecture=state["decision"].architecture,
                additional_context=additional_context
            )
            
            updates = {
                "agent_reviews": {model_alloc.agent_name: res},
                "total_tokens": tokens,
                "total_cost": cost
            }
            if role in ["chain_starter", "chain_refiner"]:
                updates["current_chain_review"] = res
            if role in ["single", "chain_final", "judge", "synthesizer", "consolidator"]:
                updates["final_review"] = res
            return updates
        return node_func

    # Nó para Formatação Final (Apenas organiza o output visivelmente)
    def format_results(state: ExecutionState):
        arch = state["decision"].architecture.capitalize()
        comments = [f"Resultados da Topologia {arch} (LangGraph):"]
        final_rev = state["final_review"]
        
        if not final_rev:
            final_rev = ReviewResult(general_comments="Erro de execução no Grafo", observations=[])
            return {"final_review": final_rev}

        if arch == "Single" or len(state["decision"].models) == 1:
            agent_name = state["decision"].models[0].agent_name
            final_rev.general_comments = f"Resultados da Topologia Single (LangGraph):\n\n--- Comentários de {agent_name} ---\n{final_rev.general_comments}"
            
        elif arch == "Chain":
            for m in state["decision"].models:
                rev = state["agent_reviews"].get(m.agent_name)
                if rev:
                     comments.append(f"--- Comentários de {m.agent_name} ---\n{rev.general_comments}")
            final_rev.general_comments = "\n\n".join(comments)
            
        elif arch == "Star":
            specialists = state["decision"].models[:-1]
            consolidator = state["decision"].models[-1]
            for m in specialists:
                rev = state["agent_reviews"].get(m.agent_name)
                if rev:
                    comments.append(f"--- Comentários de {m.agent_name} ---\n{rev.general_comments}")
            comments.append(f"--- Comentários de {consolidator.agent_name} (Consolidador) ---\n{final_rev.general_comments}")
            final_rev.general_comments = "\n\n".join(comments)

        elif arch == "Debate":
            debaters = state["decision"].models[:-1]
            judge = state["decision"].models[-1]
            for m in debaters:
                rev = state["agent_reviews"].get(m.agent_name)
                if rev:
                    comments.append(f"--- Comentários de {m.agent_name} ---\n{rev.general_comments}")
            comments.append(f"--- Comentários de {judge.agent_name} (Juiz) ---\n{final_rev.general_comments}")
            final_rev.general_comments = "\n\n".join(comments)
            
        elif arch == "Ensemble":
            voters = state["decision"].models[:-1]
            synth_agent = state["decision"].models[-1].agent_name
            for m in voters:
                rev = state["agent_reviews"].get(m.agent_name)
                if rev:
                    comments.append(f"--- Comentários de {m.agent_name} ---\n{rev.general_comments}")
            comments.append(f"--- Comentários de {synth_agent} (Síntese) ---\n{final_rev.general_comments}")
            final_rev.general_comments = "\n\n".join(comments)
            
        return {"final_review": final_rev}


    # --- Conectando os Nós e Arestas dinamicamente ---
    arch = decision.architecture.capitalize()
    
    if arch == "Single" or len(models) == 1:
        workflow.add_node("agent_0", create_agent_node(models[0], "single"))
        workflow.add_node("format", format_results)
        workflow.add_edge(START, "agent_0")
        workflow.add_edge("agent_0", "format")
        workflow.add_edge("format", END)
        
    elif arch == "Chain":
        prev = START
        for i, m in enumerate(models):
            node_name = f"agent_{i}"
            role = "chain_final" if i == len(models) - 1 else ("chain_starter" if i == 0 else "chain_refiner")
            workflow.add_node(node_name, create_agent_node(m, role))
            workflow.add_edge(prev, node_name)
            prev = node_name
        
        workflow.add_node("format", format_results)
        workflow.add_edge(prev, "format")
        workflow.add_edge("format", END)

    elif arch == "Star":
        consolidator_model = models[-1]
        specialists = models[:-1]
        
        workflow.add_node("consolidator", create_agent_node(consolidator_model, "consolidator"))
        workflow.add_node("format", format_results)
        
        for i, m in enumerate(specialists):
            node_name = f"agent_{i}"
            workflow.add_node(node_name, create_agent_node(m, "reviewer"))
            workflow.add_edge(START, node_name)
            workflow.add_edge(node_name, "consolidator")
            
        workflow.add_edge("consolidator", "format")
        workflow.add_edge("format", END)

    elif arch == "Debate":
        judge_model = models[-1]
        debaters = models[:-1]
        
        workflow.add_node("judge", create_agent_node(judge_model, "judge"))
        workflow.add_node("format", format_results)
        
        for i, m in enumerate(debaters):
            node_name = f"agent_{i}"
            workflow.add_node(node_name, create_agent_node(m, "reviewer"))
            workflow.add_edge(START, node_name)
            workflow.add_edge(node_name, "judge")
            
        workflow.add_edge("judge", "format")
        workflow.add_edge("format", END)

    elif arch == "Ensemble":
        synth_model = models[0] # Usa o modelo do primeiro agent para sintetizar
        synth_alloc = ModelAllocation(agent_name="sintetizador_ensemble", model_id=synth_model.model_id)
        
        workflow.add_node("synthesizer", create_agent_node(synth_alloc, "synthesizer"))
        workflow.add_node("format", format_results)
        
        for i, m in enumerate(models):
            node_name = f"agent_{i}"
            workflow.add_node(node_name, create_agent_node(m, "reviewer"))
            workflow.add_edge(START, node_name)
            workflow.add_edge(node_name, "synthesizer")
            
        workflow.add_edge("synthesizer", "format")
        workflow.add_edge("format", END)

    return workflow.compile()


def execute_architecture(decision: RouterDecision, section: Section) -> Tuple[ReviewResult, int, float]:
    """
    Orquestra a produção colaborativa baseada na topologia escolhida construindo um Grafo (LangGraph).
    """
    logger.info(f"Construindo Sub-Grafo (LangGraph) para a topologia: {decision.architecture}")
    
    execution_id = str(uuid.uuid4())[:8]
    
    # 1. Compila o Grafo sob demanda para esta arquitetura
    workflow = build_execution_graph(decision)
    
    # 2. Inicializa o Estado do Sub-Grafo
    initial_state = {
        "section": section,
        "decision": decision,
        "execution_id": execution_id,
        "agent_reviews": {},
        "current_chain_review": None,
        "final_review": None,
        "total_tokens": 0,
        "total_cost": 0.0
    }
    
    # 3. Invoca o LangGraph
    final_state = workflow.invoke(initial_state)
    
    if not final_state.get("final_review"):
        logger.error(f"Erro Crítico: Nenhuma revisão gerada pelo Sub-Grafo da arquitetura {decision.architecture}")
        return ReviewResult(general_comments="Erro Crítico na execução do LangGraph interno.", observations=[]), 0, 0.0
        
    return final_state["final_review"], final_state.get("total_tokens", 0), final_state.get("total_cost", 0.0)
