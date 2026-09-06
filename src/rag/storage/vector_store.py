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
from src.rag.storage.base_vector_store import BaseVectorStorage, DenseVector, SparseVector, VectorPoint, VectorSearchResult

DENSE_DIM = 1024

class QdrantVectorSearch(BaseVectorStorage):
    
    def __init__(self, client: AsyncQdrantClient, collection_name: str):
        self.client = client
        self.collection_name = collection_name
        
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
                vectors_config={
                    'dense': VectorParams(size = DENSE_DIM, distance = Distance.COSINE)
                },
                sparse_vectors_config={
                    'sparse': SparseVectorParams(index = SparseIndexParams(on_disk = False))
                }
            )
            
    async def search_dense(self, vector: DenseVector, limit: int, ) -> list[VectorSearchResult]:
        
        result = await self.client.query_points(
            collection_name = self.collection_name,
            query = vector.values,
            using = 'dense',
            limit = limit
        )
        
        return [
            VectorSearchResult(
                id = str(point.id),
                score = point.score,
                payload = point.payload or {}
            )
            for point in result.points
        ]
        
    async def search_sparse(self, vector: SparseVector, limit: int) -> list[VectorSearchResult]:
            
            result = await self.client.query_points(
                collection_name = self.collection_name,
                query=QdrantSparseVector(
                    indices=vector.indices,
                    values=vector.values,
                ),
                using = 'sparse',
                limit = limit
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