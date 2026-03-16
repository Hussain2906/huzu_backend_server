from __future__ import annotations

from html import escape
from typing import Any


def render_tax_invoice_html(invoice: Any, settings: dict[str, Any] | None = None) -> str:
    seller = getattr(invoice, "company", None)
    buyer = getattr(invoice, "customer", None) or getattr(invoice, "supplier", None)
    seller_extra = _extra(seller)
    buyer_extra = _extra(buyer)
    meta = _meta(invoice)
    lines = list(getattr(invoice, "lines", []) or [])
    tax_rows = list(getattr(invoice, "tax_summary", []) or [])
    total_quantity = getattr(invoice, "total_quantity", None)
    if total_quantity is None:
        total_quantity = sum(float(getattr(line, "qty", 0) or 0) for line in lines)
    interstate = bool(getattr(invoice, "is_interstate", False))
    round_off = _round_off(invoice)
    seller_name = _seller_name(seller)
    buyer_name = _buyer_name(buyer)

    summary_rows = [
        ("Taxable Value", _money(getattr(invoice, "subtotal", 0))),
    ]
    if interstate:
        summary_rows.append(("IGST", _money(getattr(invoice, "igst_amount", 0))))
    else:
        summary_rows.extend(
            [
                ("CGST", _money(getattr(invoice, "cgst_amount", 0))),
                ("SGST", _money(getattr(invoice, "sgst_amount", 0))),
            ]
        )
    if abs(round_off) >= 0.005:
        summary_rows.append(("Round Off", _money(round_off)))
    summary_rows.append(("Grand Total", _money(getattr(invoice, "grand_total", 0))))

    item_rows_html = "".join(
        f"""
        <tr>
          <td class="center">{index}</td>
          <td>{_h(getattr(line, 'description', ''))}</td>
          <td class="center">{_h(getattr(line, 'hsn', '') or '-')}</td>
          <td class="right">{_qty(getattr(line, 'qty', 0))}</td>
          <td class="right">{_money(getattr(line, 'price', 0))}</td>
          <td class="center">{_h(getattr(line, 'unit', '') or '-')}</td>
          <td class="right">{_money(getattr(line, 'line_total', 0))}</td>
        </tr>
        """
        for index, line in enumerate(lines, start=1)
    )

    tax_header = """
      <tr>
        <th>HSN/SAC</th>
        <th class="right">Taxable Value</th>
        <th class="right">Central Tax Rate</th>
        <th class="right">Central Tax Amount</th>
        <th class="right">State Tax Rate</th>
        <th class="right">State Tax Amount</th>
        <th class="right">Integrated Tax Rate</th>
        <th class="right">Integrated Tax Amount</th>
        <th class="right">Total Tax Amount</th>
      </tr>
    """
    tax_rows_html = "".join(
        f"""
        <tr>
          <td class="center">{_h(getattr(row, 'hsn', '') or '-')}</td>
          <td class="right">{_money(getattr(row, 'taxable_value', 0))}</td>
          <td class="right">{_percent(getattr(row, 'central_tax_rate', None))}</td>
          <td class="right">{_money(getattr(row, 'central_tax_amount', 0))}</td>
          <td class="right">{_percent(getattr(row, 'state_tax_rate', None))}</td>
          <td class="right">{_money(getattr(row, 'state_tax_amount', 0))}</td>
          <td class="right">{_percent(getattr(row, 'integrated_tax_rate', None))}</td>
          <td class="right">{_money(getattr(row, 'integrated_tax_amount', 0))}</td>
          <td class="right">{_money(getattr(row, 'total_tax_amount', 0))}</td>
        </tr>
        """
        for row in tax_rows
    )
    tax_totals_html = f"""
      <tr class="bold">
        <td>Total</td>
        <td class="right">{_money(getattr(invoice, 'subtotal', 0))}</td>
        <td class="right"></td>
        <td class="right">{_money(getattr(invoice, 'cgst_amount', 0))}</td>
        <td class="right"></td>
        <td class="right">{_money(getattr(invoice, 'sgst_amount', 0))}</td>
        <td class="right"></td>
        <td class="right">{_money(getattr(invoice, 'igst_amount', 0))}</td>
        <td class="right">{_money(getattr(invoice, 'tax_total', 0))}</td>
      </tr>
    """

    metadata_rows = "".join(
        f"""
        <tr>
          <td class="label">{_h(label)}</td>
          <td>{_h(value or '-')}</td>
        </tr>
        """
        for label, value in _metadata_pairs(invoice, settings)
    )

    summary_rows_html = "".join(
        f"<tr><td>{_h(label)}</td><td class=\"right{' strong' if label == 'Grand Total' else ''}\">{_h(value)}</td></tr>"
        for label, value in summary_rows
    )

    declaration_text = seller_extra.get(
        "declaration_text",
        "We declare that this invoice shows the actual price of the goods described and that all particulars are true and correct.",
    )
    signatory_label = seller_extra.get("authorised_signatory_name") or "Authorised Signatory"
    signatory_caption = seller_extra.get("authorised_signatory_designation") or signatory_label

    upi_id = _safe_text((seller_extra or {}).get("upi_id"), "")
    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>Tax Invoice { _h(getattr(invoice, 'invoice_no', '')) }</title>
  <style>
    @page {{ size: A4 portrait; margin: 12mm; }}
    html, body {{ margin: 0; padding: 0; background: #ffffff; color: #000000; }}
    body {{ font-family: Arial, Helvetica, sans-serif; font-size: 11px; line-height: 1.28; }}
    .sheet {{ width: 186mm; margin: 0 auto; background: #ffffff; }}
    .title {{ text-align: center; font-size: 18px; font-weight: 700; margin: 0 0 6px; }}
    table {{ width: 100%; border-collapse: collapse; table-layout: fixed; }}
    td, th {{ border: 1px solid #000000; padding: 4px 6px; vertical-align: top; }}
    .no-padding {{ padding: 0; }}
    .inner td, .inner th {{ padding: 4px 6px; }}
    .bold {{ font-weight: 700; }}
    .label {{ width: 41%; font-weight: 700; }}
    .right {{ text-align: right; }}
    .center {{ text-align: center; }}
    .small {{ font-size: 10px; }}
    .seller-name {{ font-size: 14px; font-weight: 700; }}
    .section-title {{ font-weight: 700; margin-bottom: 2px; }}
    .spacer {{ height: 8px; }}
    .summary td:first-child {{ width: 56%; }}
    .summary .strong {{ font-size: 13px; font-weight: 700; }}
    .declaration {{ height: 72px; }}
    .signature-box {{ height: 72px; text-align: right; }}
    .footer {{ text-align: center; font-size: 10px; margin-top: 8px; }}
  </style>
</head>
<body>
  <div class="sheet">
    <div class="title">Tax Invoice</div>
    <table>
      <tr>
        <td style="width:58%" class="no-padding">
          <table class="inner">
            <tr>
              <td>
                <div class="seller-name">{_h(seller_name)}</div>
                {_optional_line(_seller_legal_name(seller))}
                {_optional_line(_joined_address(seller, seller_extra))}
                {_optional_line('GSTIN/UIN: ' + _safe_text(getattr(seller, 'gstin', None), '-'))}
                {_optional_line('PAN: ' + _safe_text(seller_extra.get('pan'), '-'))}
                {_optional_line('State Name: ' + _safe_text(_seller_state(seller, seller_extra), '-'))}
                {_optional_line('State Code: ' + _safe_text(_seller_state_code(seller, seller_extra), '-'))}
                {_optional_line('Phone: ' + _safe_text(_seller_phone(seller), '-'))}
                {_optional_line('Email: ' + _safe_text(seller_extra.get('email'), '-'))}
                {_optional_line('Registration: ' + _safe_text(seller_extra.get('registration_details'), '-'))}
              </td>
            </tr>
            <tr>
              <td>
                <div class="section-title">Buyer (Bill to)</div>
                <div class="bold">{_h(buyer_name)}</div>
                {_optional_line(_buyer_legal_name(buyer))}
                {_optional_line(_joined_address(buyer, buyer_extra))}
                {_optional_line('GSTIN/UIN: ' + _safe_text(getattr(buyer, 'gstin', None), '-'))}
                {_optional_line('PAN: ' + _safe_text(_buyer_pan(buyer, buyer_extra), '-'))}
                {_optional_line('State Name: ' + _safe_text(_buyer_state(buyer, buyer_extra), '-'))}
                {_optional_line('State Code: ' + _safe_text(_buyer_state_code(buyer, buyer_extra), '-'))}
                {_optional_line('Phone: ' + _safe_text(getattr(buyer, 'phone', None), '-'))}
                {_optional_line('Email: ' + _safe_text(getattr(buyer, 'email', None) or buyer_extra.get('email'), '-'))}
              </td>
            </tr>
          </table>
        </td>
        <td style="width:42%" class="no-padding">
          <table class="inner">
            {metadata_rows}
          </table>
        </td>
      </tr>
    </table>

    <div class="spacer"></div>

    <table>
      <thead>
        <tr>
          <th style="width:6%">Sl. No.</th>
          <th style="width:37%">Description of Goods</th>
          <th style="width:11%">HSN/SAC</th>
          <th style="width:11%">Quantity</th>
          <th style="width:12%">Rate</th>
          <th style="width:8%">per</th>
          <th style="width:15%">Amount</th>
        </tr>
      </thead>
      <tbody>
        {item_rows_html}
        <tr class="bold">
          <td colspan="3" class="right">Total</td>
          <td class="right">{_qty(total_quantity)}</td>
          <td></td>
          <td></td>
          <td class="right">{_money(getattr(invoice, 'subtotal', 0))}</td>
        </tr>
      </tbody>
    </table>

    <div class="spacer"></div>

    <table>
      <tr>
        <td style="width:58%">
          <div class="section-title">Amount Chargeable (in words)</div>
          <div>{_h(getattr(invoice, 'amount_in_words', '') or '-')}</div>
          <div style="margin-top:8px">Total Items: {_h(str(len(lines)))}</div>
          <div>Total Quantity: {_h(_qty(total_quantity))}</div>
        </td>
        <td style="width:42%" class="no-padding">
          <table class="inner summary">
            {summary_rows_html}
          </table>
        </td>
      </tr>
    </table>

    <div class="spacer"></div>

    <table>
      <thead>
        {tax_header}
      </thead>
      <tbody>
        {tax_rows_html}
        {tax_totals_html}
      </tbody>
    </table>

    <div class="spacer"></div>

    <table>
      <tr>
        <td>Tax Amount (in words): {_h(getattr(invoice, 'tax_amount_in_words', '') or '-')}</td>
      </tr>
    </table>

    <div class="spacer"></div>

    <table>
      <tr>
        <td style="width:60%">
          <div class="section-title">Declaration</div>
          <div class="declaration">{_h(declaration_text)}</div>
        </td>
        <td style="width:40%">
          <div class="signature-box">
            <div class="bold">for {_h(seller_name)}</div>
            <div style="height:42px"></div>
            <div>{_h(signatory_caption)}</div>
          </div>
        </td>
      </tr>
    </table>

    <div class="footer">This is a Computer Generated Invoice</div>
  </div>
</body>
</html>"""


def build_tax_invoice_pdf(invoice: Any, settings: dict[str, Any] | None = None) -> bytes:
    seller = getattr(invoice, "company", None)
    buyer = getattr(invoice, "customer", None) or getattr(invoice, "supplier", None)
    seller_extra = _extra(seller)
    buyer_extra = _extra(buyer)
    meta = _meta(invoice)
    lines = list(getattr(invoice, "lines", []) or [])
    tax_rows = list(getattr(invoice, "tax_summary", []) or [])
    total_quantity = getattr(invoice, "total_quantity", None)
    if total_quantity is None:
        total_quantity = sum(float(getattr(line, "qty", 0) or 0) for line in lines)
    seller_name = _seller_name(seller)
    buyer_name = _buyer_name(buyer)
    round_off = _round_off(invoice)
    canvas = _PdfCanvas()

    page_width = 595.0
    page_height = 842.0
    margin = 26.0
    content_width = page_width - (margin * 2)
    top = 28.0
    bottom_guard = 34.0

    def top_to_pdf(y_top: float) -> float:
        return page_height - y_top

    def draw_rect(x: float, y_top: float, width: float, height: float, line_width: float = 0.8) -> None:
        canvas.rect(x, top_to_pdf(y_top + height), width, height, line_width)

    def draw_hline(x1: float, x2: float, y_top: float, line_width: float = 0.8) -> None:
        canvas.line(x1, top_to_pdf(y_top), x2, top_to_pdf(y_top), line_width)

    def draw_vline(x: float, y1_top: float, y2_top: float, line_width: float = 0.8) -> None:
        canvas.line(x, top_to_pdf(y1_top), x, top_to_pdf(y2_top), line_width)

    def draw_text(
        x: float,
        y_top: float,
        text: str,
        size: float = 9.0,
        bold: bool = False,
        align: str = "left",
        width: float | None = None,
    ) -> None:
        canvas.text(x, top_to_pdf(y_top), text, size=size, bold=bold, align=align, width=width)

    title_y = top
    draw_text(margin, title_y, "Tax Invoice", size=16, bold=True, align="center", width=content_width)
    cursor = title_y + 18.0

    left_width = content_width * 0.58
    right_width = content_width - left_width

    seller_lines = [
        (seller_name, 12.0, True),
        (_seller_legal_name(seller), 9.0, False),
        (_joined_address(seller, seller_extra), 9.0, False),
        (f"GSTIN/UIN: {_safe_text(getattr(seller, 'gstin', None), '-')}", 8.7, False),
        (f"PAN: {_safe_text(seller_extra.get('pan'), '-')}", 8.7, False),
        (f"State Name: {_safe_text(_seller_state(seller, seller_extra), '-')}", 8.7, False),
        (f"State Code: {_safe_text(_seller_state_code(seller, seller_extra), '-')}", 8.7, False),
        (f"Phone: {_safe_text(_seller_phone(seller), '-')}", 8.7, False),
        (f"Email: {_safe_text(seller_extra.get('email'), '-')}", 8.7, False),
        (f"Registration: {_safe_text(seller_extra.get('registration_details'), '-')}", 8.7, False),
    ]
    buyer_lines = [
        (buyer_name, 10.0, True),
        (_buyer_legal_name(buyer), 8.7, False),
        (_joined_address(buyer, buyer_extra), 8.7, False),
        (f"GSTIN/UIN: {_safe_text(getattr(buyer, 'gstin', None), '-')}", 8.7, False),
        (f"PAN: {_safe_text(_buyer_pan(buyer, buyer_extra), '-')}", 8.7, False),
        (f"State Name: {_safe_text(_buyer_state(buyer, buyer_extra), '-')}", 8.7, False),
        (f"State Code: {_safe_text(_buyer_state_code(buyer, buyer_extra), '-')}", 8.7, False),
        (f"Phone: {_safe_text(getattr(buyer, 'phone', None), '-')}", 8.7, False),
        (f"Email: {_safe_text(getattr(buyer, 'email', None) or buyer_extra.get('email'), '-')}", 8.7, False),
    ]

    seller_height = 16.0
    for raw_text, font_size, _ in seller_lines:
        if not raw_text:
            continue
        seller_height += len(_wrap_lines(raw_text, 44)) * (font_size + 2.4)
    seller_height += 8.0

    buyer_height = 26.0
    for raw_text, font_size, _ in buyer_lines:
        if not raw_text:
            continue
        buyer_height += len(_wrap_lines(raw_text, 44)) * (font_size + 2.4)
    buyer_height += 8.0

    meta_x = margin + left_width
    meta_pairs = _metadata_pairs(invoice, settings)
    meta_label_w = right_width * 0.41
    meta_row_specs: list[tuple[list[str], list[str], float]] = []
    for label, value in meta_pairs:
        label_lines = _wrap_lines(label, 18)[:3]
        value_lines = _wrap_lines(value or "-", 22)[:3]
        row_line_count = max(len(label_lines), len(value_lines), 1)
        row_height = max(24.0, 8.0 + (row_line_count * 8.6))
        meta_row_specs.append((label_lines, value_lines, row_height))
    meta_height = sum(row_height for _, _, row_height in meta_row_specs)

    master_height = max(170.0, seller_height + buyer_height, meta_height)
    draw_rect(margin, cursor, content_width, master_height)
    draw_vline(margin + left_width, cursor, cursor + master_height)
    draw_hline(margin, margin + left_width, cursor + seller_height)

    seller_y = cursor + 16.0
    for raw_text, font_size, bold in seller_lines:
        if not raw_text:
            continue
        for wrapped in _wrap_lines(raw_text, 44):
            draw_text(margin + 8, seller_y, wrapped, size=font_size, bold=bold)
            seller_y += font_size + 2.4

    buyer_y = cursor + seller_height + 14.0
    draw_text(margin + 8, buyer_y, "Buyer (Bill to)", size=9.2, bold=True)
    buyer_y += 12.0
    for raw_text, font_size, bold in buyer_lines:
        if not raw_text:
            continue
        for wrapped in _wrap_lines(raw_text, 44):
            draw_text(margin + 8, buyer_y, wrapped, size=font_size, bold=bold)
            buyer_y += font_size + 2.4

    row_cursor = cursor
    for index, (label_lines, value_lines, row_height) in enumerate(meta_row_specs):
        if index:
            draw_hline(meta_x, meta_x + right_width, row_cursor)
        draw_vline(meta_x + meta_label_w, row_cursor, row_cursor + row_height)
        label_y = row_cursor + 8.2
        for wrapped in label_lines:
            draw_text(meta_x + 5, label_y, wrapped, size=7.8, bold=True)
            label_y += 8.2
        value_y = row_cursor + 8.2
        for wrapped in value_lines:
            draw_text(meta_x + meta_label_w + 4, value_y, wrapped, size=7.8)
            value_y += 8.2
        row_cursor += row_height

    cursor += master_height + 10.0

    item_top = cursor
    summary_reserved = 36.0
    tax_reserved = max(74.0, 26.0 + (len(tax_rows) * 15.0))
    declaration_reserved = 92.0
    footer_reserved = 22.0
    available_items_height = page_height - bottom_guard - footer_reserved - declaration_reserved - tax_reserved - summary_reserved - item_top - 28.0
    header_height = 18.0
    total_row_height = 18.0
    safe_lines = lines or [None]
    default_row_height = min(18.0, max(12.5, (available_items_height - header_height - total_row_height) / max(len(lines), 1)))
    row_heights: list[float] = []
    for line in safe_lines:
        if line is None:
            row_heights.append(default_row_height)
            continue
        desc_lines = _wrap_lines(_safe_text(getattr(line, "description", None), "-"), 30)
        row_heights.append(max(default_row_height, min(30.0, 7.0 + (len(desc_lines) * 8.0))))
    item_table_height = header_height + total_row_height + sum(row_heights)

    item_columns = [0.06, 0.37, 0.11, 0.11, 0.12, 0.08, 0.15]
    item_widths = [content_width * ratio for ratio in item_columns]
    item_xs = [margin]
    for width in item_widths[:-1]:
        item_xs.append(item_xs[-1] + width)
    draw_rect(margin, item_top, content_width, item_table_height)
    running_x = margin
    for width in item_widths[:-1]:
        running_x += width
        draw_vline(running_x, item_top, item_top + item_table_height)
    draw_hline(margin, margin + content_width, item_top + header_height)
    header_titles = ["Sl. No.", "Description of Goods", "HSN/SAC", "Quantity", "Rate", "per", "Amount"]
    for x, width, title in zip(item_xs, item_widths, header_titles):
        draw_text(x + 3, item_top + 11.5, title, size=8.5, bold=True, align="center", width=width - 6)

    current_row_y = item_top + header_height
    for index, line in enumerate(safe_lines, start=1):
        data_row_height = row_heights[index - 1]
        next_y = current_row_y + data_row_height
        draw_hline(margin, margin + content_width, next_y)
        if line is not None:
            values = [
                str(index),
                _safe_text(getattr(line, "description", None), "-"),
                _safe_text(getattr(line, "hsn", None), "-"),
                _qty(getattr(line, "qty", 0)),
                _money(getattr(line, "price", 0)),
                _safe_text(getattr(line, "unit", None), "-"),
                _money(getattr(line, "line_total", 0)),
            ]
            aligns = ["center", "left", "center", "right", "right", "center", "right"]
            char_limits = [4, 30, 10, 8, 10, 8, 12]
            for column_index, (x, width, value, align, limit) in enumerate(zip(item_xs, item_widths, values, aligns, char_limits)):
                wrapped_lines = _wrap_lines(value, limit)
                if column_index == 1:
                    text_y = current_row_y + 8.0
                    for wrapped in wrapped_lines[:3]:
                        draw_text(x + 3, text_y, wrapped, size=8.4, align=align, width=width - 6)
                        text_y += 8.0
                else:
                    draw_text(
                        x + 3,
                        current_row_y + (data_row_height / 2) + 3.0,
                        wrapped_lines[0],
                        size=8.4,
                        align=align,
                        width=width - 6,
                    )
        current_row_y = next_y

    total_top = item_top + header_height + sum(row_heights)
    draw_text(
        item_xs[1] + 3,
        total_top + 11.5,
        "Total",
        size=8.7,
        bold=True,
        align="right",
        width=(item_widths[1] + item_widths[2]) - 6,
    )
    draw_text(item_xs[3] + 3, total_top + 11.5, _qty(total_quantity), size=8.7, bold=True, align="right", width=item_widths[3] - 6)
    draw_text(item_xs[6] + 3, total_top + 11.5, _money(getattr(invoice, "subtotal", 0)), size=8.7, bold=True, align="right", width=item_widths[6] - 6)

    cursor = item_top + item_table_height + 8.0

    amount_word_lines = _wrap_lines(getattr(invoice, "amount_in_words", None) or "-", 48)[:3]
    left_summary_w = content_width * 0.58
    right_summary_w = content_width - left_summary_w
    summary_pairs = [("Taxable Value", _money(getattr(invoice, "subtotal", 0)))]
    if getattr(invoice, "is_interstate", False):
        summary_pairs.append(("IGST", _money(getattr(invoice, "igst_amount", 0))))
    else:
        summary_pairs.extend(
            [
                ("CGST", _money(getattr(invoice, "cgst_amount", 0))),
                ("SGST", _money(getattr(invoice, "sgst_amount", 0))),
            ]
        )
    if abs(round_off) >= 0.005:
        summary_pairs.append(("Round Off", _money(round_off)))
    summary_pairs.append(("Grand Total", _money(getattr(invoice, "grand_total", 0))))
    summary_height = max(40.0, 18.0 + (len(amount_word_lines) * 8.8), len(summary_pairs) * 16.0)
    draw_rect(margin, cursor, content_width, summary_height)
    draw_vline(margin + left_summary_w, cursor, cursor + summary_height)
    draw_text(margin + 8, cursor + 10, "Amount Chargeable (in words)", size=8.7, bold=True)
    for idx, wrapped in enumerate(amount_word_lines):
        draw_text(margin + 8, cursor + 21 + (idx * 9), wrapped, size=8.5)
    summary_row_h = summary_height / len(summary_pairs)
    for idx, (label, value) in enumerate(summary_pairs):
        row_y = cursor + (idx * summary_row_h)
        if idx:
            draw_hline(margin + left_summary_w, margin + content_width, row_y)
        draw_vline(margin + left_summary_w + (right_summary_w * 0.58), row_y, row_y + summary_row_h)
        draw_text(margin + left_summary_w + 4, row_y + 8.5, label, size=8.5, bold=label == "Grand Total")
        draw_text(margin + left_summary_w + (right_summary_w * 0.58) + 4, row_y + 8.5, value, size=8.5, bold=label == "Grand Total", align="right", width=(right_summary_w * 0.42) - 8)

    cursor += summary_height + 8.0

    tax_titles = [
        "HSN/SAC",
        "Taxable Value",
        "Central Tax Rate",
        "Central Tax Amount",
        "State Tax Rate",
        "State Tax Amount",
        "Integrated Tax Rate",
        "Integrated Tax Amount",
        "Total Tax Amount",
    ]
    tax_title_limits = [8, 11, 11, 12, 11, 12, 13, 14, 12]
    tax_header_lines = [_wrap_lines(title, limit)[:3] for title, limit in zip(tax_titles, tax_title_limits)]
    tax_header_height = max(24.0, 8.0 + (max(len(lines_) for lines_ in tax_header_lines) * 7.2))
    tax_row_height = 18.0
    tax_table_height = tax_header_height + ((len(tax_rows) + 1) * tax_row_height)
    tax_cols = [0.10, 0.14, 0.10, 0.12, 0.10, 0.12, 0.10, 0.12, 0.10]
    tax_widths = [content_width * ratio for ratio in tax_cols]
    tax_xs = [margin]
    for width in tax_widths[:-1]:
        tax_xs.append(tax_xs[-1] + width)
    draw_rect(margin, cursor, content_width, tax_table_height)
    running_x = margin
    for width in tax_widths[:-1]:
        running_x += width
        draw_vline(running_x, cursor, cursor + tax_table_height)
    draw_hline(margin, margin + content_width, cursor + tax_header_height)
    for x, width, wrapped_title in zip(tax_xs, tax_widths, tax_header_lines):
        text_y = cursor + 8.0
        for title_line in wrapped_title:
            draw_text(x + 3, text_y, title_line, size=6.8, bold=True, align="center", width=width - 6)
            text_y += 7.0

    tax_row_top = cursor + tax_header_height
    for row in tax_rows:
        next_y = tax_row_top + tax_row_height
        draw_hline(margin, margin + content_width, next_y)
        row_values = [
            _safe_text(getattr(row, "hsn", None), "-"),
            _money(getattr(row, "taxable_value", 0)),
            _percent(getattr(row, "central_tax_rate", None)),
            _money(getattr(row, "central_tax_amount", 0)),
            _percent(getattr(row, "state_tax_rate", None)),
            _money(getattr(row, "state_tax_amount", 0)),
            _percent(getattr(row, "integrated_tax_rate", None)),
            _money(getattr(row, "integrated_tax_amount", 0)),
            _money(getattr(row, "total_tax_amount", 0)),
        ]
        aligns = ["center", "right", "right", "right", "right", "right", "right", "right", "right"]
        for x, width, value, align in zip(tax_xs, tax_widths, row_values, aligns):
            draw_text(x + 3, tax_row_top + 11.5, value, size=7.5, align=align, width=width - 6)
        tax_row_top = next_y

    draw_hline(margin, margin + content_width, tax_row_top + tax_row_height)
    total_values = [
        "Total",
        _money(getattr(invoice, "subtotal", 0)),
        "",
        _money(getattr(invoice, "cgst_amount", 0)),
        "",
        _money(getattr(invoice, "sgst_amount", 0)),
        "",
        _money(getattr(invoice, "igst_amount", 0)),
        _money(getattr(invoice, "tax_total", 0)),
    ]
    total_aligns = ["left", "right", "right", "right", "right", "right", "right", "right", "right"]
    for x, width, value, align in zip(tax_xs, tax_widths, total_values, total_aligns):
        draw_text(x + 3, tax_row_top + 11.5, value, size=7.6, bold=True, align=align, width=width - 6)

    cursor += tax_table_height + 8.0

    tax_words_height = 22.0
    draw_rect(margin, cursor, content_width, tax_words_height)
    draw_text(margin + 8, cursor + 13, f"Tax Amount (in words): {_safe_text(getattr(invoice, 'tax_amount_in_words', None), '-')}", size=8.5)
    cursor += tax_words_height + 8.0

    declaration_height = 76.0
    left_decl_w = content_width * 0.60
    right_decl_w = content_width - left_decl_w
    draw_rect(margin, cursor, content_width, declaration_height)
    draw_vline(margin + left_decl_w, cursor, cursor + declaration_height)
    draw_text(margin + 8, cursor + 11, "Declaration", size=9.0, bold=True)
    declaration_text = seller_extra.get(
        "declaration_text",
        "We declare that this invoice shows the actual price of the goods described and that all particulars are true and correct.",
    )
    decl_y = cursor + 24
    for wrapped in _wrap_lines(declaration_text, 68)[:4]:
        draw_text(margin + 8, decl_y, wrapped, size=8.3)
        decl_y += 9.2
    draw_text(margin + left_decl_w + 8, cursor + 11, f"for {seller_name}", size=9.0, bold=True, align="right", width=right_decl_w - 16)
    draw_text(
        margin + left_decl_w + 8,
        cursor + declaration_height - 12,
        seller_extra.get("authorised_signatory_designation") or seller_extra.get("authorised_signatory_name") or "Authorised Signatory",
        size=8.5,
        align="right",
        width=right_decl_w - 16,
    )

    cursor += declaration_height + 10.0
    draw_text(margin, cursor + 8, "This is a Computer Generated Invoice", size=8.2, align="center", width=content_width)

    return canvas.build_pdf()


def render_simple_receipt_html(invoice: Any, settings: dict[str, Any], company_fallback: Any | None = None) -> str:
    seller = getattr(invoice, "company", None)
    seller_extra = _extra(seller) or getattr(company_fallback, "extra_json", None) or {}
    buyer = getattr(invoice, "customer", None) or getattr(invoice, "supplier", None)
    buyer_extra = _extra(buyer)
    visibility = dict((settings or {}).get("visibility") or {})
    layout = dict((settings or {}).get("layout") or {})
    lines = _ordered_lines(list(getattr(invoice, "lines", []) or []), layout.get("item_order_mode"))
    base_font = int(layout.get("pdf_font_size", 11))
    total_qty = getattr(invoice, "total_quantity", None)
    if total_qty is None:
        total_qty = sum(float(getattr(line, "qty", 0) or 0) for line in lines)
    seller_name = _seller_name(seller)
    show = lambda key, default=False: bool(visibility.get(key, default))
    show_serial = show("show_item_serial")
    show_hsn = show("show_item_hsn")
    show_qty = show("show_item_qty", True)
    show_unit = show("show_item_unit")
    show_rate = show("show_item_rate", True)
    show_line_discount = show("show_line_discount")
    show_item_tax = show("show_item_tax")
    item_grid = _simple_receipt_grid_template(show_serial, show_hsn, show_qty, show_unit, show_rate)
    item_rows = "".join(
        _simple_receipt_html_row(
            index=index,
            line=line,
            show_serial=show_serial,
            show_hsn=show_hsn,
            show_qty=show_qty,
            show_unit=show_unit,
            show_rate=show_rate,
            show_line_discount=show_line_discount,
            show_item_tax=show_item_tax,
            multiline=bool(layout.get("print_item_multiline", True)),
            item_name_size=int(layout.get("item_name_size", 13)),
        )
        for index, line in enumerate(lines, start=1)
    )
    address_text = _joined_address(seller, seller_extra)
    business_phone = _seller_phone(seller) or getattr(company_fallback, "phone", None)
    alternate_phone = _safe_text((seller_extra or {}).get("alternate_phone"), "")
    business_email = _safe_text((seller_extra or {}).get("email"), "")
    business_pan = _safe_text((seller_extra or {}).get("pan"), "")
    business_website = _safe_text((seller_extra or {}).get("website"), "")
    buyer_phone = _safe_text(getattr(buyer, "phone", None), "")
    buyer_gstin = _safe_text(getattr(buyer, "gstin", None), "")
    buyer_address = _joined_address(buyer, buyer_extra)
    upi_id = _safe_text((seller_extra or {}).get("upi_id"), "")
    business_name_size = int(layout.get("business_name_size", 21))
    total_amount_size = int(layout.get("total_amount_size", 24))
    saving_amount_size = int(layout.get("saving_amount_size", 15))
    header_lines = [line.strip() for line in address_text.split(", ") if line.strip()] if show("show_business_address", True) and address_text else []
    email_alt_line = " ".join(part for part in [f"@: {business_email}" if show("show_business_email") and business_email else "", alternate_phone if show("show_alternate_phone") and alternate_phone else ""] if part)
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>Sale Receipt { _h(getattr(invoice, 'invoice_no', '')) }</title>
<style>
@page{{size:A4 portrait;margin:12mm}}
html,body{{margin:0;padding:0;background:#fff;color:#111}}
body{{font-family:Arial,Helvetica,sans-serif;padding:18px}}
.page{{width:min(430px,100%);margin:0 auto;background:#fff}}
.center{{text-align:center}}
.muted{{color:#2b2b2b}}
.small{{font-size:{max(base_font, 12)}px}}
.meta{{font-size:14.5px;font-weight:500;line-height:1.38}}
.line{{border-top:1px solid #1e1e1e;margin:8px 0}}
.item-head{{display:grid;grid-template-columns:{item_grid};gap:0;align-items:end;font-size:15px;font-weight:800}}
.item-row{{display:grid;grid-template-columns:{item_grid};gap:0;align-items:start;padding:4px 0}}
.item-name{{font-size:{max(int(layout.get('item_name_size', 13)), 14)}px;line-height:1.38;overflow-wrap:anywhere}}
.item-detail{{display:block;margin-top:2px;font-size:{max(base_font + 1, 13)}px;color:#333}}
.summary-row{{display:flex;align-items:flex-start;gap:12px}}
.summary-label{{flex:1;text-align:right;font-size:15.5px;font-weight:500}}
.summary-value{{width:110px;text-align:right;font-size:15.5px;font-weight:600;white-space:nowrap}}
.total{{font-size:{total_amount_size}px;font-weight:800;text-align:center;border-top:1px solid #1e1e1e;border-bottom:1px solid #1e1e1e;padding:8px 0;margin-top:2px}}
.savings{{text-align:center;font-size:{saving_amount_size}px;font-weight:700}}
</style></head><body><div class="page">
<div class="center" style="font-size:{business_name_size}px;font-weight:800;letter-spacing:0.2px">{_h(seller_name.upper())}</div>
{f'<div class="center" style="margin-top:2px;font-size:17px;font-weight:700">{_h(getattr(company_fallback, "id", "")[:4].upper())}</div>' if show('show_store_code') and company_fallback else ''}
{f'<div style="height:8px"></div>' if header_lines or (show('show_business_phone', True) and business_phone) else ''}
{''.join(f'<div class="center muted">{_h(line)}</div>' for line in header_lines)}
{f'<div style="height:4px"></div><div class="center muted">Phone Number: {_h(business_phone)}</div>' if show('show_business_phone', True) and business_phone else ''}
{f'<div class="center muted">{_h(email_alt_line)}</div>' if email_alt_line else ''}
{f'<div class="center muted">GSTIN: {_h(getattr(seller, "gstin", None) or getattr(company_fallback, "gst_number", None) or "-")}</div>' if show('show_business_gstin') else ''}
{f'<div class="center muted">PAN: {_h(business_pan)}</div>' if show('show_business_pan') and business_pan else ''}
{f'<div class="center muted">{_h(business_website)}</div>' if show('show_website') and business_website else ''}
<div style="height:10px"></div>
{f'<div class="meta">Bill No: {_h(getattr(invoice, "invoice_no", ""))}</div><div style="height:4px"></div>' if show('show_invoice_number', True) else ''}
{f'<div class="meta">Created On: {_h(_format_receipt_datetime(getattr(invoice, "invoice_date", None), show("show_invoice_date", True), show("show_invoice_time", True)))}</div><div style="height:4px"></div>' if show('show_invoice_date', True) or show('show_invoice_time', True) else ''}
{f'<div class="meta">Bill To: {_h(_buyer_name(buyer))}</div>' if show('show_customer_name', True) else ''}
{f'<div style="height:4px"></div><div class="meta">Customer Phone: {_h(buyer_phone)}</div>' if show('show_customer_phone') and buyer_phone else ''}
{f'<div style="height:4px"></div><div class="meta">Customer GSTIN: {_h(buyer_gstin)}</div>' if show('show_customer_gstin') and buyer_gstin else ''}
{f'<div style="height:4px"></div><div class="meta">Customer Address: {_h(buyer_address)}</div>' if show('show_customer_address') and buyer_address else ''}
{f'<div style="height:4px"></div><div class="meta">Payment: {_h(str(getattr(invoice, "payment_mode", "") or "").replace("_"," "))}</div>' if show('show_payment_mode') and getattr(invoice, "payment_mode", None) else ''}
{f'<div style="height:4px"></div><div class="meta">Reference: {_h(getattr(invoice, "payment_reference", ""))}</div>' if show('show_payment_reference') and getattr(invoice, "payment_reference", None) else ''}
<div style="height:8px"></div>
<div class="line"></div>
<div style="height:8px"></div>
<div class="item-head">{''.join(f'<div style="text-align:{align}">{_h(label)}</div>' for _, label, _, align in _simple_receipt_columns(show_serial, show_hsn, show_qty, show_unit, show_rate))}</div>
<div style="height:6px"></div>
<div class="line"></div>
{item_rows}
<div style="height:8px"></div>
<div class="line"></div>
<div style="height:8px"></div>
{f'<div class="meta">Total Items: {_h(str(len(lines)))}</div><div style="height:4px"></div>' if show('show_total_items', True) else ''}
{f'<div class="meta">Total Quantity: {_h(_qty(total_qty))}</div>' if show('show_total_quantity', True) else ''}
<div style="height:8px"></div>
<div class="line"></div>
<div style="height:8px"></div>
{f'<div class="summary-row"><div class="summary-label">Sub Total</div><div class="summary-value">{_h(_receipt_currency(value=getattr(invoice, "subtotal", 0), mode="unicode"))}</div></div><div style="height:6px"></div>' if show('show_subtotal', True) else ''}
<div class="total">Total {_h(_receipt_currency(value=getattr(invoice, "grand_total", 0), mode="unicode"))}</div>
{f'<div style="height:8px"></div><div class="summary-row"><div class="summary-label">Balance</div><div class="summary-value">{_h(_receipt_currency(value=getattr(invoice, "balance_due", 0), mode="unicode"))}</div></div>' if show('show_balance_due', True) else ''}
{f'<div style="height:6px"></div><div class="savings">Total Savings {_h(_receipt_currency(value=_line_savings(lines), mode="unicode"))}</div>' if show('show_savings') else ''}
{f'<div class="line"></div><div class="center">{_h(layout.get("footer_text") or "")}</div>' if show('show_footer', True) and layout.get('footer_text') else ''}
{f'<div class="center small">{_h(layout.get("support_line") or "")}</div>' if show('show_support_line') and layout.get('support_line') else ''}
{f'<div class="center small">UPI: {_h(upi_id)}</div>' if show('show_qr_block') and layout.get('print_upi_qr') and upi_id else ''}
</div></body></html>"""


def build_simple_receipt_pdf(invoice: Any, settings: dict[str, Any], company_fallback: Any | None = None) -> bytes:
    seller = getattr(invoice, "company", None)
    seller_extra = _extra(seller) or getattr(company_fallback, "extra_json", None) or {}
    buyer = getattr(invoice, "customer", None) or getattr(invoice, "supplier", None)
    buyer_extra = _extra(buyer)
    visibility = dict((settings or {}).get("visibility") or {})
    layout = dict((settings or {}).get("layout") or {})
    upi_id = _safe_text((seller_extra or {}).get("upi_id"), "")
    lines = _ordered_lines(list(getattr(invoice, "lines", []) or []), layout.get("item_order_mode"))
    base_font = float(layout.get("pdf_font_size", 11))
    multiline = bool(layout.get("print_item_multiline", True))
    total_qty = getattr(invoice, "total_quantity", None)
    if total_qty is None:
        total_qty = sum(float(getattr(line, "qty", 0) or 0) for line in lines)
    page_width = 595.0
    page_height = 842.0
    receipt_width = min(430.0, page_width - 96.0)
    x0 = (page_width - receipt_width) / 2
    cursor = 36.0
    canvas = _PdfCanvas()
    show = lambda key, default=False: bool(visibility.get(key, default))
    body_font = max(base_font + 3.0, 14.0)
    meta_font = max(body_font + 0.8, 15.0)
    summary_font = max(body_font + 1.3, 15.5)
    total_font = max(float(layout.get("total_amount_size", 24)), 26.0)
    item_name_size = max(float(layout.get("item_name_size", 13)), 14.0)
    saving_font = max(float(layout.get("saving_amount_size", 15)), 16.0)
    amount_width = 110.0

    def draw(text: str, *, size: float | None = None, bold: bool = False, align: str = "left", width: float | None = None) -> None:
        nonlocal cursor
        effective_size = size or body_font
        canvas.text(x0, page_height - cursor, text, size=effective_size, bold=bold, align=align, width=width or receipt_width)
        cursor += effective_size + 3

    def line() -> None:
        nonlocal cursor
        y = page_height - (cursor + 4)
        canvas.line(x0, y, x0 + receipt_width, y)
        cursor += 14

    def draw_lr(label: str, value: str, *, size: float | None = None, bold: bool = False) -> None:
        nonlocal cursor
        effective_size = size or summary_font
        left_width = receipt_width - amount_width - 12
        canvas.text(x0, page_height - cursor, label, size=effective_size, bold=bold, align="right", width=left_width)
        canvas.text(x0 + left_width + 12, page_height - cursor, value, size=effective_size, bold=bold, align="right", width=amount_width)
        cursor += effective_size + 3

    def draw_meta(label: str, value: str) -> None:
        draw(f"{label}: {value}", size=meta_font)

    show_serial = show("show_item_serial")
    show_hsn = show("show_item_hsn")
    show_qty = show("show_item_qty", True)
    show_unit = show("show_item_unit")
    show_rate = show("show_item_rate", True)
    show_line_discount = show("show_line_discount")
    show_item_tax = show("show_item_tax")
    columns = _simple_receipt_columns(show_serial, show_hsn, show_qty, show_unit, show_rate)
    fixed_widths = _simple_receipt_column_widths(show_serial, show_hsn, show_qty, show_unit, show_rate)
    name_width = receipt_width - sum(fixed_widths.values())
    address_text = _joined_address(seller, seller_extra)
    address_lines = [line_text.strip() for line_text in address_text.split(", ") if line_text.strip()] if show("show_business_address", True) and address_text else []
    business_phone = _seller_phone(seller) or getattr(company_fallback, "phone", None)
    alternate_phone = _safe_text((seller_extra or {}).get("alternate_phone"), "")
    business_email = _safe_text((seller_extra or {}).get("email"), "")
    email_alt_line = " ".join(
        part
        for part in [
            f"@: {business_email}" if show("show_business_email") and business_email else "",
            alternate_phone if show("show_alternate_phone") and alternate_phone else "",
        ]
        if part
    )

    draw(_seller_name(seller).upper(), size=float(layout.get("business_name_size", 21)), bold=True, align="center")
    if show("show_store_code") and company_fallback:
        draw(str(getattr(company_fallback, "id", ""))[:4].upper(), size=17, bold=True, align="center")
    if address_lines or (show("show_business_phone", True) and business_phone):
        cursor += 3
    for wrapped in address_lines:
        draw(wrapped, size=body_font, align="center")
    if show("show_business_phone", True) and business_phone:
        draw(f"Phone Number: {business_phone}", size=body_font, align="center")
    if email_alt_line:
        draw(email_alt_line, size=body_font, align="center")
    if show("show_business_gstin"):
        gstin = getattr(seller, "gstin", None) or getattr(company_fallback, "gst_number", None)
        if gstin:
            draw(f"GSTIN: {gstin}", size=body_font, align="center")
    if show("show_business_pan"):
        business_pan = _safe_text((seller_extra or {}).get("pan"), "")
        if business_pan:
            draw(f"PAN: {business_pan}", size=body_font, align="center")
    if show("show_website"):
        website = _safe_text((seller_extra or {}).get("website"), "")
        if website:
            draw(website, size=body_font, align="center")
    cursor += 4
    if show("show_invoice_number", True):
        draw_meta("Bill No", str(getattr(invoice, "invoice_no", "") or "-"))
    if show("show_invoice_date", True) or show("show_invoice_time", True):
        draw_meta("Created On", _format_receipt_datetime(getattr(invoice, "invoice_date", None), show("show_invoice_date", True), show("show_invoice_time", True)))
    if show("show_customer_name", True):
        draw_meta("Bill To", _buyer_name(buyer))
    if show("show_customer_phone"):
        buyer_phone = _safe_text(getattr(buyer, "phone", None), "")
        if buyer_phone:
            draw_meta("Customer Phone", buyer_phone)
    if show("show_customer_gstin"):
        buyer_gstin = _safe_text(getattr(buyer, "gstin", None), "")
        if buyer_gstin:
            draw_meta("Customer GSTIN", buyer_gstin)
    if show("show_customer_address"):
        wrapped_address = _wrap_lines(_joined_address(buyer, buyer_extra), 44)
        for index, wrapped in enumerate(wrapped_address):
            if index == 0:
                draw_meta("Customer Address", wrapped)
            else:
                draw(wrapped, size=meta_font)
    if show("show_payment_mode") and getattr(invoice, "payment_mode", None):
        draw_meta("Payment", str(getattr(invoice, "payment_mode")).replace("_", " "))
    if show("show_payment_reference") and getattr(invoice, "payment_reference", None):
        draw_meta("Reference", str(getattr(invoice, "payment_reference")))
    cursor += 2
    line()
    x_positions: dict[str, tuple[float, float, str]] = {}
    current_x = x0
    for key, label, width, align in columns:
        col_width = float(width or name_width)
        x_positions[key] = (current_x, col_width, align)
        canvas.text(current_x, page_height - cursor, label, size=14.0, bold=True, align=align, width=col_width)
        current_x += col_width
    cursor += 17
    line()
    for index, line_item in enumerate(lines, start=1):
        details: list[str] = []
        if show_line_discount and float(getattr(line_item, "discount_percent", 0) or 0) > 0:
            details.append(f"Disc {float(getattr(line_item, 'discount_percent')):.0f}%")
        if show_item_tax and float(getattr(line_item, "tax_amount", 0) or 0) > 0:
            details.append(f"Tax Rs. {_receipt_money(getattr(line_item, 'tax_amount', 0))}")
        name_lines = _wrap_lines(
            _safe_text(getattr(line_item, "description", None), "-"),
            max(int(name_width / max(item_name_size * 0.56, 1.0)), 12),
        )
        if not multiline:
            name_lines = name_lines[:1]
        if details:
            detail_lines = _wrap_lines(" | ".join(details), max(int(name_width / max(item_name_size * 0.6, 1.0)), 12))
            if not multiline:
                detail_lines = detail_lines[:1]
            name_lines.extend(detail_lines)
        row_height = max(1, len(name_lines)) * (item_name_size + 2) + 2
        row_y = page_height - cursor
        if show_serial:
            serial_x, serial_width, _ = x_positions["serial"]
            canvas.text(serial_x, row_y, str(index), size=item_name_size, align="center", width=serial_width)
        name_x, _, _ = x_positions["name"]
        for line_index, wrapped in enumerate(name_lines):
            canvas.text(name_x, row_y - (line_index * (item_name_size + 2)), wrapped, size=item_name_size, align="left", width=name_width)
        if show_hsn:
            hsn_x, hsn_width, _ = x_positions["hsn"]
            canvas.text(hsn_x, row_y, _safe_text(getattr(line_item, "hsn", None), "-"), size=item_name_size, align="center", width=hsn_width)
        if show_qty:
            qty_x, qty_width, _ = x_positions["qty"]
            canvas.text(qty_x, row_y, _qty(getattr(line_item, "qty", 0)), size=item_name_size, align="center", width=qty_width)
        if show_unit:
            unit_x, unit_width, _ = x_positions["unit"]
            canvas.text(unit_x, row_y, _safe_text(getattr(line_item, "unit", None), "-"), size=item_name_size, align="center", width=unit_width)
        if show_rate:
            rate_x, rate_width, _ = x_positions["rate"]
            canvas.text(rate_x, row_y, _receipt_compact_money(getattr(line_item, "price", 0)), size=item_name_size, align="right", width=rate_width)
        total_x, total_width, _ = x_positions["total"]
        canvas.text(total_x, row_y, _receipt_compact_money(getattr(line_item, "line_total", 0)), size=item_name_size, align="right", width=total_width)
        cursor += row_height
    line()
    if show("show_total_items", True):
        draw_meta("Total Items", str(len(lines)))
    if show("show_total_quantity", True):
        draw_meta("Total Quantity", _qty(total_qty))
    line()
    if show("show_subtotal", True):
        draw_lr("Sub Total", _receipt_currency(getattr(invoice, "subtotal", 0), mode="ascii"), size=summary_font)
    cursor += 2
    canvas.line(x0, page_height - (cursor + 4), x0 + receipt_width, page_height - (cursor + 4))
    cursor += 14
    draw(f"Total {_receipt_currency(getattr(invoice, 'grand_total', 0), mode='ascii')}", size=total_font, bold=True, align="center")
    cursor += 2
    canvas.line(x0, page_height - (cursor + 4), x0 + receipt_width, page_height - (cursor + 4))
    cursor += 14
    if show("show_balance_due", True):
        draw_lr("Balance", _receipt_currency(getattr(invoice, "balance_due", 0), mode="ascii"), size=summary_font)
    if show("show_savings"):
        draw(f"Total Savings {_receipt_currency(_line_savings(lines), mode='ascii')}", size=saving_font, bold=True, align="center")
    if show("show_footer", True) and layout.get("footer_text"):
        line()
        draw(str(layout.get("footer_text")), align="center")
    if show("show_support_line") and layout.get("support_line"):
        draw(str(layout.get("support_line")), size=max(body_font - 1, 11), align="center")
    if show("show_qr_block") and layout.get("print_upi_qr") and upi_id:
        draw(f"UPI: {upi_id}", size=max(body_font - 1, 11), align="center")
    cursor += int(layout.get("bottom_padding_lines", 1)) * 6
    return canvas.build_pdf()


class _PdfCanvas:
    def __init__(self) -> None:
        self._commands: list[str] = []

    def rect(self, x: float, y: float, width: float, height: float, line_width: float = 0.8) -> None:
        self._commands.append(f"q {line_width:.2f} w {x:.2f} {y:.2f} {width:.2f} {height:.2f} re S Q")

    def line(self, x1: float, y1: float, x2: float, y2: float, line_width: float = 0.8) -> None:
        self._commands.append(f"q {line_width:.2f} w {x1:.2f} {y1:.2f} m {x2:.2f} {y2:.2f} l S Q")

    def text(
        self,
        x: float,
        y: float,
        text: str,
        *,
        size: float = 10.0,
        bold: bool = False,
        align: str = "left",
        width: float | None = None,
    ) -> None:
        safe_text = _latin1(_safe_text(text, ""))
        if width is not None:
            text_width = _text_width(safe_text, size)
            if align == "center":
                x = x + max((width - text_width) / 2, 0)
            elif align == "right":
                x = x + max(width - text_width, 0)
        font = "F2" if bold else "F1"
        self._commands.append(
            f"BT /{font} {size:.2f} Tf 1 0 0 1 {x:.2f} {y:.2f} Tm ({_pdf_escape(safe_text)}) Tj ET"
        )

    def build_pdf(self) -> bytes:
        content = "\n".join(self._commands).encode("latin-1")
        objects: list[bytes | None] = [None]
        objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
        objects.append(b"<< /Type /Pages /Kids [6 0 R] /Count 1 >>")
        objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
        objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>")
        objects.append(f"<< /Length {len(content)} >>\nstream\n".encode("latin-1") + content + b"\nendstream")
        objects.append(
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> /Contents 5 0 R >>"
        )

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


def _metadata_pairs(invoice: Any, settings: dict[str, Any] | None = None) -> list[tuple[str, str]]:
    meta = _meta(invoice)
    visibility = _tax_invoice_visibility(settings, invoice)

    def show(key: str, fallback: bool = True) -> bool:
        value = visibility.get(key)
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() == "true"
        return fallback

    pairs: list[tuple[str, str]] = []
    if show("show_invoice_number", True):
        pairs.append(("Invoice No.", _safe_text(getattr(invoice, "invoice_no", None), "-")))
    if show("show_invoice_date", True):
        pairs.append(("Dated", _format_datetime(getattr(invoice, "invoice_date", None))))
    if show("show_gst_meta_delivery_note", True):
        pairs.append(("Delivery Note", _safe_text(meta.get("delivery_note"), "-")))
    if show("show_gst_meta_payment_terms", True):
        pairs.append(("Mode/Terms of Payment", _safe_text(meta.get("payment_terms"), "-")))
    if show("show_gst_meta_reference", True):
        pairs.append(("Reference No. & Date", _join_values(meta.get("reference_no"), meta.get("reference_date")) or "-"))
    if show("show_gst_meta_other_references", True):
        pairs.append(("Other References", _safe_text(meta.get("other_references"), "-")))
    if show("show_gst_meta_buyer_order_no", True):
        pairs.append(("Buyer's Order No.", _safe_text(meta.get("buyer_order_no"), "-")))
    if show("show_gst_meta_buyer_order_date", True):
        pairs.append(("Buyer's Order Date", _safe_text(meta.get("buyer_order_date"), "-")))
    if show("show_gst_meta_dispatch_doc_no", True):
        pairs.append(("Dispatch Doc No.", _safe_text(meta.get("dispatch_doc_no"), "-")))
    if show("show_gst_meta_delivery_note_date", True):
        pairs.append(("Delivery Note Date", _safe_text(meta.get("delivery_note_date"), "-")))
    if show("show_gst_meta_dispatched_through", True):
        pairs.append(("Dispatched through", _safe_text(meta.get("dispatched_through"), "-")))
    if show("show_gst_meta_destination", True):
        pairs.append(("Destination", _safe_text(meta.get("destination"), "-")))
    if show("show_gst_meta_bill_of_lading_no", True):
        pairs.append(("Bill of Lading / LR-RR No.", _safe_text(meta.get("bill_of_lading_no"), "-")))
    if show("show_gst_meta_motor_vehicle_no", True):
        pairs.append(("Motor Vehicle No.", _safe_text(meta.get("motor_vehicle_no"), "-")))
    if show("show_gst_meta_terms_of_delivery", True):
        pairs.append(("Terms of Delivery", _safe_text(meta.get("terms_of_delivery"), "-")))
    if show("show_gst_meta_place_of_supply", True):
        pairs.append(("Place of Supply", _safe_text(getattr(invoice, "place_of_supply", None) or meta.get("place_of_supply"), "-")))
    if show("show_gst_meta_eway_bill_no", True):
        pairs.append(("E-Way Bill No.", _safe_text(meta.get("eway_bill_no"), "-")))
    return pairs or [("Invoice No.", _safe_text(getattr(invoice, "invoice_no", None), "-"))]


def _tax_invoice_visibility(settings: dict[str, Any] | None, invoice: Any) -> dict[str, Any]:
    if isinstance(settings, dict):
        visibility = settings.get("visibility")
        if isinstance(visibility, dict):
            return visibility
    seller = getattr(invoice, "company", None)
    seller_extra = _extra(seller)
    receipt_settings = seller_extra.get("receipt_settings") if isinstance(seller_extra, dict) else None
    if isinstance(receipt_settings, dict) and isinstance(receipt_settings.get("visibility"), dict):
        return receipt_settings["visibility"]
    return {}


def _h(value: Any) -> str:
    return escape(_safe_text(value, ""))


def _optional_line(value: str | None) -> str:
    if not value:
        return ""
    return f"<div>{_h(value)}</div>"


def _safe_text(value: Any, fallback: str = "") -> str:
    if value is None:
        return fallback
    text = str(value).strip()
    return text if text else fallback


def _join_values(*values: Any) -> str:
    return " ".join(str(value).strip() for value in values if value is not None and str(value).strip())


def _joined_address(entity: Any, extra: dict[str, Any]) -> str:
    parts = [
        extra.get("address_line1") or getattr(entity, "address", None),
        extra.get("address_line2"),
        extra.get("city") or getattr(entity, "city", None),
        extra.get("district"),
        extra.get("state") or getattr(entity, "state", None),
        extra.get("pincode") or getattr(entity, "pincode", None),
        extra.get("country"),
    ]
    return ", ".join(str(part).strip() for part in parts if part is not None and str(part).strip())


def _seller_name(seller: Any) -> str:
    if seller is None:
        return "Company"
    return _safe_text(getattr(seller, "business_name", None) or getattr(seller, "name", None), "Company")


def _seller_legal_name(seller: Any) -> str | None:
    extra = _extra(seller)
    business_name = _safe_text(getattr(seller, "business_name", None), "")
    legal_name = _safe_text(extra.get("legal_name"), "")
    return legal_name if legal_name and legal_name != business_name else None


def _buyer_name(buyer: Any) -> str:
    if buyer is None:
        return "CASH SALE"
    return _safe_text(getattr(buyer, "business_name", None) or getattr(buyer, "name", None), "CASH SALE")


def _buyer_legal_name(buyer: Any) -> str | None:
    extra = _extra(buyer)
    business_name = _safe_text(getattr(buyer, "business_name", None), "")
    legal_name = _safe_text(extra.get("legal_name"), "")
    name = _safe_text(getattr(buyer, "name", None), "")
    return legal_name or (name if name and name != business_name else None)


def _buyer_pan(buyer: Any, extra: dict[str, Any]) -> str | None:
    return _safe_text(getattr(buyer, "pan", None) or extra.get("pan"), "")


def _seller_state(seller: Any, extra: dict[str, Any]) -> str | None:
    return _safe_text(getattr(seller, "state", None) or extra.get("state"), "")


def _buyer_state(buyer: Any, extra: dict[str, Any]) -> str | None:
    return _safe_text(getattr(buyer, "state", None) or extra.get("state"), "")


def _seller_state_code(seller: Any, extra: dict[str, Any]) -> str | None:
    return _safe_text(extra.get("state_code"), "")


def _buyer_state_code(buyer: Any, extra: dict[str, Any]) -> str | None:
    return _safe_text(getattr(buyer, "state_code", None) or extra.get("state_code"), "")


def _seller_phone(seller: Any) -> str | None:
    extra = _extra(seller)
    return _safe_text(getattr(seller, "phone", None) or extra.get("alt_phone"), "")


def _extra(entity: Any) -> dict[str, Any]:
    data = getattr(entity, "extra_data", None)
    return dict(data or {}) if isinstance(data, dict) else {}


def _meta(invoice: Any) -> dict[str, Any]:
    data = getattr(invoice, "invoice_meta", None)
    return dict(data or {}) if isinstance(data, dict) else {}


def _money(value: Any) -> str:
    amount = float(value or 0)
    return f"{amount:.2f}"


def _qty(value: Any) -> str:
    amount = float(value or 0)
    if abs(amount - round(amount)) < 0.0001:
        return str(int(round(amount)))
    return f"{amount:.3f}".rstrip("0").rstrip(".")


def _percent(value: Any) -> str:
    if value is None or value == "":
        return "-"
    return f"{float(value):.2f}%"


def _format_datetime(value: Any) -> str:
    if value is None:
        return "-"
    if hasattr(value, "strftime"):
        return value.strftime("%d-%m-%Y")
    text = str(value).strip()
    return text[:10] if text else "-"


def _wrap_lines(text: str, max_chars: int) -> list[str]:
    clean = _latin1(_safe_text(text, ""))
    if not clean:
        return [""]
    words = clean.split()
    lines: list[str] = []
    current = ""
    for word in words:
        proposal = f"{current} {word}".strip()
        if len(proposal) <= max_chars:
            current = proposal
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines or [clean[:max_chars]]


def _latin1(value: str) -> str:
    return value.encode("latin-1", "replace").decode("latin-1")


def _pdf_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _text_width(text: str, size: float) -> float:
    return len(text) * size * 0.50


def _round_off(invoice: Any) -> float:
    subtotal = float(getattr(invoice, "subtotal", 0) or 0)
    tax_total = float(getattr(invoice, "tax_total", 0) or 0)
    grand_total = float(getattr(invoice, "grand_total", 0) or 0)
    return round(grand_total - subtotal - tax_total, 2)


def _ordered_lines(lines: list[Any], item_order_mode: Any) -> list[Any]:
    ordered = list(lines)
    if str(item_order_mode or "").strip().lower() == "alphabetical":
        ordered.sort(key=lambda row: _safe_text(getattr(row, "description", None), "").lower())
    return ordered


def _currency_with_symbol(value: Any) -> str:
    return f"\u20b9 {_money(value)}"


def _receipt_money(value: Any) -> str:
    return f"{float(value or 0):,.2f}"


def _receipt_currency(value: Any, *, mode: str = "unicode", include_space: bool = True) -> str:
    prefix = "₹" if mode == "unicode" else "Rs."
    spacer = " " if include_space else ""
    return f"{prefix}{spacer}{_receipt_money(value)}"


def _receipt_compact_money(value: Any) -> str:
    amount = float(value or 0)
    if abs(amount - round(amount)) < 0.0001:
        return f"{int(round(amount)):,}"
    return f"{amount:,.2f}"


def _simple_receipt_metrics(line: Any, show_qty: bool, show_unit: bool, show_rate: bool) -> str:
    bits: list[str] = []
    if show_qty:
        qty_text = _qty(getattr(line, "qty", 0))
        if show_unit and getattr(line, "unit", None):
            qty_text = f"{qty_text} {getattr(line, 'unit')}"
        bits.append(qty_text)
    if show_rate:
        bits.append(f"x {_receipt_money(getattr(line, 'price', 0))}")
    return " ".join(bit for bit in bits if bit).strip()


def _simple_receipt_colspan(show_serial: bool, show_hsn: bool, show_qty: bool, show_unit: bool, show_rate: bool) -> int:
    count = 2
    if show_serial:
        count += 1
    if show_hsn:
        count += 1
    if show_qty:
        count += 1
    if show_unit:
        count += 1
    if show_rate:
        count += 1
    return count


def _simple_receipt_columns(show_serial: bool, show_hsn: bool, show_qty: bool, show_unit: bool, show_rate: bool) -> list[tuple[str, str, int | None, str]]:
    columns: list[tuple[str, str, int | None, str]] = []
    if show_serial:
        columns.append(("serial", "#", 24, "center"))
    columns.append(("name", "Item Name", None, "left"))
    if show_hsn:
        columns.append(("hsn", "HSN", 54, "center"))
    if show_qty:
        columns.append(("qty", "Qty", 42, "center"))
    if show_unit:
        columns.append(("unit", "Unit", 44, "center"))
    if show_rate:
        columns.append(("rate", "Rate", 60, "right"))
    columns.append(("total", "Total", 74, "right"))
    return columns


def _simple_receipt_column_widths(show_serial: bool, show_hsn: bool, show_qty: bool, show_unit: bool, show_rate: bool) -> dict[str, int]:
    return {
        key: int(width or 0)
        for key, _, width, _ in _simple_receipt_columns(show_serial, show_hsn, show_qty, show_unit, show_rate)
        if width is not None
    }


def _simple_receipt_grid_template(show_serial: bool, show_hsn: bool, show_qty: bool, show_unit: bool, show_rate: bool) -> str:
    parts = [f"{width}px" if width is not None else "minmax(0,1fr)" for _, _, width, _ in _simple_receipt_columns(show_serial, show_hsn, show_qty, show_unit, show_rate)]
    return " ".join(parts)


def _simple_receipt_detail_html(line: Any, show_hsn: bool, show_line_discount: bool, show_item_tax: bool) -> str:
    details: list[str] = []
    if show_hsn and getattr(line, "hsn", None):
        details.append(f"HSN {_h(getattr(line, 'hsn'))}")
    if show_line_discount and float(getattr(line, "discount_percent", 0) or 0) > 0:
        details.append(f"Disc {float(getattr(line, 'discount_percent')):.0f}%")
    if show_item_tax and float(getattr(line, "tax_amount", 0) or 0) > 0:
        details.append(f"Tax {_receipt_money(getattr(line, 'tax_amount', 0))}")
    if not details:
        return ""
    return f"<div class='item-detail'>{' | '.join(details)}</div>"


def _simple_receipt_html_row(
    *,
    index: int,
    line: Any,
    show_serial: bool,
    show_hsn: bool,
    show_qty: bool,
    show_unit: bool,
    show_rate: bool,
    show_line_discount: bool,
    show_item_tax: bool,
    multiline: bool,
    item_name_size: int,
) -> str:
    details: list[str] = []
    if show_line_discount and float(getattr(line, "discount_percent", 0) or 0) > 0:
        details.append(f"Disc {float(getattr(line, 'discount_percent')):.0f}%")
    if show_item_tax and float(getattr(line, "tax_amount", 0) or 0) > 0:
        details.append(f"Tax {_receipt_currency(getattr(line, 'tax_amount', 0), mode='unicode')}")
    name_html = _h(getattr(line, "description", "") or "-")
    if details:
        detail_text = " | ".join(details)
        name_html = f"{name_html}<span class=\"item-detail\">{_h(detail_text)}</span>"
    line_clamp = ""
    if not multiline:
        line_clamp = "white-space:nowrap;overflow:hidden;text-overflow:ellipsis;"
    cells: list[str] = []
    if show_serial:
        cells.append(f"<div style=\"text-align:center;font-size:{item_name_size}px\">{index}</div>")
    cells.append(f"<div class=\"item-name\" style=\"font-size:{item_name_size}px;{line_clamp}\">{name_html}</div>")
    if show_hsn:
        cells.append(f"<div style=\"text-align:center;font-size:{item_name_size}px\">{_h(getattr(line, 'hsn', None) or '-')}</div>")
    if show_qty:
        cells.append(f"<div style=\"text-align:center;font-size:{item_name_size}px\">{_h(_qty(getattr(line, 'qty', 0)))}</div>")
    if show_unit:
        cells.append(f"<div style=\"text-align:center;font-size:{item_name_size}px\">{_h(getattr(line, 'unit', None) or '-')}</div>")
    if show_rate:
        cells.append(f"<div style=\"text-align:right;font-size:{item_name_size}px\">{_h(_receipt_compact_money(getattr(line, 'price', 0)))}</div>")
    cells.append(f"<div style=\"text-align:right;font-size:{item_name_size}px\">{_h(_receipt_compact_money(getattr(line, 'line_total', 0)))}</div>")
    return f"<div class=\"item-row\">{''.join(cells)}</div>"


def _format_receipt_datetime(value: Any, show_date: bool, show_time: bool) -> str:
    if value is None:
        return "-"
    parsed = value if hasattr(value, "strftime") else None
    if parsed is None:
        from datetime import datetime
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except Exception:
            return _safe_text(value, "-")
    if show_date and show_time:
        return parsed.strftime("%d/%m/%y %I:%M %p")
    if show_date:
        return parsed.strftime("%d/%m/%y")
    if show_time:
        return parsed.strftime("%I:%M %p")
    return "-"


def _line_savings(lines: list[Any]) -> float:
    total = 0.0
    for line in lines:
        qty = float(getattr(line, "qty", 0) or 0)
        price = float(getattr(line, "price", 0) or 0)
        line_total = float(getattr(line, "line_total", 0) or 0)
        total += max((qty * price) - line_total, 0)
    return round(total, 2)
