import io
import json
from html import escape as html_escape

from cachetools import TTLCache
from langchain_core.tools import tool
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

from ..artifacts import save_artifact

# Large binary tool output doesn't belong in the SSE token stream or the
# LLM's own context -- same artifact-store pattern as the chart/image tools
# (Phase A/B), just with a download link in the frontend instead of an
# inline <img>, since PDFs/HTML files aren't meant to render in the chat
# transcript itself.


def build_document_tools(artifact_store: TTLCache) -> list:
    @tool
    def generate_html(title: str, body_html: str, filename: str = "document.html") -> str:
        """Generate a downloadable standalone HTML file from a title and
        HTML body content (e.g. "<h1>...</h1><p>...</p>"). Returns a
        reference to the file for download.
        """
        doc = (
            "<!DOCTYPE html>\n<html><head><meta charset=\"utf-8\">"
            f"<title>{html_escape(title)}</title></head>"
            f"<body>{body_html}</body></html>"
        )
        artifact_id = save_artifact(artifact_store, doc.encode("utf-8"), "text/html")
        return json.dumps(
            {
                "text": f"Generated HTML document '{title}'.",
                "artifact_id": artifact_id,
                "content_type": "text/html",
                "filename": filename if filename.endswith(".html") else f"{filename}.html",
            }
        )

    @tool
    def generate_pdf(title: str, content: str, filename: str = "document.pdf") -> str:
        """Generate a downloadable PDF from a title and plain-text content
        (paragraphs separated by blank lines). Returns a reference to the
        file for download. Not for complex layouts -- simple text documents
        only (reports, summaries, notes).
        """
        buf = io.BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=letter)
        styles = getSampleStyleSheet()
        story = [Paragraph(html_escape(title), styles["Title"]), Spacer(1, 16)]
        for para in content.split("\n\n"):
            para = para.strip()
            if para:
                story.append(Paragraph(html_escape(para).replace("\n", "<br/>"), styles["Normal"]))
                story.append(Spacer(1, 10))
        doc.build(story)

        artifact_id = save_artifact(artifact_store, buf.getvalue(), "application/pdf")
        return json.dumps(
            {
                "text": f"Generated PDF '{title}'.",
                "artifact_id": artifact_id,
                "content_type": "application/pdf",
                "filename": filename if filename.endswith(".pdf") else f"{filename}.pdf",
            }
        )

    return [generate_html, generate_pdf]
