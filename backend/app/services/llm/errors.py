class LLMError(Exception):
    code = "llm_error"


class LLMNotConfiguredError(LLMError):
    code = "llm_not_configured"


class LLMUnavailableError(LLMError):
    code = "llm_unavailable"


class LLMOutputInvalidError(LLMError):
    code = "llm_output_invalid"
