from app.fixtures.corpus import fixture_filings
from app.ingest.parser import html_to_blocks, parse_filing_html, split_items


def test_keeps_the_item_body_not_the_table_of_contents():
    html = """
    <p>TABLE OF CONTENTS</p>
    <p>Item 1. Business</p><p>Item 1A. Risk Factors</p>
    <p>PART I</p>
    <p>Item 1. Business</p><p>We make robots for car plants and warehouses.</p>
    <p>Item 1A. Risk Factors</p><p>Chip shortages could delay our shipments.</p>
    """
    sections = parse_filing_html(html, "X-1")
    assert [s.item for s in sections] == ["1", "1A"]
    assert sections[0].text == "We make robots for car plants and warehouses."
    assert sections[0].id == "X-1:1"


def test_skips_hidden_blocks_scripts_and_styles():
    html = """<html><head><style>p{}</style></head><body>
    <div style="display: none"><p>Item 1. Hidden</p><p>secret xbrl</p></div>
    <script>var x = 1;</script><p>Item 1. Business</p><p>Visible text.</p></body></html>"""
    text = " ".join(b.text for b in html_to_blocks(html))
    assert "secret" not in text and "var x" not in text
    assert "Visible text." in text


def test_tables_become_pipe_rows_with_dollar_cells_merged():
    html = """<table>
      <tr><td>(in millions)</td><td></td><td>2024</td></tr>
      <tr><td>Revenue</td><td>$</td><td>1,486.2</td></tr>
      <tr><td>Net loss</td><td>$</td><td>(45.2</td><td>)</td></tr>
    </table>"""
    blocks = html_to_blocks(html)
    assert len(blocks) == 1 and blocks[0].kind == "table"
    assert blocks[0].text.splitlines() == [
        "| (in millions) | 2024 |",
        "| Revenue | 1,486.2 |",
        "| Net loss | (45.2) |",
    ]


def test_single_column_layout_tables_are_read_as_paragraphs():
    html = "<table><tr><td>Item 7. MD&amp;A</td></tr><tr><td>Revenue grew.</td></tr></table>"
    items = split_items(html_to_blocks(html))
    assert items[0][0] == "7"
    assert items[0][2][0].text == "Revenue grew."


def test_item_headings_accept_dashes_and_lower_case():
    html = "<p>ITEM 7A — Quantitative Disclosures</p><p>Rates.</p><p>item 8: Financials</p><p>T.</p>"
    sections = parse_filing_html(html, "F")
    assert [(s.item, s.title) for s in sections] == [
        ("7A", "Quantitative Disclosures"),
        ("8", "Financials"),
    ]


def test_every_fixture_filing_parses_into_the_expected_items():
    for filing, html in fixture_filings():
        items = [s.item for s in parse_filing_html(html, filing.id)]
        assert items == ["1", "1A", "2", "3", "7", "8"], filing.id


def test_fixture_financial_table_survives_parsing():
    filing, html = next((f, h) for f, h in fixture_filings() if f.id == "BFHC-2023-10K")
    item8 = next(s for s in parse_filing_html(html, filing.id) if s.item == "8")
    assert "| Net income (loss) | (45.2) | (88.7) |" in item8.text
