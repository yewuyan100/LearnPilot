class LLMError(Exception):
    code = "llm_error"


class LLMNotConfiguredError(LLMError):
    code = "llm_not_configured"


class LLMUnavailableError(LLMError):
    code = "llm_unavailable"


class LLMAuthenticationError(LLMError):
    code = "llm_authentication_failed"


class LLMConfigurationError(LLMError):
    code = "llm_configuration_invalid"


class LLMOutputInvalidError(LLMError):
    code = "llm_output_invalid"

    def __init__(
        self,
        message: str,
        *,
        reason: str = "structured_output_invalid",
    ):
        super().__init__(message)
        self.reason = reason


class LLMOutputTruncatedError(LLMOutputInvalidError):
    code = "llm_output_truncated"


class LLMEmptyContentError(LLMOutputInvalidError):
    code = "llm_empty_content"
