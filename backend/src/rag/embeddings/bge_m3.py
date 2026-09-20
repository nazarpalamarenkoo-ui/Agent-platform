from FlagEmbedding import BGEM3FlagModel
from dataclasses import dataclass
import numpy as np
from src.rag.storage.base_vector_store import DenseVector, SparseVector

@dataclass
class EmbeddingResult:
    dense: DenseVector
    sparse: SparseVector
    
class Embedding:
    
    def __init__(self):
        self.model = BGEM3FlagModel('BAAI/bge-m3', use_fp16 = True, batch_size = 512)
        
    def embed(self, query: list[str]) -> list[EmbeddingResult]:
        
        output = self.model.encode(query, return_dense = True, return_sparse = True, return_colbert_vecs=False)
        
        return [
            EmbeddingResult(
                dense=DenseVector(values=d.tolist() if isinstance(d, np.ndarray) else d),  # type: ignore
                sparse=self._convert_sparse(s),  # type: ignore
            )
            for d, s in zip(output['dense_vecs'], output['lexical_weights'])
        ]
        
    def _convert_sparse(self, sparse: dict) -> SparseVector:
        sparse_dict = dict(sparse)
        return SparseVector(
            indices=[int(k) for k in sparse_dict.keys()],
            values=[float(v) for v in sparse_dict.values()],
        )