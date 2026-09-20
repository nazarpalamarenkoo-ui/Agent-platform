from enum import Enum

class DocumentType(str, Enum):
    BOOK = "book"
    ARCHITECTURE_DOC = "architecture_doc"
    PAPER = "paper"
    MANUAL = "manual"
    BLOG_POST = "blog_post"