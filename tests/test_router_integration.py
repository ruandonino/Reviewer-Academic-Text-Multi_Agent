import os
import sys
import uuid
import json
import time
import concurrent.futures

# Adiciona a raiz do projeto ao sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.models.section import Section
from src.models.review import ReviewResult, Observation
from src.models.summary import SummaryRecord
from src.memory.vector_db import vector_db
from src.agents.router_agent import route_section
from src.utils.logger import get_logger
from dotenv import load_dotenv

load_dotenv()
logger = get_logger()

def setup_fake_history():
    """Popula o ChromaDB com dados realistas de histórico de revisões."""
    logger.info("Populando o banco vetorial com histórico falso realista...")
    
    # Histórico 1: Uma revisão de Metodologia ruim usando arquitetura Single
    rev_ruim = ReviewResult(
        general_comments="A seção de metodologia está muito superficial. Faltam detalhes cruciais sobre a amostragem.",
        observations=[
            Observation(
                quote="A amostra foi selecionada por conveniência.",
                issue="Falta o tamanho da amostra e os critérios exatos de inclusão e exclusão.",
                suggestion="Especifique o N total da amostra e liste os critérios demográficos.",
                type="Semântica"
            )
        ]
    )
    rec_1 = SummaryRecord(
        id="fake-history-metodologia-ruim",
        section_type="metodologia",
        text_content="A pesquisa caracteriza-se como quantitativa. A amostra foi selecionada por conveniência entre os alunos do curso de Computação. Os dados foram coletados via questionário online.",
        text_summary="Metodologia quantitativa com amostragem por conveniência via questionário. Revisão apontou falta de detalhamento da amostra.",
        approved_review=rev_ruim,
        architecture_used="Single",
        models_used=["gemini/gemini-2.5-flash-lite"],
        evaluation_score=60.0, # Nota baixa!
        cost_tokens=1000,
        cost_usd=0.010
    )
    
    # Histórico 2: Uma revisão de Metodologia excelente usando arquitetura Debate
    rev_boa = ReviewResult(
        general_comments="Excelente detalhamento metodológico. Os agentes identificaram com precisão lacunas na validação dos instrumentos.",
        observations=[
            Observation(
                quote="Foi aplicado um questionário de 10 perguntas.",
                issue="Não há menção se o questionário foi validado por pares ou se é um instrumento padronizado na literatura.",
                suggestion="Indique a origem do questionário ou o processo de validação (ex: Alpha de Cronbach) antes da aplicação final.",
                type="Semântica"
            )
        ]
    )
    rec_2 = SummaryRecord(
        id="fake-history-metodologia-boa",
        section_type="metodologia",
        text_content="Este estudo adota uma abordagem mista (quali-quanti). A população alvo constitui-se de 500 discentes. A amostra probabilística estratificada resultou em n=120. Foi aplicado um questionário de 10 perguntas focado em usabilidade.",
        text_summary="Estudo misto com amostragem estratificada (n=120) e questionário. Múltiplos agentes identificaram a necessidade de descrever a validação do questionário.",
        approved_review=rev_boa,
        architecture_used="Debate",
        models_used=["gemini/gemini-2.5-flash-lite", "gemini/gemma-3-27b-it", "claude-3-5-sonnet-20241022"],
        evaluation_score=92.0, # Nota alta!
        cost_tokens=4500,
        cost_usd=0.045
    )

    # Histórico 3: Uma seção de tipo diferente (Introdução)
    rev_intro = ReviewResult(
        general_comments="A introdução apresenta bem o tema, mas a justificativa é fraca.",
        observations=[
            Observation(
                quote="O trabalho é importante pois sistemas multiagentes são legais.",
                issue="Justificativa carece de rigor acadêmico e embasamento na literatura.",
                suggestion="Substitua por uma justificativa que aponte lacunas reais na literatura atual sobre SMA.",
                type="Semântica"
            )
        ]
    )
    rec_3 = SummaryRecord(
        id="fake-history-introducao",
        section_type="introdução",
        text_content="Este trabalho discute sistemas multiagentes. O trabalho é importante pois sistemas multiagentes são legais e têm muitas aplicações na indústria.",
        text_summary="Introdução sobre sistemas multiagentes. Avaliação apontou falta de rigor na justificativa.",
        approved_review=rev_intro,
        architecture_used="Single",
        models_used=["gemini/gemini-2.5-flash-lite"],
        evaluation_score=75.0,
        cost_tokens=1200,
        cost_usd=0.012
    )

    # Histórico 4: Outra seção de tipo diferente (Conclusão)
    rev_conclusao = ReviewResult(
        general_comments="A conclusão não retoma os objetivos específicos.",
        observations=[
            Observation(
                quote="Concluímos que o sistema funciona bem.",
                issue="Falta síntese de como os objetivos propostos na introdução foram alcançados.",
                suggestion="Adicione um parágrafo relacionando os resultados aos objetivos específicos 1 e 2.",
                type="Normativa"
            )
        ]
    )
    rec_4 = SummaryRecord(
        id="fake-history-conclusao",
        section_type="conclusão",
        text_content="Em suma, concluímos que o sistema funciona bem e resolve os problemas propostos inicialmente, garantindo boa performance.",
        text_summary="Conclusão genérica. Revisão sugeriu retomar objetivos específicos.",
        approved_review=rev_conclusao,
        architecture_used="Single",
        models_used=["gemini/gemini-2.5-flash-lite"],
        evaluation_score=80.0,
        cost_tokens=800,
        cost_usd=0.008
    )

    # Histórico 5: Metodologia completamente diferente (Ex: Teórica/Matemática)
    rev_teo = ReviewResult(
        general_comments="A modelagem matemática das equações diferenciais está correta, mas as premissas não foram justificadas.",
        observations=[
            Observation(
                quote="Assumimos que o atrito é zero na equação (3).",
                issue="A premissa de atrito zero em um modelo fluido precisa de justificativa teórica.",
                suggestion="Inclua citação justificando esta premissa ou cite os limites do modelo.",
                type="Semântica"
            )
        ]
    )
    rec_5 = SummaryRecord(
        id="fake-history-metodologia-teorica",
        section_type="metodologia",
        text_content="A modelagem foi baseada nas equações de Navier-Stokes. Assumimos que o atrito é zero na equação (3) para simplificar a solução analítica proposta no teorema 1.",
        text_summary="Metodologia baseada em modelagem matemática e equações diferenciais. Revisão exigiu justificativa para premissa de atrito zero.",
        approved_review=rev_teo,
        architecture_used="Chain",
        models_used=["claude-3-5-sonnet-20241022", "gemini/gemma-3-27b-it"],
        evaluation_score=88.0,
        cost_tokens=3000,
        cost_usd=0.030
    )

    vector_db.index_record(rec_1)
    vector_db.index_record(rec_2)
    vector_db.index_record(rec_3)
    vector_db.index_record(rec_4)
    vector_db.index_record(rec_5)
    logger.info("Histórico populado com sucesso (5 registros inseridos).")

def process_single_section(section: Section):
    """Função auxiliar para rotear uma única seção e registrar o resultado."""
    logger.info(f"[{section.type.upper()}] Iniciando processamento...")
    start_time = time.time()
    
    decision, history_context = route_section(section)
    
    end_time = time.time()
    logger.info(f"[{section.type.upper()}] Concluído em {end_time - start_time:.2f}s | Arquitetura: {decision.architecture} | Histórico recuperado: {len(history_context)} registros")
    return section.type, decision, history_context

def test_router_integration():
    # Verificar chaves de API necessárias
    has_gemini = bool(os.getenv("GEMINI_API_KEY"))
    has_openai = bool(os.getenv("OPENAI_API_KEY"))
    
    if not has_gemini:
        logger.error("GEMINI_API_KEY não encontrada. O sistema RAG precisa do Gemini para os Embeddings.")
        return
        
    if not has_openai:
        logger.warning("OPENAI_API_KEY não encontrada. Se o Roteador estiver configurado para usar GPT-4o, ele falhará.")

    logger.info("=== Iniciando Teste de Integração do Roteador (Processamento Paralelo) ===")
    
    # 1. Preparar o banco de dados (Contexto RAG)
    setup_fake_history()
    
    # 2. Criar Múltiplas Seções Alvo
    target_sections = [
        Section(
            type="metodologia",
            position=3,
            text="O presente trabalho utilizou uma metodologia qualitativa baseada em entrevistas semiestruturadas. Foram entrevistados alunos matriculados no oitavo período de Ciência da Computação. As perguntas abordaram a percepção sobre sistemas multiagentes. Os resultados foram analisados posteriormente."
        ),
        Section(
            type="introdução",
            position=1,
            text="A inteligência artificial tem revolucionado a forma como interagimos com a tecnologia. Este trabalho propõe um novo framework de revisão acadêmica baseado em agentes autônomos, visando reduzir o tempo gasto por orientadores em correções normativas."
        ),
        Section(
            type="conclusão",
            position=6,
            text="Diante dos resultados obtidos, confirmamos que o uso de sistemas multiagentes para revisão de textos é não apenas viável, mas altamente eficiente. A precisão na detecção de erros da ABNT aumentou em 40% em relação às ferramentas tradicionais."
        ),
        Section(
            type="referencial teórico",
            position=2,
            text="Segundo Silva (2020), a revisão por pares é um processo fundamental. Já Santos e Souza (2021) argumentam que a automação pode introduzir vieses. Modelos LLM, conforme definido por Vaswani et al. (2017), baseiam-se na arquitetura Transformer."
        )
    ]
    
    logger.info(f"\nEnviando {len(target_sections)} seções SIMULTANEAMENTE para o Agente Roteador...")
    
    # 3. Executar o Roteador concorrentemente usando ThreadPoolExecutor
    resultados = []
    start_total = time.time()
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(target_sections)) as executor:
        # Submete as tarefas
        future_to_section = {executor.submit(process_single_section, sec): sec for sec in target_sections}
        
        # Coleta os resultados assim que terminarem
        for future in concurrent.futures.as_completed(future_to_section):
            sec = future_to_section[future]
            try:
                res = future.result()
                resultados.append(res)
            except Exception as exc:
                logger.error(f"[{sec.type.upper()}] Gerou uma exceção: {exc}")
                
    end_total = time.time()
    
    # 4. Exibir e Validar os Resultados
    logger.info("\n" + "="*80)
    logger.info(f"RESULTADOS DA INTEGRAÇÃO PARALELA (Tempo Total: {end_total - start_total:.2f}s)")
    logger.info("="*80)
    
    for sec_type, decision, history_context in resultados:
        logger.info(f"\n--- SEÇÃO: {sec_type.upper()} ---")
        logger.info(f"Contextos RAG Recuperados: {len(history_context)}")
        for i, h in enumerate(history_context):
            meta = h.get("metadata", {})
            logger.info(f"   [{i+1}] {meta.get('section_type')} | {meta.get('architecture_used')} | Score: {meta.get('evaluation_score')}")
            
        logger.info(f"Decisão da Arquitetura: {decision.architecture}")
        logger.info(f"Modelos Alocados: {[m.model_id for m in decision.models]}")
        logger.info(f"Raciocínio: {decision.reasoning}")
        logger.info("-" * 40)

    logger.info("\n=== Teste de Integração Concluído ===")

if __name__ == "__main__":
    test_router_integration()
