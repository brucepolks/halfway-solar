import os, uuid, json, smtplib, traceback
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

with app.app_context()
    init_db()

def get_setting(key, default=None):
    env_map = {
        'dash_username': 'DASH_USERNAME',
        'dash_password': 'DASH_PASSWORD',
        'smtp_host':     'SMTP_HOST',
        'smtp_port':     'SMTP_PORT',
        'smtp_user':     'SMTP_USER',
        'smtp_password': 'SMTP_PASSWORD',
    }
    env_val = os.environ.get(env_map.get(key, ''))
    if env_val:
        return env_val
    db = get_db()
    row = db.execute('SELECT value FROM settings WHERE key=?', (key,)).fetchone()
    db.close()
    return row['value'] if row else default

def set_setting(key, value):
    db = get_db()
    db.execute('INSERT OR REPLACE INTO settings (key, value) VALUES (?,?)', (key, value))
    db.commit()
    db.close()


def _dates_from_period(period_str):
    import calendar, re as _re
    if not period_str:
        return '', '', ''
    month_map = {}
    for i, name in enumerate(calendar.month_name):
        if name:
            month_map[name.upper()] = i
            month_map[name.upper()[:3]] = i
    pattern = _re.compile(
        r'(January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*[\s,]+([0-9]{4})',
        _re.IGNORECASE
    )
    m = pattern.search(period_str)
    if m:
        try:
            month_num = month_map.get(m.group(1).upper()[:3]) or month_map.get(m.group(1).upper())
            year = int(m.group(2))
            if month_num and year:
                last_day = calendar.monthrange(year, month_num)[1]
                full_month = calendar.month_name[month_num]
                return (f"{year}-{month_num:02d}-01", f"{year}-{month_num:02d}-{last_day:02d}", f"{full_month} {year}")
        except:
            pass
    return '', '', period_str

@app.route('/')
def index():
    db = get_db()
    clients = db.execute('SELECT * FROM clients ORDER BY created_at DESC').fetchall()
    db.close()
    return render_template('index.html', clients=clients)

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

@app.route('/client/<int:client_id>/analyse', methods=['GET','POST'])
def analyse_step1(client_id):
    db = get_db()
    client = db.execute('SELECT * FROM clients WHERE id=?', (client_id,)).fetchone()
    db.close()
    if not client:
        abort(404)
    if request.method == 'POST':
        bill_files = request.files.getlist('bill_pdf')
        bill_paths = []
        bills = []
        for bill_file in bill_files:
            if bill_file and bill_file.filename:
                safe = bill_file.filename.replace(' ', '_')
                bill_path = os.path.join(UPLOADS_DIR, safe)
                bill_file.save(bill_path)
                bill_paths.append(bill_path)
                try:
                    bd = parse_eskom_bill(bill_path)
                    bd['filename'] = bill_file.filename
                    bills.append(bd)
                except Exception as e:
                    print(f'Bill parse error {bill_file.filename}: {e}')
        period_str = bills[0].get('period', '') if bills else ''
        date_from, date_to, period_label = _dates_from_period(period_str)
        bill_path_str = ','.join(bill_paths)
        bill_data = {'period': period_str, 'total_kwh': sum(b.get('total_kwh') or 0 for b in bills), 'count': len(bills)}
        return render_template('analyse_step2.html', client=client, bill_data=bill_data, bill_path=bill_path_str, date_from=date_from, date_to=date_to, period_label=period_label)
    return render_template('analyse_step1.html', client=client)

@app.route('/client/<int:client_id>/analyse/generate', methods=['POST'])
def analyse_generate(client_id):
    db = get_db()
    client = db.execute('SELECT * FROM clients WHERE id=?', (client_id,)).fetchone()
    db.close()
    if not client:
        abort(404)
    period=request.form.get('period','')
    date_from=request.form.get('date_from','')
    date_to=request.form.get('date_to','')
    site_name=request.form.get('site_name', client['name'])
    tariff_rate=float(request.form.get('tariff_rate', 2.50))
    bill_path=request.form.get('bill_path','')
    dash_user=get_setting('dash_username','')
    dash_pass=get_setting('dash_password','')
    raw_rows=[]
    if dash_user and dash_pass and date_from and date_to:
        try:
            from modules.dash_scraper import get_site_data
            raw_rows=get_site_data(dash_user, dash_pass, site_name, date_from, date_to)
        except Exception as e:
            print(f'Scraper error: {traceback.format_exc()}')
    else:
        print(f'Scraper skipped: user={bool(dash_user)} pass={bool(dash_pass)} from={date_from} to={date_to}')
    totals={'generation':0,'export':0,'import':0,'consumption':0}
    formatted_rows=[]
    for row in raw_rows:
        formatted_rows.append(row)
        try:
            if len(row)>=4:
                totals['consumption']+=_parse_num(row[1])
                totals['generation']+=_parse_num(row[2])
                totals['import']+=_parse_num(row[3])
                totals['export']+=_parse_num(row[4]) if len(row)>4 else 0
        except:
            pass
    self_consumed=totals['generation']-totals['export']
    savings_amount=self_consumed*tariff_rate
    baseline=totals['consumption']*tariff_rate
    savings_pct=(savings_amount/baseline*100) if baseline else 0
    analysis_data={'period':period,'rows':formatted_rows,'totals':totals,'savings':{'amount':savings_amount,'percent':savings_pct}}
    bills=[]
    for bp in (bill_path.split(',') if bill_path else []):
        bp=bp.strip()
        if bp and os.path.exists(bp):
            try:
                bd=parse_eskom_bill(bp)
                bd['filename']=os.path.basename(bp)
                bills.append(bd)
            except:
                pass
    token=uuid.uuid4().hex
    safe_name=client['name'].replace(' ','_').replace('/','').strip('_')
    safe_period=period.replace(' ','_')
    html_content=build_html_report(dict(client), analysis_data, bills)
    html_filename=f'{safe_name}_{safe_period}_{token[:8]}.html'
    with open(os.path.join(REPORTS_DIR, html_filename), 'w') as f:
        f.write(html_content)
    xlsx_filename=f'{safe_name}_{safe_period}_{token[:8]}.xlsx'
    try:
        build_excel_report(dict(client), analysis_data, os.path.join(REPORTS_DIR, xlsx_filename))
    except Exception as e:
        print(f'Excel error: {e}')
        xlsx_filename=None
    db=get_db()
    db.execute('INSERT INTO analyses (client_id, token, filename, report_html, report_xlsx) VALUES (?,?,?,?,?)',(client_id,token,f'{safe_name}_{safe_period}',html_filename,xlsx_filename))
    db.commit()
    db.close()
    return redirect(url_for('report_view', token=token)+'?new=1')

def _parse_num(val):
    if val is None: return 0
    try: return float(str(val).replace(',','').strip())
    except: return 0

@app.route('/report/<token>')
def report_view(token):
    db=get_db()
    analysis=db.execute('SELECT * FROM analyses WHERE token=?',(token,)).fetchone()
    db.close()
    if not analysis: abort(404)
    db=get_db()
    client=db.execute('SELECT * FROM clients WHERE id=?',(analysis['client_id'],)).fetchone()
    db.close()
    html_path=os.path.join(REPORTS_DIR, analysis['report_html'])
    report_html=''
    if os.path.exists(html_path):
        with open(html_path) as f: report_html=f.read()
    is_new=request.args.get('new')=='1'
    return render_template('report_view.html', analysis=analysis, client=client, report_html=report_html, is_new=is_new)

@app.route('/report/<token>/excel')
def report_excel(token):
    db=get_db()
    analysis=db.execute('SELECT * FROM analyses WHERE token=?',(token,)).fetchone()
    db.close()
    if not analysis or not analysis['report_xlsx']: abort(404)
    path=os.path.join(REPORTS_DIR, analysis['report_xlsx'])
    if not os.path.exists(path): abort(404)
    return send_file(path, as_attachment=True)

@app.route('/report/<token>/delete', methods=['POST'])
def report_delete(token):
    db=get_db()
    analysis=db.execute('SELECT * FROM analyses WHERE token=?',(token,)).fetchone()
    if not analysis:
        db.close()
        abort(404)
    client_id=analysis['client_id']
    for f in [analysis['report_html'], analysis['report_xlsx']]:
        if f:
            p=os.path.join(REPORTS_DIR, f)
            if os.path.exists(p): os.remove(p)
    db.execute('DELETE FROM analyses WHERE token=?',(token,))
    db.commit()
    db.close()
    return redirect(url_for('client_detail', client_id=client_id))

@app.route('/report/<token>/send', methods=['POST'])
def report_send(token):
    data=request.get_json() or {}
    recipient=data.get('email','').strip()
    if not recipient: return jsonify({'ok':False,'error':'No email'}),400
    db=get_db()
    analysis=db.execute('SELECT * FROM analyses WHERE token=?',(token,)).fetchone()
    client=None
    if analysis: client=db.execute('SELECT * FROM clients WHERE id=?',(analysis['client_id'],)).fetchone()
    db.close()
    if not analysis: return jsonify({'ok':False,'error':'Not found'}),404
    report_url=request.host_url.rstrip('/')+url_for('report_view',token=token)
    smtp_host=get_setting('smtp_host','')
    smtp_port=int(get_setting('smtp_port','587') or 587)
    smtp_user=get_setting('smtp_user','')
    smtp_pass=get_setting('smtp_password','')
    client_name=client['name'] if client else 'Client'
    if smtp_host and smtp_user and smtp_pass:
        try:
            msg=MIMEMultipart('alternative')
            msg['Subject']=f'Solar Report: {client_name}'
            msg['From']=smtp_user
            msg['To']=recipient
            body=f'<html><body><p>{client_name} report ready.</p><p><a href="{report_url}">View</a></p></body></html>'
            msg.attach(MIMEText(body,'html'))
            with smtplib.SMTP(smtp_host,smtp_port) as s:
                s.starttls()
                s.login(smtp_user,smtp_pass)
                s.sendmail(smtp_user,recipient,msg.as_string())
            return jsonify({'ok':True,'message':f'Sent to {recipient}'})
        except Exception as e:
            return jsonify({'ok':False,'error':str(e),'url':report_url})
    else:
        return jsonify({'ok':False,'error':'SMTP not configured','url':report_url,'manual':True})

@app.route('/settings', methods=['GET','POST'])
def settings():
    if request.method=='POST':
        for key in ['dash_username','dash_password','smtp_host','smtp_port','smtp_user','smtp_password']:
            val=request.form.get(key,'').strip()
            if val: set_setting(key,val)
        return redirect(url_for('settings'))
    current={k:get_setting(k,'') for k in ['dash_username','smtp_host','smtp_port','smtp_user']}
    return render_template('settings.html', settings=current)

@app.route('/debug')
def debug():
    result={'dash_user':get_setting('dash_username',''),'dash_pass_set':bool(get_setting('dash_password','')),'playwright_ok':False,'playwright_error':None,'chromium_ok':False,'chromium_error':None}
    try:
        from playwright.sync_api import sync_playwright
        result['playwright_ok']=True
        try:
            with sync_playwright() as p:
                browser=p.chromium.launch(headless=True)
                browser.close()
                result['chromium_ok']=True
        except Exception as e:
            result['chromium_error']=traceback.format_exc()
    except Exception as e:
        result['playwright_error']=traceback.format_exc()
    return jsonify(result)

if __name__=='__main__':
    app.run(debug=True, port=PORT)
