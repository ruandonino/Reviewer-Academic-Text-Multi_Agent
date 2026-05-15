import json
from typing import List, Tuple, Any
from src.utils.llm_client import safe_completion as completion
from src.models.review import ReviewResult
from src.config import settings
from src.utils.logger import get_logger

logger = get_logger()

SYNTHESIZER_MODEL = settings.synthesizer_model

def synthesize_final_report(reviews_with_sections: List[Tuple[Any, ReviewResult]]) -> Tuple[str, int, float]:
    """
    Consolida as revisões parciais em um relatório unificado (Etapa 8)
    """
    logger.info(f"Iniciando síntese de {len(reviews_with_sections)} revisões parciais.")
    
    if not reviews_with_sections:
        return "Nenhuma revisão gerada para síntese.", 0, 0.0
        
    reviews_json = []
    for i, (sec, rev) in enumerate(reviews_with_sections):
        reviews_json.append(f"--- REVISÃO DA SEÇÃO: {sec.type.upper()} ---\n{rev.model_dump_json(indent=2)}\n")
        
    all_reviews_text = "\n".join(reviews_json)
    
    prompt = f"""
Você é o Agente Sintetizador de um sistema de revisão acadêmica.
Sua tarefa é consolidar as revisões parciais das diferentes seções de um trabalho acadêmico em um Relatório Final unificado e coeso.

## Revisões Parciais:
{all_reviews_text}

## Estrutura Exigida para o Relatório:
1. Visão Geral do Documento e Integração entre Seções: Analise o documento como um todo com base nas revisões. Crie observações gerais focadas na coesão, coerência e integração lógica entre as diferentes seções do texto (ex: os métodos descritos sustentam a conclusão? A introdução dialoga bem com o referencial teórico?).
2. Revisões Detalhadas por Seção seguindo a ordem canônica das seções do documento (Título, Resumo, Introdução, etc.): Para CADA seção analisada, você DEVE listar TODOS os apontamentos gerados que sejam do tipo "semântica" ou "normativa". Para cada observação, apresente explicitamente no formato de lista:
**RESTRIÇÃO:** As seções da revisão gerada não serem (Título, Resumo, Introdução, Referêncial Teórico, Metodologia, Resultados, Conclusão e Referências.) será considerada uma falha grave na sua tarefa.
**RESTRIÇÃO:** **NÃO AVALIE:** Erros de digitação, erros gramaticais, erros ortográficos, uso de itálico ou formatação de fonte. Se você encontrar um erro desse tipo, IGNORE-O.
   - Trecho (Insira a referência ou o trecho que apresenta a falha)
   - Problema (Issue)
   - Sugestão (Suggestion)
   - Tipo (Normativa ou Semântica)
**IMPORTANTE**   Não omita nenhuma observação. Apresente todas de forma organizada.
3. Conclusão da Revisão: Finalize o relatório listando de forma clara e objetiva:
   - Aspectos Positivos (Pontos fortes do trabalho)
   - Problemas Principais (As falhas mais críticas que precisam de atenção)
   - Sugestões Gerais de Melhoria (Recomendações finais para o autor)

Formate o relatório em Markdown profissional. Mantenha um tom acadêmico e construtivo. 
"""

    import time
    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = completion(
                model=SYNTHESIZER_MODEL,
                messages=[{"role": "user", "content": prompt}]
            )
            report = response.choices[0].message.content.strip()
            
            tokens = response.usage.total_tokens if hasattr(response, 'usage') and response.usage else 0
            from litellm import completion_cost
            try:
                cost = completion_cost(completion_response=response)
            except Exception:
                logger.warning(f"Não foi possível calcular o custo do Sintetizador para o modelo {SYNTHESIZER_MODEL}")
                cost = 0.0
                
            logger.info("Síntese concluída com sucesso.")
            return report, tokens, cost
        except Exception as e:
            logger.error(f"Erro ao sintetizar relatório final (Tentativa {attempt+1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                logger.info("Aguardando 60 segundos para tentar novamente...")
                time.sleep(60)
            else:
                return f"Erro ao gerar o relatório final após {max_retries} tentativas.", 0, 0.0
