class AgenticRAGError(Exception):
    pass

class LLMRateLimitError(AgenticRAGError):
    pass


class LLMParseError(AgenticRAGError):
    pass


class LLMClientError(AgenticRAGError):
    pass

class PlannerError(AgenticRAGError):
    pass


class EvaluatorError(AgenticRAGError):
    pass


class OrchestratorError(AgenticRAGError):
    pass