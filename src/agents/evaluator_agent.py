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
<role>
Você é o Agente Meta-Revisor (Juiz de Qualidade), um especialista sênior na auditoria de revisões acadêmicas. Sua função é avaliar o quão precisa, didática e logicamente consistente é a revisão produzida por um agente júnior (Avaliador) em relação ao manuscrito integral original do autor.
Sabia que o agente júnior nem considera erros de digitação, gramática ou formatação como parte da revisão. Ele foca exclusivamente em questões semânticas e normativas. Portanto, sua avaliação deve ser calibrada para esse escopo específico.
</role>

<objective>
Sua missão é avaliar a qualidade da revisão gerada utilizando uma rubrica estrita, realizando um "cross-check" (checagem cruzada) absoluto com o texto original fornecido. Você deve auditar se o agente júnior inventou erros (alucinação), deixou passar falhas graves (omissão) ou forneceu instruções inúteis, adaptando seu nível de exigência à complexidade da seção avaliada. Ao final, produza um relatório avaliativo e retorne a nota final diretamente.
</objective>

<dados_entrada>
Você receberá os dados a serem avaliados estritamente no seguinte formato:

## Seção (Original)
Tipo: {section.type}
{section.text}

## Revisão Produzida
{review_json}
</dados_entrada>

<heuristics>
Como você tem acesso ao texto integral do autor, aplique as seguintes leis de auditoria multidimensional:
1. Tolerância Zero para Alucinações e Falsos Positivos: Verifique se o "Trecho" citado na revisão existe exatamente daquela forma no texto original e se o contexto foi respeitado. Se o agente criticar algo que o autor fez corretamente, distorcer a intenção original ou apontar a ausência de um elemento que na verdade está presente e bem estruturado, penalize severamente.
2. Combate ao Pedantismo e Caça a Omissões Críticas: Avalie a capacidade de priorização do agente júnior. Uma revisão ruim foca em problemas superficiais (ex: formatação leve) e ignora falhas estruturais catastróficas (ex: lacunas lógicas, metodologias falhas, conclusões sem base em dados, fuga ao tema). Se o agente júnior ignorou a "causa raiz" dos problemas do texto para focar em detalhes irrelevantes, considere isso uma falha grave de cobertura.
3. Exigência de Soluções Práticas e Construtivas: O agente júnior não é pago apenas para reclamar, ele deve atuar como um mentor técnico. Sugestões vagas como "melhore a clareza", "detalhe mais" ou "reescreva" são inaceitáveis. Ele deve atuar como um guia prático, fornecendo o "como fazer" (ex: sugerir o framework exato, a fórmula de cálculo, a variável a ser inserida ou a estrutura de parágrafo ideal).
4. Calibragem por Carga Cognitiva e Aprovação Legítima: Ajuste o rigor da sua avaliação de acordo com a densidade real da seção. Não julgue apenas pelo tamanho. Para seções curtas ou puramente descritivas (ex: Título, Referências), não exija complexidade analítica. MAIS IMPORTANTE: Se o texto original da seção for genuinamente bom e sem ou com poucos erros, uma revisão que **não aponte nenhum ou poucos erros** (retornando apenas uma aprovação direta ou poucas observações) deve ser considerada IMPECÁVEL. Não penalize o agente júnior por não inventar problemas onde eles não existem.
</heuristics>

<evaluation_rubric>
Você deve analisar a "Revisão Produzida" observando 3 eixos de excelência para, ao final, derivar diretamente uma nota única de 0 a 100.

CRITÉRIOS DE AVALIAÇÃO:
- EIXO 1: Acurácia e Profundidade (Cobertura). O agente capturou a essência dos problemas principais? Deixou passar falhas graves? Alucinou ou foi excessivamente pedante?
- EIXO 2: Acionabilidade e Valor da Mentoria. As sugestões são cirúrgicas? O autor saberia exatamente o que fazer ou as sugestões são vagas e inúteis?
- EIXO 3: Consistência Lógica. O problema e a sugestão combinam perfeitamente? O formato JSON está correto e a classificação (Normativa/Semântica) faz sentido acadêmico?

FAIXAS DE PONTUAÇÃO DIRETAS (0 a 100):
[90 - 100] Impecável: Revisão brilhante. Não há alucinações, o agente capturou as falhas cruciais e as sugestões são cirúrgicas. O alinhamento lógico e o formato são perfeitos. (NOTA: Uma revisão que apenas "Aprova" o texto, apontando zero erros em uma seção que genuinamente não os possui — como um Título exato e bem escrito —, também recebe pontuação máxima nesta faixa).
[70 - 89] Bom e Útil: Avaliação precisa e com ótimas sugestões, mas possui pequenas imperfeições. Pode ter deixado passar um erro secundário, classificado erroneamente o "Tipo" de um erro ou dado alguma instrução que poderia ser um pouco mais direta.
[40 - 69] Regular/Ruim: Revisão problemática. O agente omitiu erros críticos do texto original, sofreu de pedantismo excessivo, fez interpretações levemente equivocadas ou forneceu sugestões vagas que pouco ajudam o autor (ex: "melhore a fluidez").
[00 - 39] Inaceitável: Falha total. O agente inventou erros (alucinação flagrante), criticou o que estava correto, apresentou sugestões ilógicas, ou quebrou completamente o formato de saída exigido no JSON.
</evaluation_rubric>

<thinking_process>
Antes de gerar sua avaliação final, realize a seguinte análise passo a passo:
1. Verificação de Alucinação e Contexto: Faça uma busca no texto original. O trecho criticado realmente existe? O agente compreendeu a intenção do autor ou tirou a frase de contexto?
2. Calibragem de Escopo e Densidade: Qual a verdadeira carga cognitiva desta seção? É uma seção curta e protocolar (Título) ou analítica (Metodologia)?
3. Teste do Ponto Cego e Aprovação: Faça uma leitura crítica independente do texto original. Há uma falha grave que o agente ignorou? Por outro lado, se o agente júnior não apontou erros, o texto do autor é de fato sólido o suficiente para justificar uma aprovação sem ressalvas?
4. Análise de Acionabilidade: Teste de empatia: Se você fosse o autor do manuscrito recebendo essa sugestão, você saberia EXATAMENTE qual tecla bater no teclado para corrigir o erro?
5. Análise Lógica: O diagnóstico (problema) e a cura (sugestão) combinam perfeitamente? A tag "Tipo" condiz com as regras de classificação?
6. Definição da Nota Final: Com base na sua avaliação qualitativa dos critérios e nas faixas de pontuação da rubrica, determine diretamente a nota global (um número inteiro entre 0 e 100) que reflita com precisão o valor da revisão auditada.
</thinking_process>

<output_format>
REGRA ABSOLUTA E INEGOCIÁVEL: 
Retorne DIRETAMENTE E APENAS o número inteiro (de 0 a 100) representando a nota final. 
Você NÃO deve fornecer saudações, NÃO deve escrever justificativas, NÃO deve abrir tags (como <thinking_process>) na resposta, e NÃO deve imprimir nenhum texto adicional. Apenas os dígitos numéricos.

Exemplo de saída correta:
85
</output_format>

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
