import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
import os, re
from datetime import datetime

def build_excel_report(client, analysis_data, output_path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Solar Report"

    red_fill = PatternFill("solid", fgColor="C00000")
    dark_fill = PatternFill("solid", fgColor="1A1714")
    grey_fill = PatternFill("solid", fgColor="2A2724")
    white_font = Font(color="FFFFFF", bold=True, name="Calibri")
    normal_font = Font(color="FFFFFF", name="Calibri")
    red_font = Font(color="C00000", bold=True, name="Calibri")

    # Title
    ws.merge_cells("A1:F1")
    ws["A1"] = f"Halfway Charge — Solar Report: {client['name']}"
    ws["A1"].font = Font(color="FFFFFF", bold=True, size=16, name="Calibri")
    ws["A1"].fill = dark_fill
    ws["A1"].alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 40

    # Headers
    headers = ["Date", "Generation (kWh)", "Export (kWh)", "Import (kWh)", "Consumption (kWh)", "Notes"]
    for col, h in enumerate(headers, 1):
        cell = ws.cell(row=2, column=col, value=h)
        cell.font = white_font
        cell.fill = red_fill
        cell.alignment = Alignment(horizontal="center")

    # Data rows
    rows = analysis_data.get('rows', [])
    for r_idx, row in enumerate(rows, 3):
        fill = grey_fill if r_idx % 2 == 0 else dark_fill
        for c_idx, val in enumerate(row[:6], 1):
            cell = ws.cell(row=r_idx, column=c_idx, value=val)
            cell.font = normal_font
            cell.fill = fill
            cell.alignment = Alignment(horizontal="center")

    # Summary row
    summary_row = len(rows) + 3
    ws.cell(row=summary_row, column=1, value="TOTAL").font = white_font
    ws.cell(row=summary_row, column=1).fill = red_fill

    for col in range(1, 7):
        ws.cell(row=summary_row, column=col).fill = red_fill
        ws.cell(row=summary_row, column=col).font = white_font

    totals = analysis_data.get('totals', {})
    ws.cell(row=summary_row, column=2, value=totals.get('generation', 0)).fill = red_fill
    ws.cell(row=summary_row, column=2).font = white_font
    ws.cell(row=summary_row, column=3, value=totals.get('export', 0)).fill = red_fill
    ws.cell(row=summary_row, column=3).font = white_font
    ws.cell(row=summary_row, column=4, value=totals.get('import', 0)).fill = red_fill
    ws.cell(row=summary_row, column=4).font = white_font
    ws.cell(row=summary_row, column=5, value=totals.get('consumption', 0)).fill = red_fill
    ws.cell(row=summary_row, column=5).font = white_font

    # Column widths
    for col in range(1, 7):
        ws.column_dimensions[get_column_letter(col)].width = 20

    ws.sheet_view.showGridLines = False
    wb.save(output_path)
    return output_path


def build_html_report(client, analysis_data, bill_data=None):
    """Generate a dark-themed HTML report matching Halfway Charge kiosk aesthetic."""
    name = client.get('name', 'Client')
    period = analysis_data.get('period', '')
    rows = analysis_data.get('rows', [])
    totals = analysis_data.get('totals', {})
    savings = analysis_data.get('savings', {})

    total_gen = totals.get('generation', 0)
    total_exp = totals.get('export', 0)
    total_imp = totals.get('import', 0)
    self_consumed = total_gen - total_exp if total_gen and total_exp else 0
    self_sufficiency = round((self_consumed / totals.get('consumption', 1)) * 100) if totals.get('consumption') else 0

    rate_rows_html = ''
    if bill_data and bill_data.get('line_items'):
        for item in bill_data['line_items']:
            if len(item) >= 2:
                is_total = any('total' in str(c).lower() or 'rate' in str(c).lower() for c in item)
                style = ' class="rate-total"' if is_total else ''
                cells = ''.join(f'<td>{c}</td>' for c in item)
                rate_rows_html += f'<tr{style}>{cells}</tr>'

    data_rows_html = ''
    for i, row in enumerate(rows):
        cls = 'even' if i % 2 == 0 else 'odd'
        cells = ''.join(f'<td>{c}</td>' for c in row)
        data_rows_html += f'<tr class="{cls}">{cells}</tr>'

    savings_amount = savings.get('amount', 0)
    savings_pct = savings.get('percent', 0)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Halfway Charge — {name} Solar Report</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,300;12..96,400;12..96,600;12..96,700&family=Hanken+Grotesk:wght@300;400;500;600&display=swap" rel="stylesheet">
<style>
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
  :root {{
    --bg: #0A0907;
    --surface: rgba(255,255,255,0.04);
    --line: rgba(255,255,255,0.08);
    --red: #C00000;
    --amber: #E8A020;
    --green: #22C55E;
    --font-d: 'Bricolage Grotesque', sans-serif;
    --font-b: 'Hanken Grotesk', sans-serif;
  }}
  body {{
    background: var(--bg);
    color: #E8E4DF;
    font-family: var(--font-b);
    min-height: 100vh;
    position: relative;
    overflow-x: hidden;
  }}
  body::before {{
    content: '';
    position: fixed; inset: 0;
    background: radial-gradient(ellipse 80% 50% at 50% -10%, rgba(192,0,0,0.18) 0%, transparent 70%);
    pointer-events: none; z-index: 0;
  }}
  body::after {{
    content: '';
    position: fixed; inset: 0;
    background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noise'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noise)' opacity='0.04'/%3E%3C/svg%3E");
    opacity: 0.35; pointer-events: none; z-index: 0;
  }}
  .wrap {{ position: relative; z-index: 1; max-width: 1100px; margin: 0 auto; padding: 48px 24px; }}

  /* Header */
  .report-header {{ display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 48px; }}
  .brand {{ display: flex; align-items: center; gap: 12px; }}
  .brand-bolt {{ width: 36px; height: 36px; }}
  .brand-name {{ font-family: var(--font-d); font-size: 1.2rem; font-weight: 600; letter-spacing: 0.04em; color: #fff; }}
  .report-meta {{ text-align: right; }}
  .report-meta h1 {{ font-family: var(--font-d); font-size: 1.8rem; font-weight: 700; color: #fff; }}
  .report-meta p {{ color: rgba(232,228,223,0.5); font-size: 0.9rem; margin-top: 4px; }}

  /* Savings hero */
  .savings-hero {{ background: var(--surface); border: 1px solid var(--line); border-radius: 20px; padding: 48px; text-align: center; margin-bottom: 32px; backdrop-filter: blur(12px); }}
  .savings-hero .label {{ font-size: 0.85rem; letter-spacing: 0.12em; text-transform: uppercase; color: rgba(232,228,223,0.4); margin-bottom: 12px; }}
  .savings-hero .amount {{ font-family: var(--font-d); font-size: clamp(3rem, 8vw, 5.5rem); font-weight: 700; background: linear-gradient(135deg, #fff 0%, var(--red) 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; line-height: 1; }}
  .savings-hero .sub {{ color: rgba(232,228,223,0.5); margin-top: 16px; font-size: 1rem; }}

  /* KPI grid */
  .kpi-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; margin-bottom: 40px; }}
  .kpi {{ background: var(--surface); border: 1px solid var(--line); border-radius: 16px; padding: 24px; backdrop-filter: blur(8px); }}
  .kpi .kpi-label {{ font-size: 0.75rem; letter-spacing: 0.1em; text-transform: uppercase; color: rgba(232,228,223,0.4); margin-bottom: 8px; }}
  .kpi .kpi-value {{ font-family: var(--font-d); font-size: 2rem; font-weight: 700; color: #fff; }}
  .kpi .kpi-unit {{ font-size: 0.85rem; color: rgba(232,228,223,0.4); margin-top: 4px; }}
  .kpi.red .kpi-value {{ color: var(--red); }}
  .kpi.green .kpi-value {{ color: var(--green); }}
  .kpi.amber .kpi-value {{ color: var(--amber); }}

  /* Tables */
  .section-title {{ font-family: var(--font-d); font-size: 1.1rem; font-weight: 600; color: #fff; margin-bottom: 16px; padding-bottom: 12px; border-bottom: 1px solid var(--line); }}
  .table-wrap {{ background: var(--surface); border: 1px solid var(--line); border-radius: 16px; overflow: hidden; margin-bottom: 32px; backdrop-filter: blur(8px); }}
  table {{ width: 100%; border-collapse: collapse; font-size: 0.875rem; }}
  thead th {{ background: rgba(192,0,0,0.2); color: rgba(232,228,223,0.7); font-weight: 500; letter-spacing: 0.06em; text-transform: uppercase; font-size: 0.75rem; padding: 14px 16px; text-align: left; border-bottom: 1px solid var(--line); }}
  tbody td {{ padding: 12px 16px; border-bottom: 1px solid var(--line); color: #E8E4DF; }}
  tbody tr:last-child td {{ border-bottom: none; }}
  tbody tr.even td {{ background: rgba(255,255,255,0.02); }}
  tbody tr.odd td {{ background: transparent; }}
  tbody tr.rate-total td {{ background: #C00000 !important; color: #ffffff !important; font-weight: 600 !important; }}

  /* Footer */
  .report-footer {{ text-align: center; margin-top: 64px; color: rgba(232,228,223,0.2); font-size: 0.8rem; }}
</style>
</head>
<body>
<div class="wrap">
  <div class="report-header">
    <div class="brand">
      <svg class="brand-bolt" viewBox="0 0 36 36" fill="none" xmlns="http://www.w3.org/2000/svg">
        <polygon points="20,2 8,20 18,20 16,34 28,16 18,16" fill="#C00000"/>
      </svg>
      <span class="brand-name">Halfway Charge</span>
    </div>
    <div class="report-meta">
      <h1>{name}</h1>
      <p>Solar Performance Report &mdash; {period}</p>
      <p>Generated {datetime.now().strftime('%d %B %Y')}</p>
    </div>
  </div>

  <div class="savings-hero">
    <div class="label">Estimated Savings This Period</div>
    <div class="amount">R {savings_amount:,.0f}</div>
    <div class="sub">{savings_pct:.1f}% reduction vs grid-only baseline</div>
  </div>

  <div class="kpi-grid">
    <div class="kpi green">
      <div class="kpi-label">Solar Generated</div>
      <div class="kpi-value">{total_gen:,.0f}</div>
      <div class="kpi-unit">kWh</div>
    </div>
    <div class="kpi amber">
      <div class="kpi-label">Self Consumed</div>
      <div class="kpi-value">{self_consumed:,.0f}</div>
      <div class="kpi-unit">kWh</div>
    </div>
    <div class="kpi red">
      <div class="kpi-label">Grid Import</div>
      <div class="kpi-value">{total_imp:,.0f}</div>
      <div class="kpi-unit">kWh</div>
    </div>
    <div class="kpi">
      <div class="kpi-label">Self-Sufficiency</div>
      <div class="kpi-value">{self_sufficiency}</div>
      <div class="kpi-unit">%</div>
    </div>
  </div>

  {'<div class="section-title">Daily Energy Data</div><div class="table-wrap"><table><thead><tr><th>Date</th><th>Generation (kWh)</th><th>Export (kWh)</th><th>Import (kWh)</th><th>Consumption (kWh)</th></tr></thead><tbody>' + data_rows_html + '</tbody></table></div>' if data_rows_html else ''}

  {'<div class="section-title">Eskom Bill Breakdown</div><div class="table-wrap"><table><tbody>' + rate_rows_html + '</tbody></table></div>' if rate_rows_html else ''}

  <div class="report-footer">
    <p>Halfway Charge Analytics &mdash; Confidential</p>
    <p>This report is generated automatically from Dash IOT monitoring data.</p>
  </div>
</div>
</body>
</html>"""
    return html
