from __future__ import annotations

from copy import deepcopy
from typing import Any

from app.db.models import CompanyProfile


DEFAULT_RECEIPT_SETTINGS: dict[str, Any] = {
    "printer": {
        "primary_printer_enabled": True,
        "primary_printer_type": "bluetooth",
        "secondary_printer_enabled": False,
        "secondary_printer_type": "usb",
        "characters_per_line": 32,
        "col2_characters": 6,
        "col3_characters": 8,
        "col4_characters": 8,
        "dots_per_line": 384,
        "test_print_enabled": True,
    },
    "layout": {
        "auto_print_sale": False,
        "print_logo": False,
        "print_upi_qr": False,
        "print_google_review_qr": False,
        "gst_print_mode": "amount_only",
        "print_tax_mrp_hsn": False,
        "print_regional_language": False,
        "regional_language_font_size": 11,
        "pdf_font_size": 11,
        "footer_text": "Thank you for your business.",
        "support_line": "",
        "spacing_fix_enabled": False,
        "bottom_padding_lines": 1,
        "print_item_multiline": True,
        "print_bill_created_info": False,
        "item_order_mode": "selection_order",
        "business_name_size": 21,
        "total_amount_size": 24,
        "saving_amount_size": 15,
        "item_name_size": 13,
    },
    "visibility": {
        "show_business_name": True,
        "show_legal_business_name": False,
        "show_branch_store_name": False,
        "show_business_address": True,
        "show_business_phone": True,
        "show_alternate_phone": True,
        "show_business_email": False,
        "show_business_gstin": False,
        "show_business_pan": False,
        "show_store_code": True,
        "show_website": False,
        "show_invoice_number": True,
        "show_invoice_date": True,
        "show_invoice_time": True,
        "show_created_by": False,
        "show_customer_name": True,
        "show_customer_phone": False,
        "show_customer_gstin": False,
        "show_customer_address": False,
        "show_payment_mode": False,
        "show_payment_reference": False,
        "show_gst_meta_delivery_note": True,
        "show_gst_meta_payment_terms": True,
        "show_gst_meta_reference": True,
        "show_gst_meta_other_references": True,
        "show_gst_meta_buyer_order_no": True,
        "show_gst_meta_buyer_order_date": True,
        "show_gst_meta_dispatch_doc_no": True,
        "show_gst_meta_delivery_note_date": True,
        "show_gst_meta_dispatched_through": True,
        "show_gst_meta_destination": True,
        "show_gst_meta_bill_of_lading_no": True,
        "show_gst_meta_motor_vehicle_no": True,
        "show_gst_meta_terms_of_delivery": True,
        "show_gst_meta_place_of_supply": True,
        "show_gst_meta_eway_bill_no": True,
        "show_due_balance": True,
        "show_round_off": False,
        "show_discount": False,
        "show_savings": True,
        "show_notes": False,
        "show_item_serial": False,
        "show_item_code": False,
        "show_item_hsn": False,
        "show_item_qty": True,
        "show_item_rate": True,
        "show_item_tax": False,
        "show_item_mrp": False,
        "show_item_unit": False,
        "show_line_discount": False,
        "show_total_items": True,
        "show_total_quantity": True,
        "show_subtotal": True,
        "show_taxable_amount": False,
        "show_tax_breakup": False,
        "show_total_tax": False,
        "show_paid_amount": False,
        "show_balance_due": True,
        "show_footer": True,
        "show_qr_block": False,
        "show_support_line": False,
    },
}

_PRINTER_TYPES = {"bluetooth", "usb"}
_GST_PRINT_MODES = {"no_gst", "amount_only", "percentage_only", "both"}
_ITEM_ORDER_MODES = {"selection_order", "alphabetical"}

_MANDATORY_VISIBILITY = {
    "show_business_name",
    "show_invoice_number",
    "show_invoice_date",
    "show_customer_name",
    "show_item_qty",
    "show_item_rate",
    "show_subtotal",
    "show_total_items",
    "show_total_quantity",
    "show_balance_due",
}


def get_receipt_settings(profile: CompanyProfile | None) -> dict[str, Any]:
    defaults = deepcopy(DEFAULT_RECEIPT_SETTINGS)
    if not profile or not profile.extra_json:
        return defaults
    raw = profile.extra_json.get("receipt_settings")
    if not isinstance(raw, dict):
        return defaults
    return sanitize_receipt_settings(raw)


def set_receipt_settings(profile: CompanyProfile, incoming: dict[str, Any]) -> dict[str, Any]:
    current = get_receipt_settings(profile)
    merged = _merge_nested(current, incoming)
    sanitized = sanitize_receipt_settings(merged)
    extra = dict(profile.extra_json or {})
    extra["receipt_settings"] = sanitized
    profile.extra_json = extra
    return sanitized


def reset_receipt_settings(profile: CompanyProfile) -> dict[str, Any]:
    defaults = deepcopy(DEFAULT_RECEIPT_SETTINGS)
    extra = dict(profile.extra_json or {})
    extra["receipt_settings"] = defaults
    profile.extra_json = extra
    return defaults


def sanitize_receipt_settings(raw: dict[str, Any]) -> dict[str, Any]:
    merged = _merge_nested(deepcopy(DEFAULT_RECEIPT_SETTINGS), raw)
    printer = merged["printer"]
    layout = merged["layout"]
    visibility = merged["visibility"]

    printer["primary_printer_enabled"] = bool(printer.get("primary_printer_enabled"))
    printer["secondary_printer_enabled"] = bool(printer.get("secondary_printer_enabled"))
    printer["test_print_enabled"] = bool(printer.get("test_print_enabled"))
    printer["primary_printer_type"] = _choice(printer.get("primary_printer_type"), _PRINTER_TYPES, "bluetooth")
    printer["secondary_printer_type"] = _choice(printer.get("secondary_printer_type"), _PRINTER_TYPES, "usb")
    printer["characters_per_line"] = _int_range(printer.get("characters_per_line"), 24, 64, 32)
    printer["col2_characters"] = _int_range(printer.get("col2_characters"), 4, 24, 6)
    printer["col3_characters"] = _int_range(printer.get("col3_characters"), 4, 24, 8)
    printer["col4_characters"] = _int_range(printer.get("col4_characters"), 4, 24, 8)
    printer["dots_per_line"] = _int_range(printer.get("dots_per_line"), 200, 800, 384)

    layout["auto_print_sale"] = bool(layout.get("auto_print_sale"))
    layout["print_logo"] = bool(layout.get("print_logo"))
    layout["print_upi_qr"] = bool(layout.get("print_upi_qr"))
    layout["print_google_review_qr"] = bool(layout.get("print_google_review_qr"))
    layout["print_tax_mrp_hsn"] = bool(layout.get("print_tax_mrp_hsn"))
    layout["print_regional_language"] = bool(layout.get("print_regional_language"))
    layout["spacing_fix_enabled"] = bool(layout.get("spacing_fix_enabled"))
    layout["print_item_multiline"] = bool(layout.get("print_item_multiline"))
    layout["print_bill_created_info"] = bool(layout.get("print_bill_created_info"))
    layout["gst_print_mode"] = _choice(layout.get("gst_print_mode"), _GST_PRINT_MODES, "amount_only")
    layout["item_order_mode"] = _choice(layout.get("item_order_mode"), _ITEM_ORDER_MODES, "selection_order")
    layout["regional_language_font_size"] = _int_range(layout.get("regional_language_font_size"), 8, 20, 11)
    layout["pdf_font_size"] = _int_range(layout.get("pdf_font_size"), 8, 16, 11)
    layout["bottom_padding_lines"] = _int_range(layout.get("bottom_padding_lines"), 0, 10, 1)
    layout["business_name_size"] = _int_range(layout.get("business_name_size"), 14, 30, 21)
    layout["total_amount_size"] = _int_range(layout.get("total_amount_size"), 18, 34, 24)
    layout["saving_amount_size"] = _int_range(layout.get("saving_amount_size"), 10, 22, 15)
    layout["item_name_size"] = _int_range(layout.get("item_name_size"), 10, 18, 13)
    layout["footer_text"] = _string(layout.get("footer_text"), max_len=240, default="Thank you for your business.")
    layout["support_line"] = _string(layout.get("support_line"), max_len=120, default="")

    for key, value in list(visibility.items()):
        visibility[key] = bool(value)
    for key in _MANDATORY_VISIBILITY:
        visibility[key] = True
    if layout["print_logo"] or layout["print_upi_qr"] or layout["print_google_review_qr"]:
        visibility["show_qr_block"] = True

    return merged


def _merge_nested(base: dict[str, Any], incoming: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(incoming, dict):
        return base
    for key, value in incoming.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            base[key] = _merge_nested(dict(base[key]), value)
        else:
            base[key] = value
    return base


def _int_range(value: Any, low: int, high: int, default: int) -> int:
    try:
        parsed = int(value)
    except Exception:
        parsed = default
    return max(low, min(high, parsed))


def _choice(value: Any, allowed: set[str], default: str) -> str:
    text = str(value or "").strip().lower()
    return text if text in allowed else default


def _string(value: Any, *, max_len: int, default: str) -> str:
    text = str(value or "").strip()
    if not text:
        return default
    return text[:max_len]
