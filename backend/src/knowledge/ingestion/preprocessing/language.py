from lingua import Language, LanguageDetectorBuilder

class LanguageDetect:
    
    def __init__(self, confidence: float = 0.7):
        self.confidence = confidence
        self._detector = LanguageDetectorBuilder.from_all_languages().build()
        
    def detect(self, text: str) -> str:
        
        if not text or not text.strip():
            return 'unknown'
        
        result = self._detector.compute_language_confidence_values(text)
        
        if not result:
            return 'unknown'
        
        best = result[0]
        
        if best.value < self.confidence:
            return "unknown"
        
        return best.language.iso_code_639_1.name.lower()