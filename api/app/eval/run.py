"""Run the labelled question set through one or more strategies and report the scores.

    python -m app.eval.run                         # every strategy, demo model, fixtures
    python -m app.eval.run --strategies naive,hybrid --markdown ../docs/evaluation.md
    python -m app.eval.run --check                 # fail if below app/eval/thresholds.json

With FILINGLENS_LLM_BASE_URL set, the configured model (usually the LLM Gateway) is used
instead of the demo model, and the report says so.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from dataclasses import asdict
from pathlib import Path

from app.eval.dataset import EvalQuestion, questions
from app.eval.metrics import Score, score
from app.rag.pipelines import Pipeline, RagContext

HERE = Path(__file__).parent
REPORT_PATH = HERE / "report.json"
THRESHOLDS_PATH = HERE / "thresholds.json"


def eval_context() -> RagContext:
    """Fixtures in an in-memory store, with the configured (or demo) model and embedder."""
    from app.config import get_settings
    from app.container import build_llm, build_rag
    from app.store.memory import InMemoryStore

    # The MCP agent calls its tools in-process here ("direct"): same functions, no
    # subprocess, so the run stays fast and deterministic. tests/test_mcp_client.py covers
    # the real stdio transport. Set FILINGLENS_EVAL_MCP_TRANSPORT=stdio to evaluate it.
    transport = os.environ.get("FILINGLENS_EVAL_MCP_TRANSPORT", "direct")
    settings = get_settings().model_copy(
        update={"database_url": None, "seed_fixtures": True, "mcp_transport": transport}
    )
    return build_rag(settings, InMemoryStore(), build_llm(settings))


def evaluate(pipeline: Pipeline, qs: list[EvalQuestion]) -> list[Score]:
    out = []
    for q in qs:
        out.append(score(q, pipeline.run(q.question)))
    return out


def _mean(values: list[float | None]) -> float | None:
    vals = [v for v in values if v is not None]
    return round(statistics.fmean(vals), 4) if vals else None


def aggregate(scores: list[Score]) -> dict:
    latencies = sorted(s.latency_ms for s in scores)
    injection = [s for s in scores if s.category == "injection"]
    return {
        "questions": len(scores),
        "accuracy": _mean([1.0 if s.correct else 0.0 for s in scores]),
        "keyword_recall": _mean([s.keyword_recall for s in scores]),
        "retrieval_recall": _mean([s.retrieval_recall for s in scores]),
        "mrr": _mean([s.mrr for s in scores]),
        "citation_precision": _mean([s.citation_precision for s in scores]),
        "faithfulness": _mean([s.faithfulness for s in scores]),
        "injection_safe": _mean([1.0 if s.injection_safe else 0.0 for s in injection]),
        "llm_calls": _mean([float(s.llm_calls) for s in scores]),
        "tokens": _mean([float(s.tokens) for s in scores]),
        "cost_usd": _mean([s.cost_usd for s in scores]),
        "latency_p50_ms": round(latencies[len(latencies) // 2], 1) if latencies else None,
        "latency_p95_ms": (
            round(latencies[max(0, int(len(latencies) * 0.95) - 1)], 1) if latencies else None
        ),
    }


def by_category(scores: list[Score]) -> dict[str, dict]:
    cats: dict[str, list[Score]] = {}
    for s in scores:
        cats.setdefault(s.category, []).append(s)
    return {
        cat: {
            "questions": len(items),
            "accuracy": _mean([1.0 if s.correct else 0.0 for s in items]),
            "retrieval_recall": _mean([s.retrieval_recall for s in items]),
        }
        for cat, items in sorted(cats.items())
    }


def run(strategies: list[str], limit: int | None = None) -> dict:
    from app.rag.strategies import PIPELINES

    ctx = eval_context()
    qs = questions()[:limit] if limit else questions()
    report: dict = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "model": ctx.llm.name,
        "embedder": ctx.embedder.name,
        "mcp_transport": ctx.mcp_transport,
        "demo_mode": ctx.llm.name.startswith("demo"),
        "questions": len(qs),
        "strategies": {},
    }
    for name in strategies:
        pipeline = PIPELINES[name](ctx)
        scores = evaluate(pipeline, qs)
        report["strategies"][name] = {
            "title": pipeline.title,
            "description": pipeline.description,
            "overall": aggregate(scores),
            "by_category": by_category(scores),
            "misses": [
                {"id": s.question_id, "missing": s.missing, "answer": s.answer[:300]}
                for s in scores if not s.correct
            ],
            "scores": [asdict(s) for s in scores],
        }
    return report


METRICS = [
    ("accuracy", "Accuracy"),
    ("retrieval_recall", "Retrieval recall"),
    ("mrr", "MRR"),
    ("citation_precision", "Citation precision"),
    ("faithfulness", "Faithfulness"),
    ("injection_safe", "Injection-safe"),
    ("llm_calls", "LLM calls"),
    ("tokens", "Tokens"),
    ("latency_p50_ms", "p50 ms"),
]


def markdown(report: dict) -> str:
    def fmt(key: str, v: float | None) -> str:
        if v is None:
            return "–"
        if key in ("llm_calls",):
            return f"{v:.1f}"
        if key in ("tokens", "latency_p50_ms"):
            return f"{v:,.0f}"
        return f"{v * 100:.1f}%"

    mode = "demo model (deterministic, not an AI)" if report["demo_mode"] else report["model"]
    lines = [
        "# Evaluation results",
        "",
        f"{report['questions']} labelled questions over the fixture corpus · model: {mode} · "
        f"embedder: {report['embedder']} · generated {report['generated_at']}",
        "",
        "| Strategy | " + " | ".join(label for _, label in METRICS) + " |",
        "|---|" + "---:|" * len(METRICS),
    ]
    for name, data in report["strategies"].items():
        o = data["overall"]
        lines.append(f"| {data['title']} | " + " | ".join(fmt(k, o[k]) for k, _ in METRICS) + " |")

    cats = sorted({c for d in report["strategies"].values() for c in d["by_category"]})
    lines += ["", "## Accuracy by question type", "",
              "| Strategy | " + " | ".join(cats) + " |", "|---|" + "---:|" * len(cats)]
    for data in report["strategies"].values():
        row = [fmt("accuracy", data["by_category"].get(c, {}).get("accuracy")) for c in cats]
        lines.append(f"| {data['title']} | " + " | ".join(row) + " |")
    return "\n".join(lines) + "\n"


def check(report: dict, thresholds: dict) -> list[str]:
    failures = []
    for name, limits in thresholds.items():
        overall = report["strategies"].get(name, {}).get("overall")
        if overall is None:
            continue
        for metric, minimum in limits.items():
            value = overall.get(metric)
            if value is None or value < minimum:
                failures.append(f"{name}.{metric} = {value} (minimum {minimum})")
    return failures


def main(argv: list[str] | None = None) -> int:
    from app.rag.strategies import PIPELINES

    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--strategies", default=",".join(PIPELINES))
    parser.add_argument("--limit", type=int)
    parser.add_argument("--out", default=str(REPORT_PATH))
    parser.add_argument("--markdown")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)

    report = run([s.strip() for s in args.strategies.split(",") if s.strip()], args.limit)
    Path(args.out).write_text(json.dumps(report, indent=1) + "\n")
    table = markdown(report)
    if args.markdown:
        Path(args.markdown).write_text(table)
    print(table)

    if args.check:
        failures = check(report, json.loads(THRESHOLDS_PATH.read_text()))
        for f in failures:
            print(f"BELOW THRESHOLD: {f}", file=sys.stderr)
        return 1 if failures else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
