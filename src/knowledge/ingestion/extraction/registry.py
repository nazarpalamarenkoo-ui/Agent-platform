from typing import Dict, Type

class ExtractorRegistry:
    
    _registry: Dict[str, Type['BaseExtractor']] = {}
    
    @classmethod
    def register(cls, name: str):
        def decorator(extractor_cls: Type['BaseExtractor']):
            if name in cls._registry:
                raise ValueError(f"Extractor with this'{name}' already registered")
            cls._registry[name] = extractor_cls
            return extractor_cls
        return decorator
    
    @classmethod
    def get(cls, name: str) -> Type["BaseExtractor"]:
        if name not in cls._registry:
            raise ValueError(f"Extractor '{name}' not available. Available: {list(cls._registry)}")
        return cls._registry[name]
    
    @classmethod

    def create(cls, name: str, **kwargs) -> "BaseExtractor":
        extractor_cls = cls.get(name)
        return extractor_cls(**kwargs)

    @classmethod
    def available(cls) -> list[str]:
        return list(cls._registry.keys())