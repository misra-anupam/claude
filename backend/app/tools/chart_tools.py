import io
import json

import matplotlib

matplotlib.use("Agg")  # headless -- no display server in the container

import matplotlib.pyplot as plt
from cachetools import TTLCache
from langchain_core.tools import tool

from ..artifacts import save_artifact

CHART_TYPES = ("bar", "line", "pie", "scatter")


def build_chart_tools(artifact_store: TTLCache) -> list:
    @tool
    def generate_chart(
        chart_type: str,
        title: str,
        labels: list[str],
        values: list[float],
        x_label: str = "",
        y_label: str = "",
    ) -> str:
        """Generate a chart from labeled numeric data and return a reference
        to the rendered PNG image for inline display. `chart_type` must be
        one of: bar, line, pie, scatter. `labels` and `values` must be the
        same length.
        """
        if chart_type not in CHART_TYPES:
            return f"Unsupported chart_type '{chart_type}'. Use one of: {', '.join(CHART_TYPES)}."
        if len(labels) != len(values):
            return "labels and values must be the same length."

        fig, ax = plt.subplots(figsize=(6, 4))
        try:
            if chart_type == "bar":
                ax.bar(labels, values)
            elif chart_type == "line":
                ax.plot(labels, values, marker="o")
            elif chart_type == "pie":
                ax.pie(values, labels=labels, autopct="%1.1f%%")
            elif chart_type == "scatter":
                ax.scatter(labels, values)
            if chart_type != "pie":
                ax.set_xlabel(x_label)
                ax.set_ylabel(y_label)
            ax.set_title(title)
            fig.tight_layout()
            buf = io.BytesIO()
            fig.savefig(buf, format="png", dpi=120)
        finally:
            plt.close(fig)

        artifact_id = save_artifact(artifact_store, buf.getvalue(), "image/png")
        return json.dumps(
            {
                "text": f"Generated a {chart_type} chart titled '{title}'.",
                "artifact_id": artifact_id,
                "content_type": "image/png",
            }
        )

    @tool
    def generate_diagram(mermaid_code: str, description: str = "") -> str:
        """Generate a flowchart, sequence diagram, or similar using Mermaid
        syntax (e.g. "graph TD; A-->B;") for inline rendering in the chat UI.
        `description` is a short caption shown alongside the diagram.
        """
        return json.dumps(
            {
                "text": description or "Generated a diagram.",
                "mermaid": mermaid_code,
            }
        )

    return [generate_chart, generate_diagram]
