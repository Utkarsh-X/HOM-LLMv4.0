from homllm.generation.providers.gemini import GeminiProvider


def test_retryable_exception_includes_dns_resolution_failures():
    assert GeminiProvider._is_retryable_exception(Exception("[Errno 11001] getaddrinfo failed")) is True
    assert GeminiProvider._is_retryable_exception(Exception("Temporary failure in name resolution")) is True


def test_retryable_exception_keeps_non_transient_errors_false():
    assert GeminiProvider._is_retryable_exception(Exception("invalid api key")) is False
