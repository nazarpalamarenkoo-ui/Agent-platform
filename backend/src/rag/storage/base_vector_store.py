from abc import ABC, abstractmethod
from dataclasses import dataclass

from src.rag.rag_schemas.search_filter import SearchFilter

@dataclass
class VectorSearchResult:
    id: str
    score: float
    payload: dict
    
@dataclass
class DenseVector:
    values: list[float]

@dataclass  
class SparseVector:
    indices: list[int]
    values: list[float]

@dataclass
class VectorPoint:
    id: str
    dense: DenseVector
    sparse: SparseVector
    payload: dict
    
class BaseVectorStorage(ABC):
    
    @abstractmethod
    async def upsert(self, point: VectorPoint) -> None:
        pass

    @abstractmethod
    async def upsert_batch(self, points: list[VectorPoint]) -> None:
        pass

    @abstractmethod
    async def search_dense(self, vector: DenseVector, limit: int, filters: SearchFilter | None = None) -> list[VectorSearchResult]:
        pass

    @abstractmethod
    async def search_sparse(self, vector: SparseVector, limit: int, filters: SearchFilter | None = None) -> list[VectorSearchResult]:
        pass
    
    @abstractmethod
    async def delete(self, id: str) -> None:
        pass
    
    @abstractmethod
    async def exists(self, id: str) -> bool:
        pass