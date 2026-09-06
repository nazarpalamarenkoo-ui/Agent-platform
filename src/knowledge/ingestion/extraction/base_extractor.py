from abc import ABC, abstractmethod
from dataclasses import dataclass

from src.knowledge.documents_schema.raw_document import RawDocument

@dataclass
class ExtractedDocument:
    text: str
    metadata: dict
    
class BaseExtractor(ABC):
    
    @abstractmethod
    def extract(self, document: RawDocument) -> ExtractedDocument:
        pass