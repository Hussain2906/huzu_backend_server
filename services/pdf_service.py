from __future__ import annotations

from textwrap import wrap


def build_text_pdf(title: str, body_lines: list[str], font: str = "Helvetica") -> bytes:
    """Render a simple multi-page text PDF without third-party dependencies."""

    safe_title = _pdf_safe(title)
    paged_lines = _paginate(body_lines)

    objects: list[bytes | None] = [None]
    font_name = "Courier" if font.lower() == "courier" else "Helvetica"
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objects.append(None)  # pages tree placeholder
    objects.append(f"<< /Type /Font /Subtype /Type1 /BaseFont /{font_name} >>".encode("latin-1"))

    page_object_numbers: list[int] = []

    for page_lines in paged_lines:
        content_bytes = _build_page_stream(safe_title, page_lines, font)
        content_object_number = len(objects)
        objects.append(
            (
                f"<< /Length {len(content_bytes)} >>\nstream\n".encode("latin-1")
                + content_bytes
                + b"\nendstream"
            )
        )
        page_object_number = len(objects)
        objects.append(
            (
                "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
                "/Resources << /Font << /F1 3 0 R >> >> "
                f"/Contents {content_object_number} 0 R >>"
            ).encode("latin-1")
        )
        page_object_numbers.append(page_object_number)

    kids = " ".join(f"{number} 0 R" for number in page_object_numbers)
    objects[2] = f"<< /Type /Pages /Kids [{kids}] /Count {len(page_object_numbers)} >>".encode("latin-1")

    pdf = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]

    for number in range(1, len(objects)):
        offsets.append(len(pdf))
        pdf.extend(f"{number} 0 obj\n".encode("latin-1"))
        pdf.extend(objects[number] or b"")
        pdf.extend(b"\nendobj\n")

    xref_offset = len(pdf)
    pdf.extend(f"xref\n0 {len(objects)}\n".encode("latin-1"))
    pdf.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode("latin-1"))
    pdf.extend(
        (
            f"trailer\n<< /Size {len(objects)} /Root 1 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF"
        ).encode("latin-1")
    )
    return bytes(pdf)


def _paginate(body_lines: list[str], max_chars: int = 92, max_lines_per_page: int = 42) -> list[list[str]]:
    expanded_lines: list[str] = []
    for line in body_lines:
        safe_line = _pdf_safe(line)
        if not safe_line:
            expanded_lines.append("")
            continue
        wrapped = wrap(safe_line, width=max_chars, break_long_words=True, replace_whitespace=False)
        expanded_lines.extend(wrapped or [""])

    if not expanded_lines:
        expanded_lines.append("")

    pages: list[list[str]] = []
    current: list[str] = []
    for line in expanded_lines:
        current.append(line)
        if len(current) >= max_lines_per_page:
            pages.append(current)
            current = []
    if current:
        pages.append(current)
    return pages


def _build_page_stream(title: str, page_lines: list[str], font: str) -> bytes:
    commands = [
        "BT",
        "/F1 18 Tf",
        "48 804 Td",
        f"({ _escape_pdf(title) }) Tj",
        "0 -28 Td",
        "/F1 11 Tf",
    ]
    for line in page_lines:
        commands.append(f"({ _escape_pdf(line) }) Tj")
        commands.append("0 -16 Td")
    commands.append("ET")
    return "\n".join(commands).encode("latin-1")


def _pdf_safe(value: str) -> str:
    return value.encode("latin-1", "replace").decode("latin-1").strip()


def _escape_pdf(value: str) -> str:
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
