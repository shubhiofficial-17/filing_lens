"""Registry of answering strategies, in the order they are compared."""

from __future__ import annotations

from app.agents.agentic import AgenticRag
from app.agents.multi_agent import MultiAgentRag
from app.agents.patterns import RoutedRag
from app.mcp.agent import McpAgentRag
from app.rag.pipelines import GraphRag, HybridRag, NaiveRag, Pipeline

PIPELINES: dict[str, type[Pipeline]] = {
    NaiveRag.name: NaiveRag,
    HybridRag.name: HybridRag,
    GraphRag.name: GraphRag,
    AgenticRag.name: AgenticRag,
    RoutedRag.name: RoutedRag,
    MultiAgentRag.name: MultiAgentRag,
    McpAgentRag.name: McpAgentRag,
}
