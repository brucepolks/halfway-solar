import os, uuid, json, threading
from flask import Flask, render_template, request, redirect, url_for, jsonify, send_file, abort
from modules.db import get_db, init_db
from modules.bill_parser import parse_bill
from modules.dash_scraper import get_site_data
from modules.report_generator import build_excel, build_html_report

app = Flask(__name__)
app.secret_key = "solar-versofy-2026"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
REPORTS_DIR = os.path.join(BASE_DIR, "reports")
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
os.makedirs(REPORTS_DIR, exist_ok=True)
os.makedirs(UPLOAD_DIR, exist_ok=True)

# In-memory job status store
jobs = {}

# ── Initialise DB ─────────────────────────────────────────────────
init_db()

# ── Home: Client list ─────────────────────────────────────────────
@app.route("/")
def index():
    db = get_db()
    clients = db.execute(
        "SELECT c.*, COUNT(a.id) as report_count, MAX(a.created_at) as last_report "
        "FROM clients c LEFT JOIN analyses a ON a.client_id = c.id "
        "GROUP BY c.id ORDER BY c.name"
    ).fetchall()
    db.close()
    return render_template("index.html", clients=clients)

# ── Add / Edit Client ─────────────────────────────────────────────
@app.route("/client/new", methods=["GET","POST"])
def client_new():
    db = get_db()
    # Get all sites from settings for dropdown hint
    if request.method == "POST":
        db.execute(
            "INSERT INTO clients (name, site_name, site_id, address, contact_email) VALUES (?,?,?,?,?)",
            (request.form["name"], request.form["site_name"], 0,
             request.form.get("address",""), request.form.get("contact_email",""))
        )
        db.commit(); db.close()
        return redirect(url_for("index"))
    db.close()
    return render_template("client_new.html")

@app.route("/client/<int:cid>/edit", methods=["GET","POST"])
def client_edit(cid):
    db = get_db()
    client = db.execute("SELECT * FROM clients WHERE id=?", (cid,)).fetchone()
    if request.method == "POST":
        db.execute(
            "UPDATE clients SET name=?, site_name=?, site_id=?, address=?, contact_email=? WHERE id=?",
            (request.form["name"], request.form["site_name"], 0,
             request.form.get("address",""), request.form.get("contact_email",""), cid)
        )
        db.commit(); db.close()
        return redirect(url_for("index"))
    db.close()
    return render_template("client_new.html", client=client)

# ── Client history ─────────────────────────────────────────────────
@app.route("/client/<int:cid>")
def client_detail(cid):
    db = get_db()
    client = db.execute("SELECT * FROM clients WHERE id=?", (cid,)).fetchone()
    analyses = db.execute(
        "SELECT * FROM analyses WHERE client_id=? ORDER BY created_at DESC", (cid,)
    ).fetchall()
    db.close()
    return render_template("client_detail.html", client=client, analyses=analyses)

# ── Step 1: Upload bill ───────────────────────────────────────────
@app.route("/analyse/new", methods=["GET","POST"])
def analyse_new():
    db = get_db()
    clients = db.execute("SELECT * FROM clients ORDER BY name").fetchall()
    db.close()
    if request.method == "POST":
        client_id = int(request.form["client_id"])
        f = request.files["bill_pdf"]
        fname = f"{uuid.uuid4().hex}.pdf"
        fpath = os.path.join(UPLOAD_DIR, fname)
        f.save(fpath)
        return redirect(url_for("analyse_review", client_id=client_id, pdf=fname))
    return render_template("analyse_step1.html", clients=clients)

# ── Step 2: Review parsed bill ────────────────────────────────────
@app.route("/analyse/review")
def analyse_review():
    client_id = int(request.args["client_id"])
    pdf_name = request.args["pdf"]
    pdf_path = os.path.join(UPLOAD_DIR, pdf_name)
    db = get_db()
    client = db.execute("SELECT * FROM clients WHERE id=?", (client_id,)).fetchone()
    db.close()
    bill = parse_bill(pdf_path)
    return render_template("analyse_step2.html", client=client, bill=bill,
                           pdf=pdf_name, client_id=client_id)

# ── Step 3: Pull dashboard data (async job) ───────────────────────
@app.route("/analyse/run", methods=["POST"])
def analyse_run():
    data = request.json
    job_id = uuid.uuid4().hex
    jobs[job_id] = {"status": "running", "message": "Connecting to Dash IOT..."}

    def run_job():
        try:
            db = get_db()
            client = db.execute("SELECT * FROM clients WHERE id=?", (data["client_id"],)).fetchone()
            settings = {r["key"]: r["value"] for r in db.execute("SELECT * FROM settings").fetchall()}
            db.close()

            jobs[job_id]["message"] = "Logging into Dash IOT..."
            dash_data = get_site_data(
                settings["dash_username"], settings["dash_password"],
                client["site_name"], data["period_from"], data["period_to"]
            )

            if not dash_data:
                jobs[job_id] = {"status": "error", "message": "No data returned from Dash IOT"}
                return

            jobs[job_id]["message"] = "Calculating savings..."
            totals = dash_data["totals"]
            bill_kwh = float(data["bill_kwh"])
            bill_excl = float(data["bill_excl_vat"])
            bill_incl = float(data["bill_incl_vat"])
            combined_rate = float(data["combined_rate"])

            self_consumed = totals["self_consumed"]
            savings_excl = round(self_consumed * combined_rate, 2)
            savings_incl = round(savings_excl * 1.15, 2)
            variance_kwh = totals["grid_import"] - bill_kwh
            variance_pct = round(abs(variance_kwh) / bill_kwh * 100, 2) if bill_kwh else 0

            token = uuid.uuid4().hex

            db = get_db()
            cur = db.execute(
                """INSERT INTO analyses
                   (client_id, bill_period_from, bill_period_to, bill_kwh, bill_excl_vat, bill_incl_vat,
                    dash_consumption, dash_production, dash_grid_import, savings_excl_vat, savings_incl_vat,
                    combined_rate, variance_pct, report_token)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (data["client_id"], data["period_from"], data["period_to"],
                 bill_kwh, bill_excl, bill_incl,
                 totals["consumption"], totals["production"], totals["grid_import"],
                 savings_excl, savings_incl, combined_rate, variance_pct, token)
            )
            analysis_id = cur.lastrowid

            rate_components = json.loads(data["rate_components"])
            for comp in rate_components:
                db.execute(
                    "INSERT INTO rate_components (analysis_id, charge_name, rate, applies_to) VALUES (?,?,?,?)",
                    (analysis_id, comp["name"], comp["rate"], comp.get("applies_to",""))
                )
            db.commit()

            jobs[job_id]["message"] = "Generating reports..."
            analysis_row = {
                "bill_period_from": data["period_from"],
                "bill_period_to": data["period_to"],
                "bill_kwh": bill_kwh, "bill_excl_vat": bill_excl, "bill_incl_vat": bill_incl,
                "dash_consumption": totals["consumption"], "dash_production": totals["production"],
                "dash_grid_import": totals["grid_import"],
                "savings_excl_vat": savings_excl, "savings_incl_vat": savings_incl,
                "combined_rate": combined_rate, "variance_pct": variance_pct,
            }
            client_dict = dict(client)

            # Save HTML report
            html = build_html_report(analysis_row, client_dict, rate_components, token)
            html_path = os.path.join(REPORTS_DIR, f"{token}.html")
            with open(html_path, "w") as hf:
                hf.write(html)

            # Save Excel
            excel_path = build_excel(analysis_row, client_dict, rate_components,
                                     dash_data["rows"], REPORTS_DIR)
            db.execute("UPDATE analyses SET report_token=? WHERE id=?", (token, analysis_id))
            db.commit(); db.close()

            jobs[job_id] = {"status": "done", "token": token, "analysis_id": analysis_id}

        except Exception as e:
            jobs[job_id] = {"status": "error", "message": str(e)}

    threading.Thread(target=run_job, daemon=True).start()
    return jsonify({"job_id": job_id})

@app.route("/analyse/status/<job_id>")
def job_status(job_id):
    return jsonify(jobs.get(job_id, {"status": "unknown"}))

# ── Report view (shareable) ───────────────────────────────────────
@app.route("/report/<token>")
def report_view(token):
    html_path = os.path.join(REPORTS_DIR, f"{token}.html")
    if not os.path.exists(html_path):
        abort(404)
    db = get_db()
    analysis = db.execute("SELECT * FROM analyses WHERE report_token=?", (token,)).fetchone()
    client = db.execute("SELECT * FROM clients WHERE id=?", (analysis["client_id"],)).fetchone() if analysis else None
    db.close()
    with open(html_path) as f:
        report_html = f.read()
    is_new = request.args.get("new") == "1"
    return render_template("report_view.html", report_html=report_html, token=token,
                           analysis=analysis, client=client, is_new=is_new)

# ── Download Excel ────────────────────────────────────────────────
@app.route("/report/<token>/excel")
def report_excel(token):
    db = get_db()
    analysis = db.execute("SELECT * FROM analyses WHERE report_token=?", (token,)).fetchone()
    db.close()
    if not analysis:
        abort(404)
    # Find the excel file
    for fname in os.listdir(REPORTS_DIR):
        if fname.endswith(".xlsx") and analysis["bill_period_from"][:7] in fname:
            return send_file(os.path.join(REPORTS_DIR, fname), as_attachment=True)
    abort(404)


@app.route("/report/<token>/send", methods=["POST"])
def report_send(token):
    import smtplib, json
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart

    data = request.get_json()
    email = data.get("email", "").strip()
    if not email:
        return jsonify({"ok": False, "error": "No email provided"})

    db = get_db()
    analysis = db.execute("SELECT * FROM analyses WHERE report_token=?", (token,)).fetchone()
    client = db.execute("SELECT * FROM clients WHERE id=?", (analysis["client_id"],)).fetchone() if analysis else None
    cfg = {r["key"]: r["value"] for r in db.execute("SELECT * FROM settings").fetchall()}
    db.close()

    if not analysis:
        return jsonify({"ok": False, "error": "Report not found"})

    report_url = f"{request.host_url}report/{token}"
    client_name = client["name"] if client else "Client"
    period = f"{analysis['bill_period_from']} to {analysis['bill_period_to']}"

    # Use SMTP settings from settings table, or fall back to mailto link
    smtp_host = cfg.get("smtp_host", "")
    smtp_user = cfg.get("smtp_user", "")
    smtp_pass = cfg.get("smtp_pass", "")

    if not smtp_host:
        # Return the link for manual sending if SMTP not configured
        return jsonify({"ok": True, "manual": True, "url": report_url,
                        "message": "SMTP not configured — copy link to send manually"})

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"Solar Performance Report — {client_name} ({period})"
        msg["From"] = smtp_user
        msg["To"] = email
        html_body = f"""
        <p>Hi,</p>
        <p>Please find your solar performance report for the period {period} at the link below:</p>
        <p><a href="{report_url}" style="background:#C00000;color:white;padding:10px 20px;
           text-decoration:none;border-radius:4px;display:inline-block;">View Report</a></p>
        <p style="color:#888;font-size:12px;">Prepared by Halfway Charge Analytics</p>
        """
        msg.attach(MIMEText(html_body, "html"))
        port = int(cfg.get("smtp_port", "587"))
        with smtplib.SMTP(smtp_host, port) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.sendmail(smtp_user, email, msg.as_string())
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


# ── Delete analysis ───────────────────────────────────────────────
@app.route("/report/<token>/delete", methods=["POST"])
def report_delete(token):
    db = get_db()
    analysis = db.execute("SELECT * FROM analyses WHERE report_token=?", (token,)).fetchone()
    if analysis:
        client_id = analysis["client_id"]
        db.execute("DELETE FROM rate_components WHERE analysis_id=?", (analysis["id"],))
        db.execute("DELETE FROM analyses WHERE report_token=?", (token,))
        db.commit()
        # Remove files
        for f in [os.path.join(REPORTS_DIR, f"{token}.html")]:
            if os.path.exists(f): os.remove(f)
        db.close()
        return redirect(f"/client/{client_id}")
    db.close()
    return redirect("/")

# ── Settings ──────────────────────────────────────────────────────
@app.route("/settings", methods=["GET","POST"])
def settings():
    db = get_db()
    if request.method == "POST":
        for key in ["dash_username", "dash_password", "dash_url"]:
            if key in request.form:
                db.execute("INSERT OR REPLACE INTO settings VALUES (?,?)", (key, request.form[key]))
        db.commit()
    cfg = {r["key"]: r["value"] for r in db.execute("SELECT * FROM settings").fetchall()}
    db.close()
    return render_template("settings.html", cfg=cfg)

if __name__ == "__main__":
    import webbrowser, time
    def open_browser():
        time.sleep(1.2)
        webbrowser.open("http://localhost:5050")
    threading.Thread(target=open_browser, daemon=True).start()
    app.run(port=5050, debug=False)
