import json
import re
from src.utils.llm_client import safe_completion as completion
from src.models.section import Section
from src.models.review import ReviewResult, EvaluationScore
from src.config import settings
from src.utils.logger import get_logger

logger = get_logger()

EVALUATOR_MODEL = "gemini/gemini-2.5-flash-lite"

def evaluate_review(section: Section, review: ReviewResult) -> EvaluationScore:
    """
    Avalia a qualidade da revisão produzida (Etapa 5)
    """
    logger.info(f"Avaliando revisão da seção: {section.type}")
    
    review_json = review.model_dump_json(indent=2)
    
    prompt = f"""
Você é um Revisor Sênior avaliando o trabalho de um revisor júnior.
Sua tarefa é dar uma nota de 0 a 100 para a revisão gerada para a seção abaixo.

## Seção (Original)
Tipo: {section.type}
{section.text[:1500]}... [truncado]

## Revisão Produzida
{review_json}

## Critérios de Avaliação
1. Cobertura: Identificou os problemas principais?
2. Especificidade: Os apontamentos são acionáveis e apontam para trechos específicos?
3. Ausência de Fabricação (Alucinação): Os erros apontados realmente existem no texto original?
4. Clareza Expositiva: A revisão é fácil de entender para o autor?

Retorne APENAS um número de 0 a 100 representando a nota da revisão, sem nenhum texto adicional.
"""

    try:
        response = completion(
            model=EVALUATOR_MODEL,
            messages=[{"role": "user", "content": prompt}]
        )
        
        content = response.choices[0].message.content.strip()
        
        # Extrai apenas o número da resposta para evitar erros se o modelo retornar texto junto
        match = re.search(r'\d+(\.\d+)?', content)
        if match:
            score_val = float(match.group(0))
        else:
            score_val = 0.0
            
        is_approved = score_val >= settings.quality_threshold
        
        score = EvaluationScore(
            score=score_val,
            approved=is_approved
        )
        logger.info(f"Avaliação concluída. Nota: {score.score}. Aprovado: {score.approved}")
        return score
        
    except Exception as e:
        logger.error(f"Erro no Agente Avaliador: {e}")
        return EvaluationScore(
            score=0.0,
            approved=False
        )
