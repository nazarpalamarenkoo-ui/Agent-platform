from typing import Dict, Type

class LoaderRegistry:
    
    _registry: Dict[str, Type['BaseLoader']] = {}
    
    @classmethod
    def register(cls, name: str):
        def decorator(loader_cls: Type['BaseLoader']):
            if name in cls._registry:
                raise ValueError(f"Loader with this'{name}' already registered")
            cls._registry[name] = loader_cls
            return loader_cls
        return decorator
    
    @classmethod
    def get(cls, name: str) -> Type["BaseLoader"]:
        if name not in cls._registry:
            raise ValueError(f"Loader '{name}' not available. Available: {list(cls._registry)}")
        return cls._registry[name]
    
    @classmethod

    def create(cls, name: str, **kwargs) -> "BaseLoader":
        loader_cls = cls.get(name)
        return loader_cls(**kwargs)

    @classmethod
    def available(cls) -> list[str]:
        return list(cls._registry.keys())