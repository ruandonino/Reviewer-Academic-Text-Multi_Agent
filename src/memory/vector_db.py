import chromadb
from chromadb.config import Settings as ChromaSettings
from typing import List, Dict, Any, Optional, Tuple
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

    def index_record(self, record: SummaryRecord) -> Tuple[int, float]:
        """
        Indexa um registro no banco de dados vetorial. Retorna (tokens, custo).
        """
        try:
            vector, tokens, cost = gerar_embedding(record.text_content)
            
            if not vector:
                logger.warning(f"Ignorando indexação do registro {record.id} - embedding vazio.")
                return 0, 0.0
                
            self.collection.add(
                documents=[record.text_content],
                embeddings=[vector],
                metadatas=[{
                    "id": record.id,
                    "section_type": record.section_type,
                    "architecture_used": record.architecture_used,
                    "models_used": ",".join(record.models_used),
                    "evaluation_score": record.evaluation_score,
                    "cost_usd": record.cost_usd,
                    # Converter complex objects para string/json se necessário para o ChromaDB
                    "text_summary": record.text_summary
                }],
                ids=[record.id]
            )
            logger.info(f"Registro {record.id} indexado com sucesso no ChromaDB.")
            return tokens, cost
        except Exception as e:
            logger.error(f"Falha ao indexar registro {record.id}: {e}")
            return 0, 0.0

    def retrieve_context(self, section_text: str, section_type: str, k: int = 3) -> Tuple[List[Dict[str, Any]], int, float]:
        """
        Realiza a busca por similaridade semântica para RAG do Roteador (Etapa 2).
        Retorna (historico, tokens, custo).
        """
        try:
            vector, tokens, cost = gerar_embedding(section_text)
            if not vector:
                return [], 0, 0.0
                
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
            return historico, tokens, cost
            
        except Exception as e:
            logger.error(f"Falha ao recuperar contexto do ChromaDB: {e}")
            return [], 0, 0.0

# Singleton instance
vector_db = VectorDB()
