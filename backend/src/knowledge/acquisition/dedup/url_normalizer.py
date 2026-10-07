import hashlib
from urllib.parse import urlparse, urlunparse

from src.knowledge.documents_schema.discovery_model import DiscoveryResult

def normalize_url(url: str) -> str:
    if not url:
        raise ValueError('URL is empty')
    
    if "://" not in url:
        url = "https://" + url
    
    parsed = urlparse(url)
    domain = parsed.netloc.lower().removeprefix('www.')
    path = parsed.path.rstrip('/')
    
    return urlunparse((
        '', # delete schema
        domain,
        path,
        '', # params
        parsed.query,
        '', # fragment
    ))
    
def calculate_hash(discovery: DiscoveryResult) -> str:
        
    normalized_url = normalize_url(discovery.url)
        
    url_hash = hashlib.sha256(normalized_url.encode()).hexdigest()
        
    return url_hash

def calculate_hash_from_url(url: str) -> str:
    
    normalized_url = normalize_url(url)
    return hashlib.sha256(normalized_url.encode()).hexdigest()