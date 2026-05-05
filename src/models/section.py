from pydantic import BaseModel, Field
from typing import Optional

class Section(BaseModel):
    """
    Representação da tupla s_j = <tipo_j, texto_j, pos_j>
    """
    type: str = Field(description="O tipo canônico da seção (ex: Introdução, Metodologia).")
    text: str = Field(description="O conteúdo em texto Markdown da seção.")
    position: int = Field(description="A posição ordinal da seção no documento.")
    
    # Optional fields for metadata
    page_start: Optional[int] = None
    page_end: Optional[int] = None
    document_id: Optional[str] = None
