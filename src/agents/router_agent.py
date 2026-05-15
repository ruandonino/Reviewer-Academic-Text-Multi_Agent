import json
import os
import uuid
import datetime
from typing import List, Dict, Any, Tuple
from src.utils.llm_client import safe_completion as completion
from src.models.section import Section
from src.models.router import RouterDecision, ModelAllocation
from src.memory.vector_db import vector_db
from src.config import settings
from src.utils.logger import get_logger

logger = get_logger()

# Modelo de decisão padrão para o roteador
ROUTER_MODEL = settings.router_model

def _save_router_log(document_id: str, section_type: str, decision_dict: dict):
    log_dir = os.path.join("logs", "router_responses")
    os.makedirs(log_dir, exist_ok=True)
    execution_id = str(uuid.uuid4())[:8]
    doc_prefix = f"{document_id}_" if document_id else ""
    filename = f"route_{doc_prefix}{section_type}_{execution_id}.json"
    filepath = os.path.join(log_dir, filename)
    
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump({
                "timestamp": datetime.datetime.now().isoformat(),
                "section": section_type,
                "decision": decision_dict
            }, f, indent=4, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Falha ao salvar log do roteador: {e}")

def mount_router_prompt(section: Section, history: List[Dict[str, Any]]) -> str:
    """
    Monta o prompt para o agente roteador com RAG (Etapa 3)
    """
    history_text = "Nenhum histórico disponível."
    if history:
        history_texts = []
        for i, h in enumerate(history):
            meta = h.get("metadata", {})
            cost_usd = meta.get('cost_usd', 0.0)
            if cost_usd is None:
                cost_usd = 0.0
            history_texts.append(f"Registro {i+1}:\n"
                                 f"- Nota obtida: {meta.get('evaluation_score')}\n"
                                 f"- Arquitetura: {meta.get('architecture_used')}\n"
                                 f"- Modelos: {meta.get('models_used', 'N/A')}\n"
                                 f"- Custo (USD): ${cost_usd:.4f}\n"
                                 f"- Resumo: {meta.get('text_summary')}\n")
        history_text = "\n".join(history_texts)

    # Constrói a lista de modelos dinamicamente
    models_text = ""
    for model_id, desc in settings.available_models.items():
        models_text += f"- {model_id}: {desc}\n"

    # Constrói a lista de arquiteturas e agentes exigidos dinamicamente
    archs_text = ""
    valid_arch_names = list(settings.available_architectures.keys())
    for arch_name, agents in settings.available_architectures.items():
        archs_text += f"- {arch_name}: Requer os seguintes agentes -> {', '.join(agents)}\n"

    arch_format = " | ".join(valid_arch_names)

    prompt = f"""
        Você é o Agente Roteador de um sistema multiagente de revisão acadêmica.
        Sua tarefa é analisar a seção atual e o histórico de execuções similares para decidir a melhor arquitetura e os melhores modelos (LLMs) para realizar a revisão, **otimizando a relação entre qualidade da revisão e custo financeiro**.
        LEMBRE-SE QUE O OBJETIVO É ENTREGAR A MELHOR REVISÃO POSSÍVEL DENTRO COM O MENOR CUSTO POSSÍVEL.

        ## Seção Atual
        Tipo: {section.type}
        Texto:
        {section.text[:1000]}... [truncado para contexto]

        ## Parâmetros de Avaliação
        NOTA MÍNIMA PARA APROVAÇÃO: {settings.quality_threshold}/100.
        (A revisão gerada pelos agentes que você escolher precisará atingir ou superar essa nota para ser considerada um sucesso pelo Avaliador. Leve isso em conta ao decidir se deve usar um modelo ou uma arquitetura mais caro/robusto em seções complexas).

        ## Histórico de Revisões Semelhantes (RAG)
        {history_text}

        ## Arquiteturas Disponíveis e Seus Agentes
        Abaixo estão as arquiteturas disponíveis e os NOMES EXATOS dos agentes que você DEVE alocar caso escolha essa arquitetura:
        {archs_text}

        ## Modelos Disponíveis
        {models_text}

        ## Princípios de Decisão (LEIA COM ATENÇÃO)

        Você DEVE tomar suas decisões considerando explicitamente o **trade-off entre custo e qualidade**. Modelos e arquiteturas mais caros NÃO são automaticamente melhores — eles só se justificam quando a complexidade da tarefa realmente os exige.

        ### 1. Avaliação da Complexidade da Seção
        Antes de escolher arquitetura e modelos, classifique mentalmente a seção em um destes níveis:
        - **BAIXA complexidade**: seções curtas, descritivas, padronizadas → Prefira modelos de **custo BAIXO** e arquiteturas **simples** (poucos agentes).
        - **MÉDIA complexidade**: seções analíticas moderadas, que exigem raciocínio profundo e não podem ser revisadas com modelos simples de baixo custo→ Prefira modelos de **custo MÉDIO** ou uma combinação de modelos BAIXO + MÉDIO em arquiteturas intermediárias.
        - **ALTA complexidade**: seções que exigem raciocínio profundo, julgamento crítico ou síntese sofisticada que já falharam quando utilizando modelos de custo BAIXO ou MEDIO em arquiteturas simples. → Justifica-se o uso de modelos de **custo ALTO** e arquiteturas mais robustas (multi-agente, juízes, consolidadores).

        ### 2. Escolha da Arquitetura
        - Arquiteturas com **mais agentes** multiplicam o custo total por chamada. Só escolha arquiteturas complexas quando a tarefa realmente se beneficiar de múltiplas perspectivas, validação cruzada ou consolidação.
        - Para tarefas simples, **uma arquitetura enxuta com um único o poucos agentes já é suficiente** e dramaticamente mais barata.
        - Considere o histórico: se seções semelhantes foram bem revisadas com arquiteturas simples, **não escale desnecessariamente**.

        ### 3. Alocação de Modelos por Agente
        - **Não use modelos ALTO custo em todos os agentes por padrão.** Distribua modelos de forma inteligente:
        - Agentes de pré-processamento, extração ou roteamento interno → modelos de custo **BAIXO**.
        - Agentes de análise intermediária → modelos de custo **MÉDIO**.
        - Apenas agentes críticos (juízes finais, consolidadores, avaliadores em seções de ALTA complexidade) → modelos de custo **ALTO**.
        - Sempre que dois modelos entregarem qualidade equivalente para a tarefa, **escolha o mais barato**.
        - Considere o histórico: se seções semelhantes foram bem revisadas com modelos de custo BAIXO, simples, escolha os modelos de MENOR CUSTO **não escale desnecessariamente**.

        ### 4. Aprendizado com o Histórico
        - Se o histórico mostra que seções semelhantes foram revisadas com sucesso usando configurações mais baratas, **replique essa escolha** em vez de optar por algo mais caro "por segurança".
        - Se o histórico mostra falhas ou revisões insuficientes com modelos baratos, escale apenas os agentes específicos que precisam de mais capacidade.
        - Antes de decidir por um modelo de custo ALTO, tente utilizar modelos de custo MÉDIO ou uma arquitetura com mais agentes para compensar, e só escale para ALTO se isso não for suficiente.

        ## Formato de Resposta

        Retorne EXATAMENTE um JSON válido com a seguinte estrutura:
        {{
            "architecture": "{arch_format}",
            "models": [
                {{"agent_name": "<nome_exato_do_agente_da_arquitetura_escolhida>", "model_id": "<um_dos_modelos_disponiveis>"}}
            ],
            "reasoning": "Sua justificativa baseada no histórico e complexidade. **Inclua obrigatoriamente**: (a) o nível de complexidade atribuído à seção, (b) por que a arquitetura escolhida é adequada (e não excessiva) para esse nível, e (c) a justificativa de custo-benefício para cada modelo alocado.",
            "system_prompt": "Instruções específicas de revisão para esta seção, considerando seu tipo e o que foi aprendido no histórico."
        }}
        ATENÇÃO: A propriedade 'models' do JSON deve conter EXATAMENTE os agentes exigidos pela arquitetura escolhida.
        O 'system_prompt' será passado para os agentes revisores para guiar o tom e o foco da análise, não adicone ao 'system_prompt' instruções relacionados a erros gramaticais ou de digitação, assim como erros de fonte como itálico ou negrito.
    """
    return prompt

def route_section(section: Section) -> Tuple[RouterDecision, List[Dict[str, Any]], int, float]:
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
        
        tokens = response.usage.total_tokens if hasattr(response, 'usage') and response.usage else 0
        from litellm import completion_cost
        try:
            cost = completion_cost(completion_response=response)
        except Exception:
            logger.warning(f"Não foi possível calcular o custo do Roteador para o modelo {ROUTER_MODEL}")
            cost = 0.0
            
        # Limpa formatação Markdown se o modelo retornar ```json ... ```
        if content.startswith("```json"):
            content = content[7:-3].strip()
        elif content.startswith("```"):
            content = content[3:-3].strip()
            
        decision_dict = json.loads(content)
        
        doc_id = getattr(section, 'document_id', '') or ""
        _save_router_log(doc_id, section.type, decision_dict)
        
        decision = RouterDecision(**decision_dict)
        
        logger.info(f"Roteador decidiu arquitetura: {decision.architecture}")
        return decision, history, tokens, cost
    except Exception as e:
        logger.error(f"Erro no Agente Roteador: {e}")
        # Fallback seguro
        fallback = RouterDecision(
            architecture="Single",
            models=[ModelAllocation(agent_name="revisor_1", model_id="gemini/gemma-3-27b-it")],
            reasoning="Fallback devido a erro de inferência.",
            system_prompt="Revise a seção prestando atenção em clareza, norma culta e fluxo lógico."
        )
        return fallback, [], 0, 0.0
