import json
import re
from typing import Tuple
from src.utils.llm_client import safe_completion as completion
from src.models.section import Section
from src.models.review import ReviewResult, EvaluationScore
from src.config import settings
from src.utils.logger import get_logger

logger = get_logger()

EVALUATOR_MODEL = settings.evaluator_model

def evaluate_review(section: Section, review: ReviewResult) -> Tuple[EvaluationScore, int, float]:
    """
    Avalia a qualidade da revisão produzida (Etapa 5)
    """
    logger.info(f"Avaliando revisão da seção: {section.type}")
    
    review_json = review.model_dump_json(indent=2)
    
    prompt = f"""
<heuristics>
Como você tem acesso ao texto integral do autor, aplique as seguintes leis de auditoria:
1. Tolerância Zero para Alucinações: Verifique se o "Trecho" citado na revisão existe exatamente daquela forma no texto original. Se o agente criticar algo que o autor fez corretamente ou apontar a ausência de um elemento que na verdade está presente, penalize severamente.
2. Caça a Omissões Críticas: Leia o texto original com atenção. Se houver uma falha grave (ex: citação fora do padrão, metodologias genéricas, resultados sem números, fuga ao tema) que o agente júnior ignorou, isso constitui uma falha de cobertura.
3. Exigência de Soluções Práticas: O agente júnior não é pago apenas para reclamar. Sugestões vagas como "melhore a clareza" são inaceitáveis. Ele deve atuar como um guia prático para o autor.
4. Calibragem por Tipo de Seção: Ajuste o rigor da sua avaliação de acordo com o "Tipo" da seção informada. Seções naturalmente curtas e estruturadas, como "Título" ou "Referências", demandam uma revisão mais simples e objetiva. Não penalize o agente por falta de profundidade analítica complexa ou baixo volume de observações nessas seções, contanto que os erros normativos ou de clareza evidentes tenham sido capturados.
</heuristics>

<evaluation_rubric>
Você deve avaliar a "Revisão Produzida" em 3 eixos, atribuindo uma nota de 1 a 4 para cada eixo.

EIXO 1: Acurácia e Cobertura (Texto Integral)
[4] Impecável: O agente não alucinou em nenhum momento e não deixou passar absolutamente nenhuma falha normativa/semântica grave presente no texto original (respeitando a simplicidade esperada para seções curtas).
[3] Bom: Avaliação precisa (sem alucinações), mas o agente deixou passar um erro menor que estava presente no texto.
[2] Ruim: Omitiu um erro CRÍTICO e óbvio que estava no texto original OU cometeu uma leve interpretação equivocada do que o autor escreveu.
[1] Inaceitável: O agente inventou um erro (alucinação flagrante), citou um trecho falsificado ou penalizou o autor por algo que ele fez corretamente.

EIXO 2: Acionabilidade e Especificidade
[4] Impecável: As sugestões de correção são cirúrgicas. O agente diz exatamente O QUE inserir, COMO reescrever ou QUAL norma aplicar. Serve como um guia prático perfeito para o autor do texto.
[3] Bom: As sugestões são úteis, mas alguma instrução poderia ser mais exemplificada ou direta.
[2] Ruim: Sugestões frequentemente vagas e pouco úteis (ex: "melhore a clareza", "reescreva de forma acadêmica", "seja mais específico").
[1] Inaceitável: A revisão é apenas uma lista de reclamações. Critica o texto, mas não diz como o autor deve consertar.

EIXO 3: Consistência Lógica e Estrutural
[4] Impecável: O "Problema" descrito e a "Sugestão" proposta têm alinhamento perfeito. A classificação (Normativa/Semântica) está correta segundo os conceitos acadêmicos e a formatação exigida pelo JSON foi perfeitamente respeitada.
[3] Bom: Lógica boa, mas o agente classificou erroneamente o "Tipo" de um erro (ex: chamou falta de formatação de Semântica).
[2] Ruim: A sugestão dada não resolve o problema apontado, havendo contradição.
[1] Inaceitável: A revisão não faz sentido lógico ou o formato de saída do JSON está completamente quebrado/ilegível.
</evaluation_rubric>

<thinking_process>
Antes de gerar sua avaliação final, realize a seguinte análise passo a passo:
1. Verificação de Alucinação: Faça uma busca no texto original. O trecho criticado realmente existe e o erro procede?
2. Calibragem de Escopo: Identifique o Tipo da seção avaliada. É uma seção densa (Metodologia, Resultados) ou uma seção curta/simples (Título, Referências)? Ajuste sua expectativa de cobertura.
3. Verificação de Omissão: Faça uma leitura independente do texto original. Há algo grave que o agente não viu? (Sendo mais tolerante com a quantidade de apontamentos caso seja uma seção curta).
4. Análise de Acionabilidade: Se você fosse o autor do manuscrito lendo a sugestão, você saberia EXATAMENTE o que digitar ou modificar para corrigir o erro?
5. Análise Lógica: O diagnóstico e a cura (problema e sugestão) combinam? A tag "Tipo" está correta?
6. Cálculo do Score: Atribua as notas (1 a 4) e converta a soma para uma escala de 0 a 100. (Fórmula: Nota final = (Soma das notas * 100) / 12).
</thinking_process>

Retorne APENAS um número de 0 a 100 representando a nota da revisão, sem nenhum texto adicional.
"""

    try:
        response = completion(
            model=EVALUATOR_MODEL,
            messages=[{"role": "user", "content": prompt}]
        )
        
        content = response.choices[0].message.content.strip()
        
        tokens = response.usage.total_tokens if hasattr(response, 'usage') and response.usage else 0
        from litellm import completion_cost
        try:
            cost = completion_cost(completion_response=response)
        except Exception:
            logger.warning(f"Não foi possível calcular o custo do Avaliador para o modelo {EVALUATOR_MODEL}")
            cost = 0.0
            
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
        return score, tokens, cost
        
    except Exception as e:
        logger.error(f"Erro no Agente Avaliador: {e}")
        return EvaluationScore(
            score=0.0,
            approved=False
        ), 0, 0.0
