import os
import json
import uuid
import datetime
from typing import List, Dict, Any, Optional
from litellm import completion
from src.models.section import Section
from src.models.router import RouterDecision
from src.models.review import ReviewResult, Observation
from src.utils.logger import get_logger

logger = get_logger()

def _save_agent_log(execution_id: str, section_type: str, architecture: str, model_id: str, agent_name: str, content_json: Any):
    """Salva a resposta do agente agrupada por ID de execução e separada pelo nome do agente."""
    log_dir = os.path.join("logs", "agents_responses")
    os.makedirs(log_dir, exist_ok=True)
    
    # Usa um nome de arquivo fixo por execução para garantir o agrupamento
    filename = f"exec_{section_type}_{execution_id}.json"
    filepath = os.path.join(log_dir, filename)
    
    # Estrutura do log para este agente
    log_entry = {
        "timestamp": datetime.datetime.now().isoformat(),
        "model_id": model_id,
        "response": content_json
    }
    
    try:
        # Se o arquivo já existe, lê o conteúdo atual (dicionário) e adiciona a nova chave/agente
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
            
        # Trata o caso de um mesmo agente responder mais de uma vez (como em iterações futuras)
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

def execute_architecture(decision: RouterDecision, section: Section) -> ReviewResult:
    """
    Orquestra a produção colaborativa baseada na topologia escolhida (Etapa 4).
    """
    logger.info(f"Executando topologia: {decision.architecture}")
    
    # Gera um ID de execução único para esta seção e esta tentativa
    execution_id = str(uuid.uuid4())[:8]
    
    if not decision.models:
        return _execute_single(decision, section, execution_id)
        
    if decision.architecture == "Single":
        return _execute_single(decision, section, execution_id)
    elif decision.architecture == "Star":
        return _execute_star(decision, section, execution_id)
    elif decision.architecture == "Chain":
        return _execute_chain(decision, section, execution_id)
    elif decision.architecture == "Debate":
        return _execute_debate(decision, section, execution_id)
    elif decision.architecture == "Ensemble":
        return _execute_ensemble(decision, section, execution_id)
    else:
        logger.warning(f"Topologia {decision.architecture} desconhecida. Usando Single fallback.")
        return _execute_single(decision, section, execution_id)

def _call_llm_for_review(model_id: str, system_prompt: str, section: Section, execution_id: str, agent_name: str, architecture: str, additional_context: str = "") -> ReviewResult:
    """Função utilitária agnóstica de provedor usando LiteLLM"""
    prompt = f"""
{system_prompt}

{additional_context}

## Seção para revisão
Tipo: {section.type}
Texto:
{section.text}

Retorne EXATAMENTE um JSON válido com a estrutura:
{{
    "general_comments": "Comentários gerais sobre a seção.",
    "observations": [
        {{
            "quote": "trecho do texto",
            "issue": "problema encontrado",
            "suggestion": "sugestão",
            "type": "Normativa" ou "Semântica"
        }}
    ]
}}
"""
    try:
        response = completion(
            model=model_id,
            messages=[{"role": "user", "content": prompt}]
        )
        content = response.choices[0].message.content.strip()
        
        # Limpa formatação Markdown se o modelo retornar ```json ... ```
        if content.startswith("```json"):
            content = content[7:-3].strip()
        elif content.startswith("```"):
            content = content[3:-3].strip()
            
        review_dict = json.loads(content)
        
        # Salva o log agrupado por execução e separado por agente com o JSON já formatado
        _save_agent_log(execution_id, section.type, architecture, model_id, agent_name, review_dict)
        
        return ReviewResult(**review_dict)
    except Exception as e:
        logger.error(f"Erro na execução do modelo {model_id} (Agente: {agent_name}): {e}")
        return ReviewResult(general_comments=f"Erro na execução: {e}", observations=[])

def _execute_single(decision: RouterDecision, section: Section, execution_id: str) -> ReviewResult:
    model_id = decision.models[0].model_id if decision.models else "gpt-4o"
    agent_name = decision.models[0].agent_name if decision.models else "revisor_unico"
    res = _call_llm_for_review(model_id, decision.system_prompt, section, execution_id, agent_name=agent_name, architecture=decision.architecture)
    
    res.general_comments = f"Resultados da Topologia Single:\n\n--- Comentários de {agent_name} ---\n{res.general_comments}"
    return res

def _execute_star(decision: RouterDecision, section: Section, execution_id: str) -> ReviewResult:
    """
    Topologia Star: Especialistas em áreas distintas cujos resultados são somados.
    """
    results = []
    foci = ["Normas Acadêmicas", "Coesão e Lógica Semântica", "Rigor Metodológico"]
    
    for i, model_alloc in enumerate(decision.models[:3]):
        focus_prompt = f"{decision.system_prompt}\nFOCO EXCLUSIVO: {foci[i]}."
        res = _call_llm_for_review(model_alloc.model_id, focus_prompt, section, execution_id, agent_name=model_alloc.agent_name, architecture=decision.architecture)
        results.append((model_alloc.agent_name, res))
    
    all_obs = []
    comments = ["Resultados da Topologia Star:"]
    for agent_name, r in results:
        all_obs.extend(r.observations)
        comments.append(f"--- Comentários de {agent_name} ---\n{r.general_comments}")
        
    return ReviewResult(general_comments="\n\n".join(comments), observations=all_obs)

def _execute_chain(decision: RouterDecision, section: Section, execution_id: str) -> ReviewResult:
    """
    Topologia Chain: Um agente revisa e o próximo refina a revisão anterior.
    """
    current_review = None
    comments = ["Resultados da Topologia Chain:"]
    
    for i, model_alloc in enumerate(decision.models):
        context = ""
        if current_review:
            context = f"A revisão anterior foi:\n{current_review.model_dump_json()}\nMelhore e refine esta revisão."
        
        current_review = _call_llm_for_review(model_alloc.model_id, decision.system_prompt, section, execution_id, agent_name=model_alloc.agent_name, architecture=decision.architecture, additional_context=context)
        comments.append(f"--- Comentários de {model_alloc.agent_name} ---\n{current_review.general_comments}")
        
    if current_review:
        current_review.general_comments = "\n\n".join(comments)
        
    return current_review

def _execute_debate(decision: RouterDecision, section: Section, execution_id: str) -> ReviewResult:
    """
    Topologia Debate: Dois agentes revisam e um terceiro julga/consolida.
    """
    if len(decision.models) < 3:
        return _execute_star(decision, section, execution_id) # Fallback se faltarem modelos
        
    rev1 = _call_llm_for_review(decision.models[0].model_id, decision.system_prompt, section, execution_id, agent_name=decision.models[0].agent_name, architecture=decision.architecture)
    rev2 = _call_llm_for_review(decision.models[1].model_id, decision.system_prompt, section, execution_id, agent_name=decision.models[1].agent_name, architecture=decision.architecture)
    
    consolidator_model = decision.models[2].model_id
    consolidator_agent_name = decision.models[2].agent_name
    prompt = f"""
Atue como um Juiz Revisor. Abaixo estão duas revisões para a mesma seção.
Consolide-as, removendo duplicatas e mantendo apenas os apontamentos mais pertinentes e corretos.

## Revisão 1:
{rev1.model_dump_json()}

## Revisão 2:
{rev2.model_dump_json()}
"""
    final_rev = _call_llm_for_review(consolidator_model, prompt, section, execution_id, agent_name=consolidator_agent_name, architecture=decision.architecture)
    
    comments = [
        "Resultados da Topologia Debate:",
        f"--- Comentários de {decision.models[0].agent_name} ---\n{rev1.general_comments}",
        f"--- Comentários de {decision.models[1].agent_name} ---\n{rev2.general_comments}",
        f"--- Comentários de {consolidator_agent_name} (Juiz) ---\n{final_rev.general_comments}"
    ]
    final_rev.general_comments = "\n\n".join(comments)
    return final_rev

def _execute_ensemble(decision: RouterDecision, section: Section, execution_id: str) -> ReviewResult:
    """
    Topologia Ensemble: Múltiplas revisões independentes e extração do consenso.
    """
    results = []
    comments = ["Resultados da Topologia Ensemble:"]
    
    for model_alloc in decision.models:
        res = _call_llm_for_review(model_alloc.model_id, decision.system_prompt, section, execution_id, agent_name=model_alloc.agent_name, architecture=decision.architecture)
        results.append(res)
        comments.append(f"--- Comentários de {model_alloc.agent_name} ---\n{res.general_comments}")
        
    # Agente de síntese para o ensemble
    synthesis_prompt = "Sintetize as múltiplas revisões abaixo em uma única revisão final, mantendo a diversidade de problemas encontrados."
    all_contexts = "\n".join([r.model_dump_json() for r in results])
    
    synthesizer_model = decision.models[0].model_id
    synthesizer_agent_name = "sintetizador_ensemble"
    final_rev = _call_llm_for_review(synthesizer_model, synthesis_prompt, section, execution_id, agent_name=synthesizer_agent_name, architecture=decision.architecture, additional_context=f"Revisões para consolidar:\n{all_contexts}")
    
    comments.append(f"--- Comentários de {synthesizer_agent_name} (Síntese) ---\n{final_rev.general_comments}")
    final_rev.general_comments = "\n\n".join(comments)
    return final_rev
