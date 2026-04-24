import json
from typing import List
from litellm import completion
from src.models.review import ReviewResult
from src.utils.logger import get_logger

logger = get_logger()

SYNTHESIZER_MODEL = "gemini/gemini-2.5-flash-lite"

def synthesize_final_report(reviews: List[ReviewResult]) -> str:
    """
    Consolida as revisões parciais em um relatório unificado (Etapa 8)
    """
    logger.info(f"Iniciando síntese de {len(reviews)} revisões parciais.")
    
    if not reviews:
        return "Nenhuma revisão gerada para síntese."
        
    reviews_json = []
    for i, rev in enumerate(reviews):
        reviews_json.append(f"--- REVISÃO PARCIAL {i+1} ---\n{rev.model_dump_json(indent=2)}\n")
        
    all_reviews_text = "\n".join(reviews_json)
    
    prompt = f"""
Você é o Agente Sintetizador de um sistema de revisão acadêmica.
Sua tarefa é consolidar as revisões parciais das diferentes seções de um trabalho acadêmico em um Relatório Final unificado e coeso.

## Revisões Parciais:
{all_reviews_text}

## Estrutura Exigida para o Relatório:
1. Visão Geral do Documento e Integração entre Seções: Analise o documento como um todo com base nas revisões. Crie observações gerais focadas na coesão, coerência e integração lógica entre as diferentes seções do texto (ex: os métodos descritos sustentam a conclusão? A introdução dialoga bem com o referencial teórico?).
2. Revisões Detalhadas por Seção: Para CADA seção analisada, você DEVE listar TODOS os apontamentos gerados. Para cada observação, apresente explicitamente no formato de lista:
   - Trecho (Quote)
   - Problema (Issue)
   - Sugestão (Suggestion)
   - Tipo (Normativa ou Semântica)
   Não omita nenhuma observação. Apresente todas de forma organizada.
3. Conclusão da Revisão: Finalize o relatório listando de forma clara e objetiva:
   - Aspectos Positivos (Pontos fortes do trabalho)
   - Problemas Principais (As falhas mais críticas que precisam de atenção)
   - Sugestões Gerais de Melhoria (Recomendações finais para o autor)

Formate o relatório em Markdown profissional. Mantenha um tom acadêmico e construtivo.
"""

    try:
        response = completion(
            model=SYNTHESIZER_MODEL,
            messages=[{"role": "user", "content": prompt}]
        )
        report = response.choices[0].message.content.strip()
        logger.info("Síntese concluída com sucesso.")
        return report
    except Exception as e:
        logger.error(f"Erro ao sintetizar relatório final: {e}")
        return "Erro ao gerar o relatório final."
