import os
from pydantic import BaseModel, Field

class Settings(BaseModel):
    # LLM Settings
    openai_api_key: str = Field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))
    gemini_api_key: str = Field(default_factory=lambda: os.getenv("GEMINI_API_KEY", ""))
    anthropic_api_key: str = Field(default_factory=lambda: os.getenv("ANTHROPIC_API_KEY", ""))
    
    # Model Defaults
    embedding_model: str = "gemini/gemini-embedding-2" # Modelo de embedding do Google atualizado
    
    # Parser Default ("mineru", "docling", "markitdown")
    default_parser: str = "docling"
    
    # System Thresholds
    quality_threshold: float = 80.0
    max_attempts: int = 3
    
    # ChromaDB Settings
    chroma_db_dir: str = "./chroma_db_gemini2"
    chroma_collection_name: str = "reviews_history"
    
    # RAG Settings
    k_nearest_neighbors: int = 3

settings = Settings()
