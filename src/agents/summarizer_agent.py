import uuid
from litellm import completion
from src.models.section import Section
from src.models.router import RouterDecision
from src.models.review import ReviewResult
from src.models.summary import SummaryRecord
from src.memory.vector_db import vector_db
from src.utils.logger import get_logger

logger = get_logger()

SUMMARIZER_MODEL = "gemini/gemini-2.5-flash-lite"

def summarize_and_index(
    section: Section, 
    review: ReviewResult, 
    decision: RouterDecision, 
    score: float, 
    cost_tokens: int = 0, 
    cost_usd: float = 0.0
) -> SummaryRecord:
    """
    Condensa o conteúdo e salva na memória de longo prazo (Etapa 6)
    """
    logger.info(f"Iniciando sumarização para a seção: {section.type}")
    
    prompt = f"""
Resuma o texto abaixo em no máximo 3 parágrafos, focando nos conceitos principais, metodologias ou resultados descritos. 
Isso será usado para buscas semânticas futuras.

Texto Original:
{section.text[:3000]}...
"""

    try:
        response = completion(
            model=SUMMARIZER_MODEL,
            messages=[{"role": "user", "content": prompt}]
        )
        text_summary = response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"Erro ao gerar resumo textual: {e}")
        text_summary = "Resumo indisponível devido a erro."

    record = SummaryRecord(
        id=str(uuid.uuid4()),
        section_type=section.type,
        text_content=section.text,
        text_summary=text_summary,
        approved_review=review,
        architecture_used=decision.architecture,
        models_used=[m.model_id for m in decision.models],
        evaluation_score=score,
        cost_tokens=cost_tokens,
        cost_usd=cost_usd
    )
    
    vector_db.index_record(record)
    logger.info(f"Sumarização e indexação concluídas (ID: {record.id})")
    
    return record
