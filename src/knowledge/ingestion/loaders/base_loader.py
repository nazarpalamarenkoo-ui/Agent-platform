from abc import ABC, abstractmethod
from src.knowledge.documents_schema.raw_document import RawDocument

class BaseLoader(ABC):
    
    @abstractmethod
    def load_document(self, source: str) -> RawDocument:
        pass