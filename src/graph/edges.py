"""Graph edges — conditional routing for the analysis graph."""
from __future__ import annotations

from src.graph.state import AnalystState

MAX_RETRIES = 2


def after_plan(state: AnalystState) -> str:
    if state.get("error"):
        return "handle_error"
    return "execute_query"


def after_execute(state: AnalystState) -> str:
    if state.get("error"):
        return "handle_error"
    return "reflect"


def after_reflect(state: AnalystState) -> str:
    if state.get("error"):
        return "handle_error"
    reflection_ok = state.get("reflection_ok", True)
    retry_count = state.get("retry_count", 0)
    if not reflection_ok and retry_count < MAX_RETRIES:
        return "retry_plan"
    return "synthesize"


def after_synthesize(state: AnalystState) -> str:
    if state.get("error"):
        return "handle_error"
    return "finalize"
