from qdrant_client.models import (
    VectorParams,
    Distance,
    SparseVectorParams,
    SparseIndexParams,
    PointStruct,
    SparseVector as QdrantSparseVector,
    PointIdsList
)
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchAny, MatchValue, PayloadSchemaType
from src.rag.storage.base_vector_store import BaseVectorStorage, DenseVector, SparseVector, VectorPoint, VectorSearchResult
from src.rag.rag_schemas.search_filter import SearchFilter

DENSE_DIM = 1024

class QdrantVectorSearch(BaseVectorStorage):
    
    def __init__(self, client: AsyncQdrantClient, collection_name: str):
        self.client = client
        self.collection_name = collection_name
    
    def _build_qdrant_filter(self, filters: SearchFilter | None) -> Filter | None:
        if filters is None:
            return None
        
        list_fields = {
            'knowledge_pack': filters.knowledge_packs,
            'domain': filters.domains,
            'tags': filters.tags
        }
        
        scalar_fields = {
            'language': filters.language,
            'framework': filters.framework,
            'source_type': filters.source_type
        }
        
        conditions = []
        
        for key, value in list_fields.items():
            if value:
                conditions.append(FieldCondition(key = key, match = MatchAny(any = value)))
                
        for key, value in scalar_fields.items():
            if value:
                conditions.append(FieldCondition(key = key, match = MatchValue(value = value)))
        
        if not conditions:
            return None
        
        return Filter(must = conditions)
    
    async def upsert_batch(self, points: list[VectorPoint]) -> None:
        await self.client.upsert(
            collection_name=self.collection_name,
            points=[
                PointStruct(
                    id=point.id,
                    vector={
                        "dense": point.dense.values,
                        "sparse": QdrantSparseVector(
                            indices=point.sparse.indices,
                            values=point.sparse.values,
                        ),
                    },
                    payload=point.payload,
                )
                for point in points
            ],
        )
        
    async def upsert(self, point: VectorPoint) -> None:
        await self.upsert_batch([point])
        
    @classmethod
    async def create(cls, client: AsyncQdrantClient, collection_name: str) -> 'QdrantVectorSearch':
        instance = cls(client, collection_name)
        await instance.ensure_collection()
        return instance
    
    async def ensure_collection(self) -> None:
        
        exists = await self.client.collection_exists(self.collection_name)
        
        if not exists:
            await self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config={'dense': VectorParams(size = DENSE_DIM, distance = Distance.COSINE)},
                sparse_vectors_config={'sparse': SparseVectorParams(index = SparseIndexParams(on_disk = False))}
            )
            indexed_fields = ['knowledge_pack', 'domain', 'language', 'framework', 'source_type', 'tags']
            
            for field in indexed_fields:
                await self.client.create_payload_index(
                    collection_name=self.collection_name,
                    field_name = field,
                    field_schema = PayloadSchemaType.KEYWORD
                )
                
    async def search_dense(self, vector: DenseVector, limit: int, filters: SearchFilter | None = None) -> list[VectorSearchResult]:
        
        query_filter = self._build_qdrant_filter(filters)
        
        result = await self.client.query_points(
            collection_name = self.collection_name,
            query = vector.values,
            using = 'dense',
            limit = limit,
            query_filter=query_filter
        )
        
        return [
            VectorSearchResult(
                id = str(point.id),
                score = point.score,
                payload = point.payload or {}
            )
            for point in result.points
        ]
        
    async def search_sparse(self, vector: SparseVector, limit: int, filters: SearchFilter | None = None) -> list[VectorSearchResult]:
            query_filter = self._build_qdrant_filter(filters)
            
            result = await self.client.query_points(
                collection_name = self.collection_name,
                query=QdrantSparseVector(
                    indices=vector.indices,
                    values=vector.values,
                ),
                using = 'sparse',
                limit = limit,
                query_filter=query_filter
            )
            
            return [
                VectorSearchResult(
                    id = str(point.id),
                    score = point.score,
                    payload = point.payload or {}
                )
                for point in result.points
            ]
            
    async def delete(self, id: str) -> None:
        
        await self.client.delete(
            collection_name=self.collection_name,
            points_selector= PointIdsList(points = [id])
        )
        
    async def exists(self, id: str) -> bool:
        result = await self.client.retrieve(
            collection_name=self.collection_name,
            ids=[id],
        )
        return len(result) > 0