import math

def recall_at_k(relevant: set[str], retrieved: list[str], k: int) -> float:
        
    hits = len(set(retrieved[:k]).intersection(relevant))
        
    return hits / len(relevant)
    
def mrr(relevant: set[str], retrieved: list[str]) -> float:
    
    for rank, chunk_id in enumerate(retrieved, start=1):
        if chunk_id in relevant:
            return 1.0 / rank
    return 0.0
    
def ndcg_at_k(relevant: set[str], retrieved: list[str], k: int) -> float:
        
    gains = [1 if chunk_id in relevant else 0 for chunk_id in retrieved[:k]]
        
    dcg = sum(gain / math.log2(idx + 2) for idx, gain in enumerate(gains))
        
    ideal_gains = sorted(gains, reverse=True)
    idcg = sum(gain / math.log2(idx + 2) for idx, gain in enumerate(ideal_gains))
        
    if idcg == 0:
        return 0.0
        
    return dcg / idcg