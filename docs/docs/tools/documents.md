# Documents (PDF/HTML)

`backend/app/tools/document_tools.py`

```python
@tool
def generate_html(title: str, body_html: str, filename: str = "document.html") -> str: ...

@tool
def generate_pdf(title: str, content: str, filename: str = "document.pdf") -> str: ...
```

## Why `reportlab`, not `weasyprint`

PDF generation needed a library choice. `weasyprint` (HTML&rarr;PDF) is the
more common choice for rich layouts, but pulls in heavy system
dependencies (Pango, Cairo) that complicate the `python:3.12-slim` base
image. `reportlab` is pure Python, installs as a plain wheel, and is more
than sufficient for the actual scope here: simple titled documents with
paragraphs (reports, summaries, notes) -- not arbitrary rich HTML layouts.
Confirmed it installs and renders cleanly with no extra system packages
before committing to it.

```python
doc = SimpleDocTemplate(buf, pagesize=letter)
styles = getSampleStyleSheet()
story = [Paragraph(title, styles["Title"]), Spacer(1, 16)]
for para in content.split("\n\n"):
    story.append(Paragraph(para, styles["Normal"]))
doc.build(story)
```

## Delivery: download link, not inline rendering

Unlike the chart/image tools, PDFs and HTML files use the
[artifact pattern](index.md#artifacts-how-binary-output-reaches-the-browser)
but render as a **download link** in the chat UI rather than inline content
-- the frontend's `tool_result` handler checks `content_type`: image types
get an `<img>`, everything else gets
`<a href="/api/artifacts/{id}" download="{filename}">`.

## Verified behavior

A single real turn generated both a PDF report ("Q1 Highlights", two
paragraphs of realistic-looking sales narrative) and an HTML page
("Welcome") in parallel. Both artifacts were fetched back and inspected
directly:

- The PDF: a real, correctly laid-out 1-page document, confirmed by reading
  its actual rendered content (title, both paragraphs, correct formatting)
  -- not just checking for valid PDF magic bytes.
- The HTML: well-formed, served with the correct `text/html; charset=utf-8`
  content type.
