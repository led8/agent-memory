"""Unit tests for sentence-transformers embeddings."""

from neo4j_agent_memory.embeddings.sentence_transformers import SentenceTransformerEmbedder


def test_default_model_uses_bge_small() -> None:
    """Direct embedder construction should use the repo default local model."""
    embedder = SentenceTransformerEmbedder()

    assert embedder._model_name == "BAAI/bge-small-en-v1.5"
    assert embedder.dimensions == 384
