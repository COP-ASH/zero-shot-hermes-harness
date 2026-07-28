"""Graph assembly — AnalystState graph compiled once at import."""
from __future__ import annotations

from langgraph.graph import END, StateGraph

from src.graph.edges import after_execute, after_plan, after_reflect, after_synthesize
from src.graph.nodes import (
    execute_query,
    finalize,
    handle_error,
    plan_query,
    reflect,
    synthesize,
)
from src.graph.state import AnalystState


def _increment_retry(state: AnalystState) -> AnalystState:
    """Increment retry_count before re-running plan_query."""
    return {"retry_count": state.get("retry_count", 0) + 1}


def _build_graph():
    g = StateGraph(AnalystState)

    # Nodes
    g.add_node("plan_query", plan_query)
    g.add_node("execute_query", execute_query)
    g.add_node("reflect", reflect)
    g.add_node("synthesize", synthesize)
    g.add_node("handle_error", handle_error)
    g.add_node("finalize", finalize)
    g.add_node("increment_retry", _increment_retry)

    # Entry
    g.set_entry_point("plan_query")

    # Edges
    g.add_conditional_edges(
        "plan_query",
        after_plan,
        {"execute_query": "execute_query", "handle_error": "handle_error"},
    )
    g.add_conditional_edges(
        "execute_query",
        after_execute,
        {"reflect": "reflect", "handle_error": "handle_error"},
    )
    g.add_conditional_edges(
        "reflect",
        after_reflect,
        {
            "retry_plan": "increment_retry",
            "synthesize": "synthesize",
            "handle_error": "handle_error",
        },
    )
    # After incrementing retry count, go back to plan_query with corrected SQL
    g.add_edge("increment_retry", "plan_query")

    g.add_conditional_edges(
        "synthesize",
        after_synthesize,
        {"finalize": "finalize", "handle_error": "handle_error"},
    )
    g.add_edge("finalize", END)
    g.add_edge("handle_error", END)

    return g.compile()


agentic_ai = _build_graph()
