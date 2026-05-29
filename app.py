import os, uuid, json, smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flask import Flask, render_template, request, redirect, url_for, jsonify, send_file, abort
from modules.db import init_db, get_db
from modules.report_generator import build_html_report, build_excel_report
from modules.bill_parser import parse_eskom_bill

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'halfway-solar-secret-2024')
PORT = int(os.environ.get('PORT', 5050))

REPORTS_DIR = os.path.join(BASE_DIR, 'reports')
UPLOADS_DIR = os.path.join(BASE_DIR, 'uploads')
os.makedirs(REPORTS_DIR, exist_ok=True)
os.makedirs(UPLOADS_DIR, exist_ok=True)

with app.app_context():
    init_db()

def get_setting(key, default=None):
    db = get_db()
    row = db.execute('SELECT value FROM settings WHERE key=?', (key,)).fetchone()
    db.close()
    return row['value'] if row else default

def set_setting(key, value):
    db = get_db()
    db.execute('INSERT OR REPLACE INTO settings (key, value) VALUES (?,?)', (key, value))
    db.commit()
    db.close()

# ── INDEX ──────────────────────────────────────────────────────────────────────
@app.route('/')
def index():
    db = get_db()
    clients = db.execute('SELECT * FROM clients ORDER BY created_at DESC').fetchall()
    db.close()
    return render_template('index.html', clients=clients)

# ── CLIENTS ────────────────────────────────────────────────────────────────────
@app.route('/client/new', methods=['GET','POST'])
def client_new():
    if request.method == 'POST':
        name = request.form['name'].strip()
        email = request.form.get('email','').strip()
        db = get_db()
        db.execute('INSERT INTO clients (name, email) VALUES (?,?)', (name, email))
        db.commit()
        db.close()
        return redirect(url_for('index'))
    return render_template('client_new.html')

@app.route('/client/<int:client_id>')
def client_detail(client_id):
    db = get_db()
    client = db.execute('SELECT * FROM clients WHERE id=?', (client_id,)).fetchone()
    analyses = db.execute('SELECT * FROM analyses WHERE client_id=? ORDER BY created_at DESC', (client_id,)).fetchall()
    db.close()
    if not client:
        abort(404)
    return render_template('client_detail.html', client=client, analyses=analyses)

# ── ANALYSE ────────────────────────────────────────────────────────────────────
@app.route('/client/<int:client_id>/analyse', methods=['GET','POST'])
def analyse_step1(client_id):
    db = get_db()
    client = db.execute('SELECT * FROM clients WHERE id=?', (client_id,)).fetchone()
    db.close()
    if not client:
        abort(404)
    if request.method == 'POST':
        bill_file = request.files.get('bill_pdf')
        bill_path = None
        bill_data = {}
        if bill_file and bill_file.filename:
            safe = bill_file.filename.replace(' ','_')
            bill_path = os.path.join(UPLOADS_DIR, safe)
            bill_file.save(bill_path)
            try:
                bill_data = parse_eskom_bill(bill_path)
            except Exception as e:
                bill_data = {'error': str(e)}
        return render_template('analyse_step2.html', client=client,
                               bill_data=bill_data, bill_path=bill_path)
    return render_template('analyse_step1.html', client=client)

@app.route('/client/<int:client_id>/analyse/generate', methods=['POST'])
def analyse_generate(client_id):
    db = get_db()
    client = db.execute('SELECT * FROM clients WHERE id=?', (client_id,)).fetchone()
    db.close()
    if not client:
        abort(404)

    # Get form data
    period      = request.form.get('period','')
    date_from   = request.form.get('date_from','')
    date_to     = request.form.get('date_to','')
    site_name   = request.form.get('site_name', client['name'])
    tariff_rate = float(request.form.get('tariff_rate', 2.50))
    bill_path   = request.form.get('bill_path','')

    # Dash IOT credentials from settings
    dash_user = get_setting('dash_username','')
    dash_pass = get_setting('dash_password','')

    # Scrape data
    raw_rows = []
    if dash_user and dash_pass and date_from and date_to:
        try:
            from modules.dash_scraper import get_site_data
            raw_rows = get_site_data(dash_user, dash_pass, site_name, date_from, date_to)
        except Exception as e:
            print(f'Scraper error: {e}')

    # Build analysis_data structure
    totals = {'generation': 0, 'export': 0, 'import': 0, 'consumption': 0}
    formatted_rows = []
    for row in raw_rows:
        formatted_rows.append(row)
        try:
            if len(row) >= 4:
                totals['generation']  += _parse_num(row[1])
                totals['export']      += _parse_num(row[2])
                totals['import']      += _parse_num(row[3])
                totals['consumption'] += _parse_num(row[4]) if len(row) > 4 else 0
        except:
            pass

    self_consumed = totals['generation'] - totals['export']
    savings_amount = self_consumed * tariff_rate
    baseline = totals['consumption'] * tariff_rate
    savings_pct = (savings_amount / baseline * 100) if baseline else 0

    analysis_data = {
        'period': period,
        'rows': formatted_rows,
        'totals': totals,
        'savings': {'amount': savings_amount, 'percent': savings_pct}
    }

    bill_data = {}
    if bill_path and os.path.exists(bill_path):
        try:
            bill_data = parse_eskom_bill(bill_path)
        except:
            pass

    # Generate token and filenames
    token = uuid.uuid4().hex
    safe_name = client['name'].replace(' ','_').replace('/','').strip('_')
    safe_period = period.replace(' ','_')

    # Build HTML report
    html_content = build_html_report(dict(client), analysis_data, bill_data)
    html_filename = f'{safe_name}_{safe_period}_{token[:8]}.html'
    html_path = os.path.join(REPORTS_DIR, html_filename)
    with open(html_path, 'w') as f:
        f.write(html_content)

    # Build Excel report
    xlsx_filename = f'{safe_name}_{safe_period}_{token[:8]}.xlsx'
    xlsx_path = os.path.join(REPORTS_DIR, xlsx_filename)
    try:
        build_excel_report(dict(client), analysis_data, xlsx_path)
    except Exception as e:
        print(f'Excel error: {e}')
        xlsx_filename = None

    # Save to DB
    db = get_db()
    db.execute('''INSERT INTO analyses (client_id, token, filename, report_html, report_xlsx)
                  VALUES (?,?,?,?,?)''',
               (client_id, token, f'{safe_name}_{safe_period}', html_filename, xlsx_filename))
    db.commit()
    db.close()

    return redirect(url_for('report_view', token=token) + '?new=1')

def _parse_num(val):
    if val is None:
        return 0
    try:
        return float(str(val).replace(',','').strip())
    except:
        return 0

# ── REPORTS ────────────────────────────────────────────────────────────────────
@app.route('/report/<token>')
def report_view(token):
    db = get_db()
    analysis = db.execute('SELECT * FROM analyses WHERE token=?', (token,)).fetchone()
    db.close()
    if not analysis:
        abort(404)
    db = get_db()
    client = db.execute('SELECT * FROM clients WHERE id=?', (analysis['client_id'],)).fetchone()
    db.close()

    html_path = os.path.join(REPORTS_DIR, analysis['report_html'])
    report_html = ''
    if os.path.exists(html_path):
        with open(html_path) as f:
            report_html = f.read()

    is_new = request.args.get('new') == '1'
    return render_template('report_view.html',
                           analysis=analysis, client=client,
                           report_html=report_html, is_new=is_new)

@app.route('/report/<token>/excel')
def report_excel(token):
    db = get_db()
    analysis = db.execute('SELECT * FROM analyses WHERE token=?', (token,)).fetchone()
    db.close()
    if not analysis or not analysis['report_xlsx']:
        abort(404)
    path = os.path.join(REPORTS_DIR, analysis['report_xlsx'])
    if not os.path.exists(path):
        abort(404)
    return send_file(path, as_attachment=True)

@app.route('/report/<token>/delete', methods=['POST'])
def report_delete(token):
    db = get_db()
    analysis = db.execute('SELECT * FROM analyses WHERE token=?', (token,)).fetchone()
    if not analysis:
        db.close()
        abort(404)
    client_id = analysis['client_id']
    for f in [analysis['report_html'], analysis['report_xlsx']]:
        if f:
            p = os.path.join(REPORTS_DIR, f)
            if os.path.exists(p):
                os.remove(p)
    db.execute('DELETE FROM analyses WHERE token=?', (token,))
    db.commit()
    db.close()
    return redirect(url_for('client_detail', client_id=client_id))

@app.route('/report/<token>/send', methods=['POST'])
def report_send(token):
    data = request.get_json() or {}
    recipient = data.get('email','').strip()
    if not recipient:
        return jsonify({'ok': False, 'error': 'No email address provided'}), 400

    db = get_db()
    analysis = db.execute('SELECT * FROM analyses WHERE token=?', (token,)).fetchone()
    client = None
    if analysis:
        client = db.execute('SELECT * FROM clients WHERE id=?', (analysis['client_id'],)).fetchone()
    db.close()

    if not analysis:
        return jsonify({'ok': False, 'error': 'Report not found'}), 404

    # Build report URL
    report_url = request.host_url.rstrip('/') + url_for('report_view', token=token)

    # Get SMTP settings
    smtp_host = get_setting('smtp_host', '')
    smtp_port = int(get_setting('smtp_port', '587') or 587)
    smtp_user = get_setting('smtp_user', '')
    smtp_pass = get_setting('smtp_password', '')

    client_name = client['name'] if client else 'Client'

    if smtp_host and smtp_user and smtp_pass:
        try:
            msg = MIMEMultipart('alternative')
            msg['Subject'] = f'Halfway Charge — Solar Report: {client_name}'
            msg['From'] = smtp_user
            msg['To'] = recipient
            body = f"""<html><body style="font-family:sans-serif;background:#0A0907;color:#E8E4DF;padding:32px;">
<h2 style="color:#C00000;">Halfway Charge Solar Report</h2>
<p>Hi,</p>
<p>Your solar performance report for <strong>{client_name}</strong> is ready.</p>
<p><a href="{report_url}" style="background:#C00000;color:#fff;padding:12px 24px;border-radius:8px;text-decoration:none;display:inline-block;margin:16px 0;">View Report</a></p>
<p style="color:rgba(232,228,223,0.4);font-size:0.85rem;">Halfway Charge Analytics</p>
</body></html>"""
            msg.attach(MIMEText(body, 'html'))
            with smtplib.SMTP(smtp_host, smtp_port) as s:
                s.starttls()
                s.login(smtp_user, smtp_pass)
                s.sendmail(smtp_user, recipient, msg.as_string())
            return jsonify({'ok': True, 'message': f'Report sent to {recipient}'})
        except Exception as e:
            return jsonify({'ok': False, 'error': str(e), 'url': report_url})
    else:
        return jsonify({'ok': False, 'error': 'SMTP not configured', 'url': report_url,
                        'manual': True})

# ── SETTINGS ───────────────────────────────────────────────────────────────────
@app.route('/settings', methods=['GET','POST'])
def settings():
    if request.method == 'POST':
        for key in ['dash_username','dash_password','smtp_host','smtp_port','smtp_user','smtp_password']:
            val = request.form.get(key,'').strip()
            if val:
                set_setting(key, val)
        return redirect(url_for('settings'))
    current = {k: get_setting(k,'') for k in ['dash_username','smtp_host','smtp_port','smtp_user']}
    return render_template('settings.html', settings=current)

if __name__ == '__main__':
    app.run(debug=True, port=PORT)
