from __future__ import annotations

import io
import re
import zipfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import streamlit as st
from pypdf import PdfReader


st.set_page_config(
    page_title="PDF to Markdown",
    page_icon="📖",
    layout="centered",
)

st.markdown(
    """
    <style>
      .block-container { max-width: 880px; padding-top: 3rem; }
      [data-testid="stFileUploader"] { padding: 1rem; border-radius: 14px; }
      .quiet { color: #667085; font-size: .92rem; }
    </style>
    """,
    unsafe_allow_html=True,
)


@dataclass
class ConversionResult:
    filename: str
    markdown: str
    pages: int
    characters: int
    warnings: list[str]


def normalize_line(line: str) -> str:
    """Normalize PDF oddities without destroying meaningful whitespace."""
    return (
        line.replace("\u00ad", "")
        .replace("\u00a0", " ")
        .replace("\ufb00", "ff")
        .replace("\ufb01", "fi")
        .replace("\ufb02", "fl")
        .strip()
    )


def repeated_margin_lines(pages: list[list[str]]) -> set[str]:
    """Find likely headers/footers repeated on most pages."""
    if len(pages) < 3:
        return set()

    candidates: Counter[str] = Counter()
    for lines in pages:
        visible = [line for line in lines if line]
        # Only use the outermost visible lines. Including the second line can
        # accidentally remove repeated body text from similarly laid-out pages.
        candidates.update(set(visible[:1] + visible[-1:]))

    threshold = max(3, round(len(pages) * 0.6))
    return {
        line
        for line, count in candidates.items()
        if count >= threshold and len(line) < 120
    }


def looks_like_heading(line: str) -> bool:
    if not line or len(line) > 100 or line.endswith(('.', ',', ';', ':')):
        return False
    words = line.split()
    if not 1 <= len(words) <= 12:
        return False
    if re.match(r"^(chapter|part|section)\s+([\divxlcdm]+)\b", line, re.I):
        return True
    letters = [char for char in line if char.isalpha()]
    return bool(letters) and all(char.isupper() for char in letters)


def lines_to_markdown(lines: list[str]) -> str:
    """Join wrapped prose while keeping paragraphs, headings, and list items."""
    blocks: list[str] = []
    paragraph: list[str] = []

    def flush() -> None:
        if paragraph:
            text = " ".join(paragraph)
            text = re.sub(r"(?<=\w)- (?=[a-z])", "", text)
            blocks.append(re.sub(r"\s+", " ", text).strip())
            paragraph.clear()

    for line in lines:
        if not line:
            flush()
            continue
        if looks_like_heading(line):
            flush()
            blocks.append(f"## {line.title() if line.isupper() else line}")
        elif re.match(r"^(?:[-*•]|\d+[.)])\s+", line):
            flush()
            blocks.append(re.sub(r"^•\s+", "- ", line))
        else:
            paragraph.append(line)
    flush()
    return "\n\n".join(block for block in blocks if block)


def convert_pdf(
    data: bytes,
    original_name: str,
    remove_margins: bool,
    page_markers: bool,
) -> ConversionResult:
    warnings: list[str] = []
    reader = PdfReader(io.BytesIO(data))
    if reader.is_encrypted:
        try:
            reader.decrypt("")
        except Exception as exc:
            raise ValueError("This PDF is password-protected.") from exc

    raw_pages: list[list[str]] = []
    for index, page in enumerate(reader.pages, start=1):
        try:
            # Plain extraction usually preserves prose flow better than layout
            # mode, which can insert large runs of spaces and blank lines.
            text = page.extract_text() or ""
        except TypeError:  # Compatibility with older pypdf versions.
            text = page.extract_text() or ""
        if not text.strip():
            warnings.append(f"Page {index} contains no extractable text.")
        raw_pages.append([normalize_line(line) for line in text.splitlines()])

    margins = repeated_margin_lines(raw_pages) if remove_margins else set()
    title = Path(original_name).stem.replace("_", " ").replace("-", " ").strip().title()
    output = [f"# {title}"]

    for index, lines in enumerate(raw_pages, start=1):
        cleaned = [line for line in lines if line not in margins]
        body = lines_to_markdown(cleaned)
        if page_markers:
            output.append(f"<!-- Page {index} -->")
        if body:
            output.append(body)

    markdown = "\n\n".join(output).strip() + "\n"
    if not any(page.extract_text() for page in reader.pages):
        warnings.append("This looks like a scanned PDF. OCR is required to read it.")

    return ConversionResult(
        filename=f"{Path(original_name).stem}.md",
        markdown=markdown,
        pages=len(reader.pages),
        characters=len(markdown),
        warnings=warnings,
    )


def build_zip(results: list[ConversionResult]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for result in results:
            archive.writestr(result.filename, result.markdown)
    return buffer.getvalue()


st.title("PDF to Markdown")
st.markdown(
    '<p class="quiet">Turn text-based PDFs into clean Markdown for LLMs. '
    "Your files stay on this machine.</p>",
    unsafe_allow_html=True,
)

uploads = st.file_uploader(
    "Choose one or more PDFs",
    type=["pdf"],
    accept_multiple_files=True,
    help="Scanned/image-only PDFs need OCR and will be flagged.",
)

with st.expander("Conversion options"):
    remove_margins = st.checkbox("Remove repeated headers and footers", value=True)
    page_markers = st.checkbox("Add invisible page markers", value=True)

if uploads:
    results: list[ConversionResult] = []
    for upload in uploads:
        try:
            results.append(
                convert_pdf(upload.getvalue(), upload.name, remove_margins, page_markers)
            )
        except Exception as exc:
            st.error(f"Could not convert {upload.name}: {exc}")

    if results:
        total_pages = sum(item.pages for item in results)
        st.success(f"Converted {len(results)} file(s) across {total_pages} page(s).")

        if len(results) > 1:
            st.download_button(
                "Download all as ZIP",
                data=build_zip(results),
                file_name="markdown-books.zip",
                mime="application/zip",
                type="primary",
                use_container_width=True,
            )

        for result in results:
            with st.container(border=True):
                st.subheader(result.filename)
                st.caption(f"{result.pages} pages · {result.characters:,} characters")
                for warning in result.warnings:
                    st.warning(warning)
                st.download_button(
                    "Download Markdown",
                    data=result.markdown,
                    file_name=result.filename,
                    mime="text/markdown",
                    key=f"download-{result.filename}",
                    use_container_width=True,
                )
                with st.expander("Preview"):
                    st.code(result.markdown[:12000], language="markdown")
elif uploads == []:
    st.info("Drop PDFs above to get started.")

st.divider()
st.caption("Best for text-based PDFs. Formatting is simplified intentionally for reliable LLM ingestion.")
