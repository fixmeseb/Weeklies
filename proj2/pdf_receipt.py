# pdf_receipt.py
import json
from io import BytesIO
from datetime import datetime

from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas
from reportlab.lib import colors

from proj2.sqlQueries import create_connection, close_connection, fetch_one


def _safe_str(x):
    """
    Safely convert a value to string, avoiding None.
    Args:
        x (Any): The input value to convert.
    Returns:
        str: Empty string if None, otherwise stringified value.
    """
    return "" if x is None else str(x)


def _money(x):
    """
    Format a numeric value as a currency string.
    Args:
        x (float | int | str): The numeric amount to format.
    Returns:
        str: The value formatted as a dollar amount (e.g., "$12.34"), or empty string on failure.
    """
    try:
        return f"${float(x):.2f}"
    except Exception:
        return ""


def _dt_display(iso_str):
    """
    Format an ISO timestamp string into a readable form.
    Args:
        iso_str (str): ISO 8601 datetime string.
    Returns:
        str: A formatted timestamp 'YYYY-MM-DD HH:MM' or the original string if invalid.
    """
    if not iso_str:
        return ""
    try:
        return datetime.fromisoformat(iso_str).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return iso_str


def generate_order_receipt_pdf(db_file: str, ord_id: int) -> bytes:
    """
    Generate a PDF receipt for a given order.
    Args:
        db_file (str): Path to the SQLite database file.
        ord_id (int): Order ID for which to generate the receipt.
    Returns:
        bytes: The binary PDF data as a bytes object.
    """
    conn = create_connection(db_file)
    try:
        # Order: ord_id,rtr_id,usr_id,details,status
        orow = fetch_one(
            conn,
            'SELECT ord_id, rtr_id, usr_id, details, status FROM "Order" WHERE ord_id = ?',
            (ord_id,),
        )
        if not orow:
            raise ValueError("Order not found")

        ord_id, rtr_id, usr_id, details, status = orow

        # User
        urow = fetch_one(
            conn,
            'SELECT first_name, last_name, email, phone FROM "User" WHERE usr_id = ?',
            (usr_id,),
        )
        first_name, last_name, email, phone = urow or ("", "", "", "")

        # Restaurant
        rrow = fetch_one(
            conn,
            'SELECT name, address, city, state, zip, phone FROM "Restaurant" WHERE rtr_id = ?',
            (rtr_id,),
        )
        r_name, r_addr, r_city, r_state, r_zip, r_phone = rrow or ("", "", "", "", "", "")

        # Parse details JSON (new format)
        j = {}
        try:
            j = json.loads(details or "{}")
        except Exception:
            j = {}

        placed_at = _dt_display(j.get("placed_at") or j.get("time"))
        delivery_type = _safe_str(j.get("delivery_type"))
        deliver_to = _safe_str(j.get("deliver_to"))
        due_at = _safe_str(j.get("due_at")).replace("T", " ") if not j.get("asap") else ""
        notes = _safe_str(j.get("notes"))

        items = j.get("items") or []
        charges = j.get("charges") or {}
        subtotal = charges.get("subtotal")
        tax = charges.get("tax")
        delivery_fee = charges.get("delivery_fee")
        service_fee = charges.get("service_fee")
        tip = charges.get("tip")
        total = charges.get("total") or charges.get("grand_total") or charges.get("amount")

        # --------- Build PDF ----------
        buf = BytesIO()
        c = canvas.Canvas(buf, pagesize=letter)
        width, height = letter
        margin = 0.75 * inch
        y = height - margin

        # Header
        c.setFont("Helvetica-Bold", 16)
        c.drawString(margin, y, f"Receipt · Order #{ord_id}")

        # Status badge with color coding
        c.setFont("Helvetica-Bold", 11)
        status_str = _safe_str(status).upper()

        # Set color based on status
        if status_str == "CANCELLED":
            c.setFillColor(colors.red)
        elif status_str == "DELIVERED":
            c.setFillColor(colors.green)
        elif status_str in ["PREPARING", "READY"]:
            c.setFillColor(colors.orange)
        elif status_str == "ACCEPTED":
            c.setFillColor(colors.blue)
        else:
            c.setFillColor(colors.grey)

        c.drawString(margin, y - 14, f"Status: {status_str}")

        # Placed date
        c.setFillColor(colors.grey)
        c.setFont("Helvetica", 10)
        c.drawRightString(width - margin, y - 14, f"Placed: {placed_at}")
        c.setFillColor(colors.black)
        y -= 30

        # Parties
        c.setFont("Helvetica-Bold", 12)
        c.drawString(margin, y, "Billed To")
        c.setFont("Helvetica", 10)
        c.drawString(margin, y - 14, f"{_safe_str(first_name)} {_safe_str(last_name)}")
        c.drawString(margin, y - 28, f"Email: {_safe_str(email)}")
        c.drawString(margin, y - 42, f"Phone: {_safe_str(phone)}")

        c.setFont("Helvetica-Bold", 12)
        c.drawRightString(width - margin, y, "Restaurant")
        c.setFont("Helvetica", 10)
        c.drawRightString(width - margin, y - 14, _safe_str(r_name))
        c.drawRightString(width - margin, y - 28, f"{_safe_str(r_addr)}")
        c.drawRightString(
            width - margin, y - 42, f"{_safe_str(r_city)}, {_safe_str(r_state)} {_safe_str(r_zip)}"
        )
        c.drawRightString(width - margin, y - 56, f"Phone: {_safe_str(r_phone)}")

        y -= 78

        # Add prominent notice for cancelled orders
        if status_str == "CANCELLED":
            # Draw a red box with cancellation notice
            c.setStrokeColor(colors.red)
            c.setFillColor(colors.Color(1, 0.95, 0.95))  # Light red background
            c.rect(margin, y - 40, width - 2 * margin, 35, stroke=1, fill=1)

            c.setFillColor(colors.red)
            c.setFont("Helvetica-Bold", 12)
            c.drawCentredString(width / 2, y - 15, "⚠ ORDER CANCELLED ⚠")
            c.setFont("Helvetica", 10)
            c.drawCentredString(width / 2, y - 30, "This order was cancelled by the restaurant")
            c.setFillColor(colors.black)
            y -= 55

        # Divider
        c.setStrokeColor(colors.lightgrey)
        c.line(margin, y, width - margin, y)
        y -= 16

        # Items table header
        c.setFont("Helvetica-Bold", 11)
        c.drawString(margin, y, "Qty")
        c.drawString(margin + 40, y, "Item")
        c.drawRightString(width - margin - 140, y, "Unit")
        c.drawRightString(width - margin, y, "Line")
        y -= 12
        c.setStrokeColor(colors.lightgrey)
        c.line(margin, y, width - margin, y)
        y -= 10
        c.setFont("Helvetica", 10)

        # Items rows
        for it in items:
            qty = _safe_str(it.get("qty"))
            name = _safe_str(it.get("name"))
            unit = _money(it.get("unit_price"))
            line = _money(it.get("line_total"))

            c.drawString(margin, y, qty)
            c.drawString(margin + 40, y, name[:60])
            c.drawRightString(width - margin - 140, y, unit)
            c.drawRightString(width - margin, y, line)
            y -= 14
            if y < 1.25 * inch:
                c.showPage()
                y = height - margin
                c.setFont("Helvetica", 10)

        # Divider
        y -= 6
        c.setStrokeColor(colors.lightgrey)
        c.line(margin, y, width - margin, y)
        y -= 12

        # Charges
        c.setFont("Helvetica", 10)

        def row(label, value):
            """
            Draw a label-value row for a charge line.
            Args:
                label (str): Description of the charge (e.g., 'Tax', 'Subtotal').
                value (float): Amount associated with the charge.
            Returns:
                None
            """
            nonlocal y
            if value is None or value == "":
                return
            c.drawRightString(width - margin - 140, y, label)
            c.drawRightString(width - margin, y, _money(value))
            y -= 14

        row("Subtotal", subtotal)
        row("Tax", tax)
        row("Delivery fee", delivery_fee)
        row("Service fee", service_fee)
        row("Tip", tip)

        c.setFont("Helvetica-Bold", 11)
        c.drawRightString(width - margin - 140, y, "Total")
        c.drawRightString(width - margin, y, _money(total))
        y -= 18

        # Footer notes
        c.setFont("Helvetica", 9)
        if delivery_type:
            c.drawString(margin, y, f"Delivery type: {delivery_type}")
            y -= 12
        if deliver_to:
            c.drawString(margin, y, f"Deliver to: {deliver_to[:110]}")
            y -= 12
        if due_at:
            c.drawString(margin, y, f"For: {due_at}")
            y -= 12
        if notes:
            c.drawString(margin, y, f"Notes: {notes[:120]}")
            y -= 12

        c.setFillColor(colors.grey)
        c.drawString(margin, 0.6 * inch, "Thank you for your order!")
        c.setFillColor(colors.black)

        c.showPage()
        c.save()
        pdf_bytes = buf.getvalue()
        buf.close()
        return pdf_bytes

    finally:
        close_connection(conn)
