# Calculator

`backend/app/tools/calculator.py`

Arithmetic evaluation via `numexpr.evaluate()` -- never raw `eval()`.

```python
@tool
def calculator(expression: str) -> str:
    """Evaluate an arithmetic expression, e.g. "482 * 37 - 19**2 / 4"."""
```

No cache, no breaker, no retry -- it's a pure function with no external
dependency and no meaningful failure mode to retry.

!!! danger "Real security bug caught and fixed during development"
    `numexpr.evaluate()` does **not** sandbox name resolution the way you'd
    expect from a "safe eval" library: by default, it resolves unknown
    identifiers in the expression against the **caller's own Python
    frame** -- local and global variables included.

    Confirmed live:

    ```python
    import numexpr
    secret_var = 42
    numexpr.evaluate("secret_var + 1").item()  # -> 43, leaking secret_var!
    ```

    This means a naive `numexpr.evaluate(expression)` call would let
    user-controlled expression text read arbitrary variables from the
    calling Python process -- not code execution, but a real information
    disclosure vector (imagine any sensitive variable happening to share a
    name with something in the expression).

    Fixed with explicit empty namespaces, which forces any bare name to
    raise instead of resolving:

    ```python
    numexpr.evaluate(expression, local_dict={}, global_dict={})
    ```

    Verified the fix actually closes the hole (`secret_var + 1` now raises
    `'secret_var'` instead of returning `43`) while normal expressions still
    work correctly.
