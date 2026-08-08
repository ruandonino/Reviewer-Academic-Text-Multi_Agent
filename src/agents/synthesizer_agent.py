import json
import re
from typing import List, Tuple, Any
from src.utils.llm_client import calculate_completion_cost, safe_completion as completion
from src.models.review import ReviewResult
from src.config import settings
from src.ingestion.segmenter import CANONICAL_SECTIONS
from src.utils.logger import get_logger
from src.utils.section_mapping import resolve_section_key

logger = get_logger()

SYNTHESIZER_MODEL = settings.synthesizer_model


def _section_heading(index: int, section_type: str) -> str:
    return f"### 2.{index} {section_type.title()}"


def _canonical_section_key(section_type: str) -> str:
    """Resolve aliases before comparing section types across pipeline stages."""
    return resolve_section_key(section_type) or section_type.strip().lower()


def _fallback_report(
    reviews_with_sections: List[Tuple[Any, ReviewResult]],
    expected_sections: List[Tuple[int, str]],
) -> str:
    """Preserva as revisoes estruturadas quando a sintese do provedor falhar."""
    reviews_by_type = {
        _canonical_section_key(sec.type): review
        for sec, review in reviews_with_sections
        if sec.type
    }

    lines = [
        "## 1. Visao Geral do Documento e Integracao entre Secoes",
        "",
    ]
    general_comments = []
    for _, section_type in expected_sections:
        review = reviews_by_type.get(_canonical_section_key(section_type))
        if review and review.general_comments.strip():
            general_comments.append(
                f"- **{section_type.title()}:** {review.general_comments.strip()}"
            )
    lines.extend(general_comments or ["- Revisoes parciais consolidadas por secao."])
    lines.extend(["", "## 2. Revisoes Detalhadas por Secao", ""])

    all_observations = []
    for index, section_type in expected_sections:
        review = reviews_by_type.get(_canonical_section_key(section_type))
        lines.extend([_section_heading(index, section_type), ""])
        observations = review.observations if review else []
        if not observations:
            lines.extend(["Nenhuma observacao relevante.", ""])
            continue

        for observation_index, observation in enumerate(observations, start=1):
            observation_type = (
                "Normativa"
                if observation.type.strip().lower() == "normativa"
                else "Semantica"
            )
            lines.extend([
                f'{observation_index}. **Trecho:** "{observation.quote}"',
                f"   - **Problema:** {observation.issue}",
                f"   - **Sugestao:** {observation.suggestion}",
                f"   - **Tipo:** {observation_type}",
                "",
            ])
            all_observations.append(observation)

    lines.extend([
        "## 3. Conclusao da Revisao",
        "### Aspectos Positivos",
        "- Consulte as revisoes detalhadas para os aspectos positivos identificados em cada secao.",
        "",
        "### Problemas Principais",
        (
            f"- Foram preservadas {len(all_observations)} observacoes das revisoes parciais. "
            "Priorize as que afetam evidencias, metodo, resultados e conclusoes."
        ),
        "",
        "### Sugestoes Gerais de Melhoria",
        "- Execute as correcoes indicadas nas secoes correspondentes e revise a consistencia entre metodo, resultados e conclusoes.",
    ])
    return "\n".join(lines)

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
    present_section_keys = {
        _canonical_section_key(sec.type)
        for sec, _ in reviews_with_sections
        if sec.type
    }
    expected_sections = [
        (index, section_type)
        for index, section_type in enumerate(CANONICAL_SECTIONS, start=1)
        if _canonical_section_key(section_type) in present_section_keys
    ]
    expected_section_list = ", ".join(
        f"{index}. {section_type.title()}"
        for index, section_type in expected_sections
    )
    expected_section_headings = [
        _section_heading(index, section_type)
        for index, section_type in expected_sections
    ]
    expected_section_names = ", ".join(
        section_type.title() for _, section_type in expected_sections
    )
    expected_section_contract = "\n".join(
        f"- {heading}" for heading in expected_section_headings
    )
    
    prompt = f"""
Você é o Agente Sintetizador de um sistema de revisão acadêmica.
Sua tarefa é consolidar as revisões parciais das diferentes seções de um trabalho acadêmico em um Relatório Final unificado e coeso.

## Revisões Parciais:
{all_reviews_text}

## Seções Analisadas:
{expected_section_list}

Crie subseções detalhadas somente para as seções listadas acima. Se uma seção canônica não estiver presente nas revisões parciais, ela não foi identificada pelo parser e não deve ser inventada, exigida ou tratada como falha.

## Contrato Literal dos Cabecalhos Detalhados:
{expected_section_contract}

Use exatamente esses cabecalhos, na mesma ordem e com a mesma numeracao. Nao renumere os cabecalhos quando uma secao canonica estiver ausente. Inclua todos os cabecalhos deste contrato, inclusive quando a secao nao tiver observacoes.

## Política Obrigatória de Classificação:
Classifique cada observação pelo motivo principal da correção. Seja rigoroso, verificável e baseado exclusivamente nas revisões recebidas; não invente falhas, dados, fontes ou trechos. Não inclua erros de gramática, ortografia, digitação, concordância, espaçamento ou outros erros meramente linguístico-mecânicos.

- **Normativa:** não conformidade verificável com uma norma acadêmica, bibliográfica, editorial ou institucional identificável, como ABNT, APA, IEEE, Vancouver ou manual formal da instituição. Inclui citação e referência que descumpram a norma aplicável; numeração, identificação, legenda, referência cruzada, hierarquia ou apresentação de seções, figuras, tabelas e equações quando a exigência decorrer dessa norma; e elementos obrigatórios definidos explicitamente pelo manual aplicável.
- **Semântica:** qualidade do conteúdo científico: conceito, explicação, lógica, escopo, argumentação ou interpretação; termos técnicos/siglas não explicados; método sem justificativa; dados sem caracterização; unidades, protocolos, seeds, hiperparâmetros ou validação ausentes; evidências quantitativas, análise estatística, limitações, vieses, reprodutibilidade ou comparação crítica insuficientes; artefato visual ausente quando impede compreender, validar ou comparar o argumento.

Em caso de dúvida, classifique como **Semântica** quando a correção exigir alterar conteúdo, evidência, método ou interpretação para tornar a pesquisa cientificamente válida. Use **Normativa** somente quando o conteúdo já for suficiente e for possível vincular a falha a uma exigência formal verificável de ABNT, APA, IEEE, Vancouver ou manual institucional. Citação ou referência em desacordo com uma norma aplicável é Normativa; conceito ou sigla não explicado é Semântica. Legenda, numeração, posição e referência cruzada são Normativas apenas quando a exigência formal aplicável justificar o apontamento; tabela, figura ou diagrama necessário para sustentar evidência, explicar método ou comparar resultados é Semântico.

Antes de definir `Tipo`, aplique este teste causal: pergunte se, sem a correção, um leitor consegue avaliar a validade da afirmação, compreender como o estudo foi conduzido, reproduzir o procedimento ou interpretar o resultado. Se a resposta for não, classifique como **Semântica**, mesmo que a ação sugerida seja adicionar uma citação, uma tabela, uma figura, uma subseção, uma legenda ou uma referência. Classifique como **Normativa** somente se a falha puder ser corrigida sem mudar a suficiência científica do conteúdo, das evidências, do método ou da interpretação e se existir uma norma formal aplicável que a descreva. Se não houver impacto científico nem norma verificável, não gere uma observação.

Não use a forma superficial do apontamento como atalho de classificação: a presença das palavras “citação”, “referência”, “tabela”, “figura”, “equação” ou “seção” não torna uma observação automaticamente Normativa. O rótulo Normativa exige indicar, no diagnóstico ou na sugestão, qual padrão formal é descumprido. Por exemplo, referência em formato incompatível com ABNT ou APA é Normativa; evidência ou fundamento bibliográfico insuficiente para sustentar uma afirmação científica é Semântica. Tabela ausente apenas quando uma norma exige sua identificação ou apresentação é Normativa; tabela necessária para revelar variabilidade, permitir comparação ou sustentar uma conclusão é Semântica. Uma subseção ou referência cruzada ausente é Normativa apenas se contrariar uma estrutura formal exigida; informações de protocolo, amostra, parâmetros, critérios de avaliação, limitações ou resultados que não foram apresentados são Semânticas.

Ao consolidar as revisões, preserve o diagnóstico substantivo do agente de origem. Não rebaixe uma observação Semântica para Normativa apenas porque a sugestão inclui um ajuste de apresentação; se houver os dois aspectos, classifique pelo impacto principal e mantenha o aspecto secundário na sugestão.

Preserve, na seção de origem, recomendações prospectivas fundamentadas pelo escopo ou pelas premissas da seção revisada.

Preserve também recomendações e questionamentos técnicos específicos do domínio quando estiverem ligados a uma afirmação, escolha, resultado, omissão ou limitação concreta da seção. Não os elimine apenas porque exigem conhecimento especializado; elimine somente duplicatas reais ou itens sem conexão verificável com a seção analisada.

Não agrupe observações que tenham causas científicas distintas, ainda que incidam sobre o mesmo trecho. Elimine apenas duplicatas que apresentem o mesmo diagnóstico e demandem essencialmente a mesma correção.

## Estrutura Exigida para o Relatório:
1. Visão Geral do Documento e Integração entre Seções: Analise o documento como um todo com base nas revisões. Crie observações gerais focadas na coesão, coerência e integração lógica entre as diferentes seções do texto (ex: os métodos descritos sustentam a conclusão? A introdução dialoga bem com o referencial teórico?).
2. Revisões Detalhadas por Seção seguindo a ordem canônica das seções do documento (Título, Resumo, Introdução, etc.): Para CADA seção analisada, você DEVE listar TODOS os apontamentos gerados que sejam do tipo "semântica" ou "normativa". Para cada observação, apresente explicitamente no formato de lista:
**RESTRIÇÃO:** Use somente os nomes das seções presentes no Contrato Literal dos Cabeçalhos Detalhados ({expected_section_names}). Qualquer seção detalhada fora desse contrato será considerada uma falha grave.
Essa restrição aplica-se somente às seções analisadas listadas acima; a ausência de uma seção não identificada pelo parser não é falha.
**RESTRIÇÃO:** **NÃO AVALIE:** Erros de digitação, erros gramaticais, erros ortográficos, uso de itálico ou formatação de fonte. Se você encontrar um erro desse tipo, IGNORE-O.
   - Trecho (Insira a referência ou o trecho que apresenta a falha)
   - Problema (Issue)
   - Sugestão (Suggestion)
   - Tipo (Normativa ou Semântica)
**IMPORTANTE**   Não omita nenhuma observação. Apresente todas de forma organizada.

## Contrato Obrigatório de Markdown
Use exatamente os títulos e rótulos abaixo. Não altere os nomes, não omita os dois-pontos e não use tabelas para as observações.

```markdown
## 1. Visão Geral do Documento e Integração entre Seções

## 2. Revisões Detalhadas por Seção

### 2.1 Título
1. **Trecho:** "trecho literal do trabalho"
   - **Problema:** descrição objetiva da falha
   - **Sugestão:** ação concreta para corrigi-la
   - **Tipo:** Normativa

### 2.2 Resumo
1. **Trecho:** "trecho literal do trabalho"
   - **Problema:** descrição objetiva da falha
   - **Sugestão:** ação concreta para corrigi-la
   - **Tipo:** Semântica

## 3. Conclusão da Revisão
### Aspectos Positivos
### Problemas Principais
### Sugestões Gerais de Melhoria
```

Repita o padrão `### 2.N Nome da Seção` para cada seção analisada, usando exatamente os nomes presentes no Contrato Literal dos Cabeçalhos Detalhados: {expected_section_names}. Cada observação deve conter os quatro rótulos em linhas separadas e `Tipo` deve ser exatamente `Normativa` ou `Semântica`.
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
                messages=[{"role": "user", "content": prompt}],
                max_tokens=settings.synthesizer_max_tokens,
            )
            choice = response.choices[0]
            finish_reason = getattr(choice, "finish_reason", None)
            if finish_reason in {"error", "length"}:
                raise RuntimeError("O provedor retornou finish_reason=error para a sÃ­ntese final.")

            report = (choice.message.content or "").strip()
            if not report:
                raise RuntimeError("O provedor retornou uma sÃ­ntese final vazia.")

            # A resposta parcial pode ser devolvida como sucesso quando o provedor
            # converte um erro de geraÃ§Ã£o em finish_reason=stop. Rejeite-a antes
            # de gravar Markdown/JSON para que o retry gere um relatÃ³rio completo.
            missing_headings = [
                heading
                for heading in expected_section_headings
                if not re.search(
                    rf"(?m)^{re.escape(heading)}(?:\s|$)",
                    report,
                    flags=re.IGNORECASE,
                )
            ]
            if missing_headings:
                raise RuntimeError(
                    "SÃ­ntese final incompleta; seÃ§Ãµes ausentes: " + ", ".join(missing_headings)
                )
            
            tokens = response.usage.total_tokens if hasattr(response, 'usage') and response.usage else 0
            try:
                cost = calculate_completion_cost(response, SYNTHESIZER_MODEL)
            except Exception as cost_error:
                logger.warning(f"Não foi possível calcular o custo do Sintetizador para o modelo {SYNTHESIZER_MODEL}: {cost_error}")
                cost = 0.0
                
            logger.info("Síntese concluída com sucesso.")
            return report, tokens, cost
        except Exception as e:
            logger.error(f"Erro ao sintetizar relatório final (Tentativa {attempt+1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                logger.info("Aguardando 60 segundos para tentar novamente...")
                time.sleep(60)
            else:
                logger.error(
                    "Sintese indisponivel apos todas as tentativas; "
                    "gerando relatorio estruturado a partir das revisoes parciais."
                )
                return _fallback_report(reviews_with_sections, expected_sections), 0, 0.0
