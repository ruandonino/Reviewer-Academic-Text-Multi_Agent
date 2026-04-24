import json
from litellm import completion
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

Retorne EXATAMENTE um JSON válido com a estrutura:
{{
    "score": 85.5,
    "justification": "Explicação detalhada dos pontos fortes e fracos, baseada nos critérios.",
    "approved": true
}}
"""

    try:
        response = completion(
            model=EVALUATOR_MODEL,
            messages=[{"role": "user", "content": prompt}]
        )
        
        content = response.choices[0].message.content.strip()
        
        # Limpa formatação Markdown se o modelo retornar ```json ... ```
        if content.startswith("```json"):
            content = content[7:-3].strip()
        elif content.startswith("```"):
            content = content[3:-3].strip()
            
        eval_dict = json.loads(content)
        
        # Override aprovado based on the internal setting to be safe
        eval_dict['approved'] = eval_dict['score'] >= settings.quality_threshold
        
        score = EvaluationScore(**eval_dict)
        logger.info(f"Avaliação concluída. Nota: {score.score}. Aprovado: {score.approved}")
        return score
        
    except Exception as e:
        logger.error(f"Erro no Agente Avaliador: {e}")
        return EvaluationScore(
            score=0.0,
            justification=f"Falha na avaliação: {e}",
            approved=False
        )
