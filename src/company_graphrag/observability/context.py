"""Request correlation context shared across API, retrieval, and agents."""

from contextvars import ContextVar, Token

request_id_var: ContextVar[str] = ContextVar("request_id", default="")
run_id_var: ContextVar[str] = ContextVar("run_id", default="")
trace_id_var: ContextVar[str] = ContextVar("trace_id", default="")


def bind_context(*, request_id: str, run_id: str, trace_id: str) -> list[tuple[ContextVar[str], Token[str]]]:
    """Bind identifiers and return tokens that can restore the prior context."""
    return [
        (request_id_var, request_id_var.set(request_id)),
        (run_id_var, run_id_var.set(run_id)),
        (trace_id_var, trace_id_var.set(trace_id)),
    ]


def reset_context(tokens: list[tuple[ContextVar[str], Token[str]]]) -> None:
    """Restore identifiers after a request."""
    for variable, token in reversed(tokens):
        variable.reset(token)


def current_request_id() -> str:
    return request_id_var.get()


def current_run_id() -> str:
    return run_id_var.get()


def current_trace_id() -> str:
    return trace_id_var.get()
