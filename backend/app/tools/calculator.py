import numexpr
from langchain_core.tools import tool


@tool
def calculator(expression: str) -> str:
    """Evaluate an arithmetic expression, e.g. "482 * 37 - 19**2 / 4".

    Supports +, -, *, /, **, parentheses, and common math functions
    (sin, cos, sqrt, exp, log, abs). Does not support variables or assignment.
    """
    try:
        # Explicit empty dicts: numexpr.evaluate otherwise resolves unknown
        # names against the *caller's* local/global frame (verified locally --
        # it genuinely does this), which would leak this process's Python
        # variables into a user-controlled expression. Forcing empty
        # namespaces means any bare name raises instead of resolving.
        result = numexpr.evaluate(expression, local_dict={}, global_dict={}).item()
    except Exception as exc:  # noqa: BLE001 - surface any parse/eval error to the model
        return f"Could not evaluate '{expression}': {exc}"
    return str(result)
