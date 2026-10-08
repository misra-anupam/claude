# Charts & Diagrams

`backend/app/tools/chart_tools.py`

Two tools, two different delivery mechanisms, chosen to match what each
actually produces.

## `generate_chart`

```python
@tool
def generate_chart(
    chart_type: str,  # bar | line | pie | scatter
    title: str, labels: list[str], values: list[float],
    x_label: str = "", y_label: str = "",
) -> str:
```

Renders via `matplotlib` with the `Agg` backend (headless, no display
server needed) to an in-memory PNG, then stored via the
[artifact pattern](index.md#artifacts-how-binary-output-reaches-the-browser).
`scatter` and `pie` charts with string labels were confirmed to render
correctly (matplotlib treats string x-values as categorical positions,
verified rather than assumed).

## `generate_diagram`

```python
@tool
def generate_diagram(mermaid_code: str, description: str = "") -> str:
```

Just returns `{"text": description, "mermaid": mermaid_code}` directly --
no artifact storage needed, since Mermaid source is small text. The
frontend detects the `mermaid` key and renders the diagram **client-side**
via a locally-bundled `mermaid.js` (no CDN dependency, consistent with the
rest of the project). See [Frontend](../frontend.md#mermaid-diagrams).

## Verified behavior

A single real turn asked for both a bar chart (`Quarterly Revenue`, Q1-Q4)
and a login-flow flowchart in one message -- the model called both tools in
parallel (two simultaneous `tool_call` events). The chart artifact was
fetched back from `GET /api/artifacts/{id}` and confirmed to be a real,
correctly-rendered 720x480 PNG with the exact requested data (visually
inspected, not just checked for valid PNG bytes).
