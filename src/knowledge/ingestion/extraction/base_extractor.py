from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from src.knowledge.documents_schema.raw_document import RawDocument
from src.knowledge.documents_schema.text_span import TextSpan

@dataclass
class ExtractedDocument:
    text: str
    metadata: dict
    spans: list[TextSpan] = field(default_factory=list)
    
class BaseExtractor(ABC):
    
    @abstractmethod
    def extract(self, document: RawDocument) -> ExtractedDocument:
        pass