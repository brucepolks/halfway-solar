import pdfplumber
import re

# Metadata fields to exclude from line_items display
METADATA_KEYS = {
    'accountnumber', 'account number', 'accountno', 'account no',
    'billingdate', 'billing date', 'taxinvoiceno', 'tax invoice',
    'accountmonth', 'account month', 'currentduedate', 'due date',
    'vatregno', 'vat reg', 'securityheld', 'security held',
    'balance', 'payment', 'electronic', 'vat raised', 'account summary',
    'account transaction', 'brought forward',
}

def _is_charge_row(row):
    """Return True if this row looks like an actual charge/amount line."""
    if not row or len(row) < 2:
        return False
    joined = ' '.join(str(c) for c in row).strip()
    if not joined:
        return False
    first = str(row[0]).strip().lower().replace(' ', '')
    for key in METADATA_KEYS:
        if first == key.replace(' ', '') or key.replace(' ', '') in first:
            return False
    for cell in row:
        s = str(cell).strip().replace(',', '').replace('R', '').strip()
        if re.match(r'^\d+(\.\d+)?$', s):
            return True
    return False


def parse_eskom_bill(pdf_path):
    """Extract key data from an Eskom PDF bill."""
    data = {
        'account_number': None,
        'period': None,
        'total_kwh': None,
        'total_amount': None,
        'line_items': []
    }

    all_rows = []

    with pdfplumber.open(pdf_path) as pdf:
        full_text = ''
        for page in pdf.pages:
            full_text += (page.extract_text() or '') + '\n'
            tables = page.extract_tables()
            for table in tables:
                for row in table:
                    if row:
                        cleaned = [str(c).strip() if c else '' for c in row]
                        all_rows.append(cleaned)

    # Extract account number
    m = re.search(r'Account\s+(?:Number|No)[:\s]+(\d[\d\s\-]+)', full_text, re.IGNORECASE)
    if m:
        data['account_number'] = m.group(1).strip()

    # Extract period - try ACCOUNTMONTH table row first, then regex
    period = None
    for row in all_rows:
        first = str(row[0]).strip().lower().replace(' ', '')
        if 'accountmonth' in first:
            for cell in row[1:]:
                val = str(cell).strip()
                if val and re.search(r'[A-Za-z]', val):
                    period = val
                    break
        if period:
            break

    if not period:
        m = re.search(
            r'\b(January|February|March|April|May|June|July|August|September|October|November|December|'
            r'Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s+\d{4}\b',
            full_text, re.IGNORECASE
        )
        if m:
            period = m.group(0)

    data['period'] = period or ''

    # Extract kWh
    m = re.search(r'(\d[\d,]+)\s*kWh', full_text, re.IGNORECASE)
    if m:
        data['total_kwh'] = float(m.group(1).replace(',', ''))

    # Extract total amount
    m = re.search(
        r'TOTAL\s+CHARGES\s+FOR\s+BILLING\s+PERIOD[^\d]*([\d,]+\.?\d*)',
        full_text, re.IGNORECASE
    )
    if m:
        data['total_amount'] = float(m.group(1).replace(',', ''))
    else:
        m = re.search(r'Total[^\n]*R\s*([\d,]+\.?\d*)', full_text, re.IGNORECASE)
        if m:
            data['total_amount'] = float(m.group(1).replace(',', ''))

    # Only keep actual charge rows
    data['line_items'] = [row for row in all_rows if _is_charge_row(row)]

    return data
