from app.models import Filing, Section
from app.rag.chunking import chunk_section, index_text

FILING = Filing(id="F", ticker="ABC", company="Abc Inc.", cik="1", fiscal_year=2024)


def _section(text: str) -> Section:
    return Section(id="F:7", filing_id="F", item="7", title="MD&A", text=text)


def test_short_paragraphs_are_grouped():
    chunks = chunk_section(_section("One two three.\n\nFour five six."), FILING)
    assert [c.text for c in chunks] == ["One two three.\n\nFour five six."]
    assert chunks[0].id == "F:7#0" and chunks[0].kind == "text"


def test_tables_are_kept_whole_and_separate():
    table = "| (in millions) | 2024 |\n| Revenue | 10.0 |\n| Net income | 1.0 |"
    chunks = chunk_section(_section(f"Intro text.\n\n{table}\n\nAfter text."), FILING)
    assert [c.kind for c in chunks] == ["text", "table", "text"]
    assert chunks[1].text == table


def test_groups_never_exceed_the_word_limit():
    paras = "\n\n".join(" ".join(["word"] * 30) + "." for _ in range(5))
    chunks = chunk_section(_section(paras), FILING, max_words=70)
    assert all(len(c.text.split()) <= 70 for c in chunks)
    assert len(chunks) == 3


def test_a_long_paragraph_is_split_on_sentences():
    para = " ".join(f"Sentence number {i} is here." for i in range(40))
    chunks = chunk_section(_section(para), FILING, max_words=50)
    assert len(chunks) > 1
    assert all(c.text.endswith(".") for c in chunks)


def test_a_subheading_stays_with_the_paragraph_it_introduces():
    body = " ".join(["word"] * 60) + "."
    text = f"{body}\n\nExecutive Officers\n\nJane Doe serves as our Chief Executive Officer."
    chunks = chunk_section(_section(text), FILING, max_words=80)
    assert chunks[-1].text.startswith("Executive Officers")


def test_index_text_carries_company_year_and_item():
    chunk = chunk_section(_section("Revenue grew."), FILING)[0]
    assert index_text(chunk, "Abc Inc.", "MD&A").startswith(
        "Abc Inc. (ABC) 10-K fiscal 2024, Item 7 MD&A\n"
    )
