import math

from app.rag.embeddings import HashingEmbedder, cosine


def test_vectors_are_unit_length_and_deterministic():
    e = HashingEmbedder(64)
    a, b = e.embed(["Revenue grew in fiscal 2024", "Revenue grew in fiscal 2024"])
    assert len(a) == 64
    assert math.isclose(sum(v * v for v in a), 1.0, rel_tol=1e-9)
    assert a == b


def test_related_text_is_closer_than_unrelated_text():
    e = HashingEmbedder()
    q, near, far = e.embed([
        "research and development expense",
        "Research and development expense was $214.6 million.",
        "Our headquarters are located in Phoenix, Arizona.",
    ])
    assert cosine(q, near) > cosine(q, far)


def test_empty_text_gives_a_zero_vector():
    assert set(HashingEmbedder(8).embed([""])[0]) == {0.0}
