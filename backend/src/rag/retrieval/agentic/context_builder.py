from src.rag.retrieval.agentic.models import RetrievalEvidence


class ContextBuilder:

    def __init__(self, max_chunks: int = 10, max_chars: int = 20_000):
        self.max_chunks = max_chunks
        self.max_chars = max_chars

    def _deduplicate(self, evidence: list[RetrievalEvidence]) -> list[RetrievalEvidence]:
        seen: dict[str, RetrievalEvidence] = {}

        for ev in evidence:
            if ev.chunk_id not in seen:
                seen[ev.chunk_id] = ev
            else:
                if ev.score > seen[ev.chunk_id].score:
                    seen[ev.chunk_id] = ev

        return list(seen.values())

    def _sort_by_score(self, evidence: list[RetrievalEvidence]) -> list[RetrievalEvidence]:
        return sorted(evidence, key=lambda e: e.score, reverse=True)

    def _truncate(self, evidence: list[RetrievalEvidence]) -> list[RetrievalEvidence]:
        result = []
        total_chars = 0

        for ev in evidence:
            if len(result) >= self.max_chunks:
                break
            if total_chars + len(ev.text) > self.max_chars:
                break
            result.append(ev)
            total_chars += len(ev.text)

        return result

    def _format(self, evidence: list[RetrievalEvidence]) -> str:
        if not evidence:
            return ""

        blocks = []

        for i, ev in enumerate(evidence, start=1):
            line = f"[Source {i}] (score: {ev.score:.2f})\n{ev.text}\n"
            blocks.append(line)

        return "\n\n".join(blocks)
    
    def build_evidence_list(self, evidence: list[RetrievalEvidence]) -> list[RetrievalEvidence]:
        deduplicated = self._deduplicate(evidence)
        sorted_evidence = self._sort_by_score(deduplicated)
        return self._truncate(sorted_evidence)

    def build(self, evidence: list[RetrievalEvidence]) -> str:
        truncated = self.build_evidence_list(evidence)
        return self._format(truncated)