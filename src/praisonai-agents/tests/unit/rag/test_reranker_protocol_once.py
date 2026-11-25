"""X-06: rag has one RerankerProtocol.

rag/retriever.py defined a copy identical to rag/protocols.py's (same `name`
attribute and `rerank` signature). It now imports that one, so the old import
path still works and both names are the same class.
"""


def test_rag_reranker_protocol_is_defined_once():
    from praisonaiagents.rag.protocols import RerankerProtocol as from_protocols
    from praisonaiagents.rag.retriever import RerankerProtocol as from_retriever

    assert from_retriever is from_protocols


def test_simple_reranker_still_satisfies_it():
    from praisonaiagents.rag.retriever import RerankerProtocol, SimpleReranker

    assert isinstance(SimpleReranker(), RerankerProtocol)
