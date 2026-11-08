from __future__ import annotations

from app.graph.extract import RELATIONS
from app.rag.prompts import DATA_RULE

EXTRACT_SYSTEM = f"""TASK: extract_graph
Extract facts about the filing company from the passage of its 10-K.
Allowed relations: {", ".join(RELATIONS)}.
Use "COMPANY" as the source for facts about the filing company itself.
Reply with JSON only:
{{"triples": [{{"source": "COMPANY", "relation": "OWNS", "target": "Acme GmbH",
  "target_kind": "organization", "detail": ""}}]}}
Kinds are "person" or "organization". Return {{"triples": []}} when there are none.
{DATA_RULE}"""


def extract_messages(company: str, text: str) -> list[dict[str, str]]:
    user = f"<company>{company}</company>\n<passage>\n{text}\n</passage>"
    return [{"role": "system", "content": EXTRACT_SYSTEM}, {"role": "user", "content": user}]
