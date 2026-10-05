# PDF to Markdown

A small local web app that extracts text from PDFs and produces clean Markdown files for use with LLMs.

## Features

- Convert one or many text-based PDFs
- Join wrapped lines and repair common hyphenation
- Detect simple headings and lists
- Remove repeated page headers and footers
- Preserve page references with invisible HTML comments
- Download individual Markdown files or a ZIP
- Flag pages that likely require OCR

## Run locally

Python 3.10 or newer is recommended.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
streamlit run app.py
```

Streamlit will open the app in your browser. Uploaded files are processed in memory and are not sent to an external service.

## Limitations

PDFs store positioned characters rather than semantic document structure, so complex tables, multi-column layouts, and footnotes may require manual cleanup. Image-only scans need OCR before they can be converted.
