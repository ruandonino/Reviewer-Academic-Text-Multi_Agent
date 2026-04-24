import chromadb
from chromadb.config import Settings as ChromaSettings
from typing import List, Dict, Any, Optional
from src.config import settings
from src.models.summary import SummaryRecord
from src.memory.embeddings import gerar_embedding
from src.utils.logger import get_logger

logger = get_logger()

class VectorDB:
    """
    Gerencia a persistência e busca vetorial (ChromaDB) (RF02, RF06)
    """
    def __init__(self):
        self.client = chromadb.PersistentClient(
            path=settings.chroma_db_dir,
            settings=ChromaSettings(allow_reset=True)
        )
        self.collection = self.client.get_or_create_collection(
            name=settings.chroma_collection_name,
            metadata={"hnsw:space": "cosine"}
        )
        logger.info(f"Conectado ao ChromaDB em {settings.chroma_db_dir}")

    def index_record(self, record: SummaryRecord):
        """
        Indexa um registro no banco de dados vetorial.
        """
        try:
            vector = gerar_embedding(record.text_content)
            
            if not vector:
                logger.warning(f"Ignorando indexação do registro {record.id} - embedding vazio.")
                return
                
            self.collection.add(
                documents=[record.text_content],
                embeddings=[vector],
                metadatas=[{
                    "id": record.id,
                    "section_type": record.section_type,
                    "architecture_used": record.architecture_used,
                    "evaluation_score": record.evaluation_score,
                    "cost_usd": record.cost_usd,
                    # Converter complex objects para string/json se necessário para o ChromaDB
                    "text_summary": record.text_summary
                }],
                ids=[record.id]
            )
            logger.info(f"Registro {record.id} indexado com sucesso no ChromaDB.")
        except Exception as e:
            logger.error(f"Falha ao indexar registro {record.id}: {e}")

    def retrieve_context(self, section_text: str, section_type: str, k: int = 3) -> List[Dict[str, Any]]:
        """
        Realiza a busca por similaridade semântica para RAG do Roteador (Etapa 2).
        """
        try:
            vector = gerar_embedding(section_text)
            if not vector:
                return []
                
            results = self.collection.query(
                query_embeddings=[vector],
                n_results=k,
                where={"section_type": section_type} # Filtragem categórica
            )
            
            historico = []
            if results and results['metadatas'] and len(results['metadatas'][0]) > 0:
                for i in range(len(results['ids'][0])):
                    historico.append({
                        "id": results['ids'][0][i],
                        "document": results['documents'][0][i],
                        "metadata": results['metadatas'][0][i],
                        "distance": results['distances'][0][i] if 'distances' in results else None
                    })
            
            logger.info(f"Recuperados {len(historico)} registros históricos para o tipo '{section_type}'.")
            return historico
            
        except Exception as e:
            logger.error(f"Falha ao recuperar contexto do ChromaDB: {e}")
            return []

# Singleton instance
vector_db = VectorDB()
