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
Você DEVE gerar o relatório contendo EXATAMENTE estes três cabeçalhos principais (Nível 2):

## 1. Visão Geral do Documento e Integração entre Seções
Analise o documento como um todo com base nas revisões. Crie observações gerais focadas na coesão, coerência e integração lógica entre as diferentes seções do texto.

## 2. Revisões Detalhadas por Seção
Para CADA seção analisada (Título, Resumo, Introdução, Referencial Teórico, Metodologia, Resultados, Discussão e Conclusão, Referências), você DEVE criar um cabeçalho de nível 3 no formato exato `### Seção: [NOME DA SEÇÃO]`. Abaixo de cada cabeçalho, liste TODOS os apontamentos originais dessa seção.
Para cada observação, utilize OBRIGATORIAMENTE este formato de bloco Markdown:
*   **Trecho:** "[Citação do texto]"
    *   **Problema:** [Descrição da falha]
    *   **Sugestão:** [Como corrigir]
    *   **Tipo:** [Normativa ou Semântica]

**IMPORTANTE:**
- Não omita nenhuma seção, mesmo que não haja observações (neste caso, escreva "Nenhuma observação relevante").
- Use EXATAMENTE os rótulos em negrito: **Trecho:**, **Problema:**, **Sugestão:** e **Tipo:**.
- NÃO avalie erros gramaticais, ortográficos ou de formatação de fonte (itálico/negrito). Foque apenas no conteúdo técnico e estrutura acadêmica.

## 3. Conclusão da Revisão
Finalize com cabeçalhos de nível 3 para:
### Aspectos Positivos
[Liste os pontos fortes do trabalho]
### Problemas Principais
[Liste as falhas mais críticas]
### Sugestões Gerais de Melhoria
[Recomendações finais para o autor]

Formate o relatório em Markdown profissional, garantindo que os cabeçalhos ## 1., ## 2. e ## 3. sejam os principais divisores do documento. 
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
