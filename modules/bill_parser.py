"""
Parse Eskom (and similar) electricity bills from PDF.
Extracts: billing period, kWh by band, charges, and per-kWh rate components.
"""
import pdfplumber
import re

def parse_bill(pdf_path):
    text = ""
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text += (page.extract_text() or "") + "\n"

    result = {
        "period_from": None,
        "period_to": None,
        "account_month": None,
        "customer_name": None,
        "bill_kwh_total": 0.0,
        "bill_kwh_peak": 0.0,
        "bill_kwh_std": 0.0,
        "bill_kwh_off": 0.0,
        "bill_excl_vat": 0.0,
        "bill_incl_vat": 0.0,
        "vat_amount": 0.0,
        "rate_components": [],  # list of {name, rate, applies_to}
        "std_rate_weighted": 0.0,
        "combined_rate": 0.0,
    }

    # ── Billing period ──────────────────────────────────────
    period = re.search(r'CONSUMPTION DETAILS\s*\((\d{4}-\d{2}-\d{2})\s*-\s*(\d{4}-\d{2}-\d{2})\)', text)
    if period:
        result["period_from"] = period.group(1)
        result["period_to"] = period.group(2)

    # Account month fallback
    month = re.search(r'ACCOUNT\s+M\s*ONTH\s+([A-Z]+\s+\d{4})', text)
    if month:
        result["account_month"] = month.group(1)

    # ── Customer name ────────────────────────────────────────
    name = re.search(r'NAME\s*\n([A-Z][A-Z &]+)', text)
    if name:
        result["customer_name"] = name.group(1).strip()

    # ── kWh consumption ──────────────────────────────────────
    total = re.search(r'ENERGY CONSUMPTION ALL\s+kWh?\s+([\d,]+\.?\d*)', text)
    if total:
        result["bill_kwh_total"] = float(total.group(1).replace(',', ''))

    peak = re.search(r'ENERGY CONSUMPTION PEAK\s+kWh?\s+([\d,]+\.?\d*)', text)
    if peak:
        result["bill_kwh_peak"] = float(peak.group(1).replace(',', ''))

    std = re.search(r'ENERGY CONSUMPTION STD\s+kWh?\s+([\d,]+\.?\d*)', text)
    if std:
        result["bill_kwh_std"] = float(std.group(1).replace(',', ''))

    off = re.search(r'ENERGY CONSUMPTION OFF PEAK\s+kWH?\s+([\d,]+\.?\d*)', text)
    if off:
        result["bill_kwh_off"] = float(off.group(1).replace(',', ''))

    # ── Financial totals ─────────────────────────────────────
    charges = re.search(r'TOTAL CHARGES FOR BILLING PERIOD\s+R\s+([\d,]+\.?\d*)', text)
    if charges:
        result["bill_excl_vat"] = float(charges.group(1).replace(',', ''))

    vat = re.search(r'VAT RAISED ON ITEMS AT \d+%\s+R\s+([\d,]+\.?\d*)', text)
    if vat:
        result["vat_amount"] = float(vat.group(1).replace(',', ''))

    total_due = re.search(r'TOTAL AMOUNT DUE\s+([\d,]+\.?\d*)', text)
    if total_due:
        result["bill_incl_vat"] = float(total_due.group(1).replace(',', ''))
    elif result["bill_excl_vat"] and result["vat_amount"]:
        result["bill_incl_vat"] = result["bill_excl_vat"] + result["vat_amount"]

    # ── Per-kWh rate components ───────────────────────────────
    # Find all line items with kWh @ R rate patterns
    rate_lines = re.findall(
        r'([A-Za-z][A-Za-z &/\(\)]+?)\s+([\d,]+\.?\d*)\s+kWh\s+@\s+R([\d.]+)\s*/kWh\s+R\s+([\d,]+\.?\d*)',
        text
    )

    # Group by charge type - accumulate kWh and cost per type
    charge_groups = {}
    for name_raw, kwh_str, rate_str, cost_str in rate_lines:
        name_clean = re.sub(r'\s+', ' ', name_raw.strip())
        # Normalise name to category
        cat = categorise_charge(name_clean)
        kwh = float(kwh_str.replace(',', ''))
        cost = float(cost_str.replace(',', ''))
        if cat not in charge_groups:
            charge_groups[cat] = {"kwh": 0.0, "cost": 0.0, "raw_name": name_clean}
        charge_groups[cat]["kwh"] += kwh
        charge_groups[cat]["cost"] += cost

    total_kwh = result["bill_kwh_total"] or 1  # avoid div/0

    # Build rate components
    components = []
    std_kwh = result["bill_kwh_std"] or 1

    for cat, vals in charge_groups.items():
        if vals["kwh"] > 0:
            rate = round(vals["cost"] / vals["kwh"], 4)
        else:
            rate = 0.0

        is_std = "Standard" in cat or "STD" in cat.upper()
        is_energy = is_std or "Peak" in cat or "Off" in cat

        # Determine scope
        if is_energy:
            applies_to = "Standard period kWh" if is_std else ("Peak kWh" if "Peak" in cat and "Off" not in cat else "Off-Peak kWh")
        else:
            applies_to = "ALL kWh"

        components.append({
            "name": cat,
            "kwh": vals["kwh"],
            "cost": vals["cost"],
            "rate": rate,
            "applies_to": applies_to,
            "is_std_base": is_std,
            "include_in_savings": True,  # all per-kWh charges
        })

    result["rate_components"] = components

    # ── Weighted standard tariff ──────────────────────────────
    std_comps = [c for c in components if c["is_std_base"]]
    if std_comps:
        total_std_cost = sum(c["cost"] for c in std_comps)
        total_std_kwh = sum(c["kwh"] for c in std_comps)
        result["std_rate_weighted"] = round(total_std_cost / total_std_kwh, 4) if total_std_kwh else 0

    # ── Combined savings rate ─────────────────────────────────
    # Standard rate (already per std-kWh) + all other per-kWh charges weighted over total kWh
    non_std = [c for c in components if not c["is_std_base"]]
    non_std_rate = sum(c["cost"] for c in non_std) / total_kwh if non_std else 0
    result["combined_rate"] = round(result["std_rate_weighted"] + non_std_rate, 4)

    return result


def categorise_charge(name):
    name_up = name.upper()
    if "STANDARD" in name_up or " STD" in name_up:
        return "Standard Energy Charge"
    elif "OFF PEAK" in name_up or "OFF-PEAK" in name_up:
        return "Off-Peak Energy Charge"
    elif "PEAK" in name_up and "OFF" not in name_up:
        return "Peak Energy Charge"
    elif "LEGACY" in name_up:
        return "Legacy Charge"
    elif "NETWORK DEMAND" in name_up or "DEMAND CHARGE" in name_up:
        return "Network Demand Charge"
    elif "ANCILLARY" in name_up:
        return "Ancillary Service Charge"
    elif "TRANSMISSION" in name_up:
        return "Transmission Charge"
    elif "ELECTRIFICATION" in name_up:
        return "Electrification Charge"
    else:
        return name.strip()
