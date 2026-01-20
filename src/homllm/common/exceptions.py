"""Exception hierarchy for HOM-LLM."""


class HOMLLMError(Exception):
    """Base exception for all HOM-LLM errors."""

    pass


class IndexerError(HOMLLMError):
    """Indexer layer errors."""

    pass


class RetrievalError(HOMLLMError):
    """Retrieval layer errors."""

    pass


class RankingError(HOMLLMError):
    """Ranking layer errors."""

    pass


class ContextError(HOMLLMError):
    """Context assembly errors."""

    pass


class GenerationError(HOMLLMError):
    """Generation layer errors."""

    pass
