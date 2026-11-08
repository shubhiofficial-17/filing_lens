from app.graph.extract import (
    RuleExtractor,
    entity_alias,
    entity_key,
    parse_triples,
    split_names,
)
from app.models import Chunk
from app.rag.pipelines import GraphRag, HybridRag
from tests.helpers import fixture_store, rag


def _chunk(text: str) -> Chunk:
    return Chunk("F:1#0", "F:1", "F", "ABC", 2025, "1", text, company="Abc Holdings, Inc.")


def test_names_are_normalised_but_subsidiaries_stay_distinct():
    assert entity_key("Bluefin Health Corp.") == "bluefin health"
    assert entity_key("Solace Energy Holdings, Inc.") == "solace energy"
    assert entity_key("Northwind Robotics GmbH") == "northwind robotics gmbh"
    assert entity_alias("Helix Vision Ltd.") == "helix vision"


def test_name_lists_keep_commas_inside_names():
    assert split_names("Bluefin Pharmacy LLC and CareLoop Analytics, Inc.") == [
        "Bluefin Pharmacy LLC", "CareLoop Analytics, Inc."]
    assert split_names("A Co, B GmbH and C Ltd.") == ["A Co.", "B GmbH", "C Ltd."]


def test_rule_extractor_reads_officers_subsidiaries_deals_and_customers():
    text = (
        "Jane Roe serves as our Chief Executive Officer and John Poe serves as our Chief "
        "Financial Officer. Our principal subsidiaries are Abc GmbH and Xyz Labs LLC. "
        "We acquired Xyz Labs LLC, a testing company, in May 2025 for $12.5 million in cash. "
        "Big Retail Co accounted for approximately 30% of our revenue in fiscal 2025."
    )
    got = RuleExtractor().extract("Abc Holdings, Inc.", [_chunk(text)])
    triples = {(r.source_id, r.relation, r.target_id, r.detail) for r in got.relations}
    assert triples == {
        ("abc", "CEO", "jane roe", ""),
        ("abc", "CFO", "john poe", ""),
        ("abc", "OWNS", "abc gmbh", ""),
        ("abc", "OWNS", "xyz labs llc", ""),
        ("abc", "ACQUIRED", "xyz labs llc", "May 2025, $12.5 million"),
        ("abc", "CUSTOMER", "big retail", "30% of revenue"),
    }
    assert all(r.chunk_id == "F:1#0" and r.fiscal_year == 2025 for r in got.relations)
    kinds = {e.id: e.kind for e in got.entities}
    assert kinds["abc"] == "company" and kinds["jane roe"] == "person"


def test_llm_triples_are_validated():
    reply = '{"triples": [{"source": "COMPANY", "relation": "OWNS", "target": "X"},' \
            ' {"source": "COMPANY", "relation": "LIKES", "target": "Y"}, 7]}'
    assert [t["target"] for t in parse_triples(reply)] == ["X"]
    assert parse_triples("not json") == []


def test_fixture_graph_has_provenance_for_every_relation():
    store = fixture_store()
    chunk_ids = {c.id for c in store._chunks.values()}
    relations = store.relations_for([e.id for e in store.list_entities()])
    assert len(relations) == store.count_relations() > 50
    assert all(r.chunk_id in chunk_ids for r in relations)


def test_graph_bridges_from_a_subsidiary_to_its_parents_ceo():
    result = rag().graph.expand(
        "Which company owns Helix Vision Ltd., and who was that company's CEO in fiscal 2025?"
    )
    assert [e.name for e in result.mentioned] == ["Helix Vision Ltd."]
    assert result.bridge_tickers == ["NWRB"]
    texts = [f.text() for f in result.facts]
    assert texts[0].startswith("Northwind Robotics, Inc. owns Helix Vision Ltd.")
    assert any("Maya Chen is the Chief Executive Officer" in t for t in texts)


def test_graph_ignores_a_company_named_without_a_relation_question():
    assert rag().graph.expand("What was Northwind Robotics' revenue in fiscal 2024?").facts == []


def test_graph_strategy_answers_a_two_hop_question_hybrid_misses():
    q = "Which company owns Helix Vision Ltd., and who was that company's CEO in fiscal 2025?"
    assert "Maya Chen" not in HybridRag(rag()).run(q).text
    answer = GraphRag(rag()).run(q)
    assert "Northwind" in answer.text and "Maya Chen" in answer.text
    assert "graph lookup" in [s.name for s in answer.trace]
    assert answer.retrieved[0].source == "graph"
