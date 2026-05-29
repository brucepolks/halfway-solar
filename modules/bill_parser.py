import pdfplumber
import re

def parse_eskom_bill(pdf_path):
    """Extract key data from an Eskom PDF bill."""
    data = {
        'account_number': None,
        'period': None,
        'total_kwh': None,
        'total_amount': None,
        'line_items': []
    }
    with pdfplumber.open(pdf_path) as pdf:
        full_text = ''
        for page in pdf.pages:
            full_text += (page.extract_text() or '') + '\n'
            tables = page.extract_tables()
            for table in tables:
                for row in table:
                    if row:
                        data['line_items'].append([str(c) if c else '' for c in row])

    # Try to extract account number
    m = re.search(r'Account\s+(?:Number|No)[:\s]+(\d[\d\s\-]+)', full_text, re.IGNORECASE)
    if m:
        data['account_number'] = m.group(1).strip()

    # Try to extract period
    m = re.search(r'(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{4}', full_text, re.IGNORECASE)
    if m:
        data['period'] = m.group(0)

    # Try to extract kWh
    m = re.search(r'(\d[\d,]+)\s*kWh', full_text, re.IGNORECASE)
    if m:
        data['total_kwh'] = float(m.group(1).replace(',', ''))

    # Try to extract total amount
    m = re.search(r'Total[^\n]*R\s*([\d,]+\.?\d*)', full_text, re.IGNORECASE)
    if m:
        data['total_amount'] = float(m.group(1).replace(',', ''))

    return data
