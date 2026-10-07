class JudgeError(Exception):
    pass

class JudgeClientError(JudgeError):
    pass

class JudgeParseError(JudgeError):
    pass

class JudgeValidationError(JudgeError):
    pass