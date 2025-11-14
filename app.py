from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file
import sqlite3
from datetime import datetime
import os
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import pandas as pd
from reportlab.pdfgen import canvas

# ====================== CONFIG ======================

DB_PATH = os.path.join(os.path.dirname(__file__), "database.db")

app = Flask(__name__)
app.secret_key = "CHANGE_THIS_SECRET_KEY"

SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SMTP_USER = "financial.affairs@hu.edu.iq"   # ضعي بريد الجامعة
SMTP_PASS = "APP_PASSWORD_HERE"             # ضعي App Password

# ====================== DB ==========================

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cur = conn.cursor()

    # جدول الطلبات
    cur.execute("""
        CREATE TABLE IF NOT EXISTS requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            requester_name TEXT NOT NULL,
            department TEXT NOT NULL,
            email TEXT NOT NULL,
            job_title TEXT,
            item_description TEXT NOT NULL,
            category TEXT NOT NULL,
            quantity INTEGER,
            unit TEXT,
            specs TEXT,
            justification TEXT,
            estimated_total REAL NOT NULL,
            approver_title TEXT NOT NULL,
            status TEXT NOT NULL,
            approver_name TEXT,
            decision_note TEXT,
            created_at TEXT NOT NULL,
            decided_at TEXT
        )
    """)

    # جدول المستخدمين
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL
        )
    """)

    conn.commit()
    conn.close()

# ======================== ROLES =======================

def determine_approver_title(amount: float) -> str:
    if amount <= 2_000_000:
        return "مدير صندوق المالية"
    elif 2_000_000 < amount <= 20_000_000:
        return "مدير الشؤون المالية"
    else:
        return "رئيس الجامعة"

def current_user():
    if "user_id" not in session:
        return None
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE id = ?", (session["user_id"],))
    user = cur.fetchone()
    conn.close()
    return user

def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            flash("يُرجى تسجيل الدخول.", "warning")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrapper

def roles_required(*roles):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            user = current_user()
            if not user or user["role"] not in roles:
                flash("ليس لديك صلاحية.", "danger")
                return redirect(url_for("index"))
            return f(*args, **kwargs)
        return wrapper
    return decorator

# ======================== EMAIL =======================

def send_email(to, subject, body):
    try:
        msg = MIMEMultipart()
        msg["From"] = SMTP_USER
        msg["To"] = to
        msg["Subject"] = subject

        msg.attach(MIMEText(body, "html"))

        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.sendmail(SMTP_USER, to, msg.as_string())

    except Exception as e:
        print("EMAIL ERROR:", e)

# ======================== AUTH =========================

@app.route("/create_admin")
def create_admin():
    # شغّلي مرة واحدة فقط
    conn = get_db_connection()
    cur = conn.cursor()

    email = "admin@hu.edu.iq"
    password = "Admin@123"

    cur.execute("SELECT * FROM users WHERE email=?", (email,))
    if not cur.fetchone():
        cur.execute("""
            INSERT INTO users (full_name, email, password_hash, role)
            VALUES (?, ?, ?, ?)
        """, ("مدير النظام", email, generate_password_hash(password), "admin"))
        conn.commit()

    conn.close()
    return "تم إنشاء الأدمن."

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"].strip()
        password = request.form["password"]

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE email=?", (email,))
        user = cur.fetchone()
        conn.close()

        if user and check_password_hash(user["password_hash"], password):
            session["user_id"] = user["id"]
            session["role"] = user["role"]
            flash("تم تسجيل الدخول.", "success")
            return redirect(url_for("index"))

        flash("بيانات الدخول غير صحيحة.", "danger")

    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    flash("تم تسجيل الخروج.", "info")
    return redirect(url_for("login"))

# ======================== MAIN ROUTES ===================

@app.route("/")
def index():
    return render_template("new_request.html")

@app.route("/requests/new", methods=["POST"])
def new_request():
    req_name = request.form["requester_name"].strip()
    dept = request.form["department"].strip()
    email = request.form["email"].strip()
    job = request.form.get("job_title", "")
    desc = request.form["item_description"]
    cat = request.form["category"]
    qty = int(request.form.get("quantity") or 0)
    unit = request.form.get("unit", "")
    specs = request.form.get("specs", "")
    just = request.form.get("justification", "")
    total = float(request.form["estimated_total"])

    approver = determine_approver_title(total)
    created = datetime.now().strftime("%Y-%m-%d %H:%M")

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO requests (
            requester_name, department, email, job_title, item_description,
            category, quantity, unit, specs, justification, estimated_total,
            approver_title, status, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        req_name, dept, email, job, desc, cat, qty, unit, specs, just, total,
        approver, "قيد المراجعة", created
    ))
    conn.commit()
    conn.close()

    # إشعار بريد
    send_email(
        to="financial.affairs@hu.edu.iq",
        subject="طلب تجهيز جديد",
        body=f"""
        تم تقديم طلب جديد:<br><br>
        <b>الموظف:</b> {req_name}<br>
        <b>القسم:</b> {dept}<br>
        <b>المبلغ:</b> {total:,.0f} د.ع<br>
        """
    )

    flash("تم إرسال الطلب.", "success")
    return redirect(url_for("index"))

# ===================== REQUESTS LIST ===================

@app.route("/requests")
@login_required
@roles_required("admin", "fund_manager", "finance_manager", "president")
def requests_list():
    conn = get_db_connection()
    cur = conn.cursor()

    query = "SELECT * FROM requests WHERE 1=1"
    params = []

    dept = request.args.get("department")
    status = request.args.get("status")
    f = request.args.get("date_from")
    t = request.args.get("date_to")

    if dept:
        query += " AND department LIKE ?"
        params.append(f"%{dept}%")

    if status:
        query += " AND status = ?"
        params.append(status)

    if f:
        query += " AND created_at >= ?"
        params.append(f)

    if t:
        query += " AND created_at <= ?"
        params.append(t)

    query += " ORDER BY created_at DESC"

    cur.execute(query, params)
    rows = cur.fetchall()
    conn.close()

    return render_template("requests_list.html", requests=rows)

# ===================== REQUEST DETAILS =================

@app.route("/requests/<int:rid>")
@login_required
@roles_required("admin", "fund_manager", "finance_manager", "president")
def request_detail(rid):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM requests WHERE id=?", (rid,))
    row = cur.fetchone()
    conn.close()

    if not row:
        flash("الطلب غير موجود.", "warning")
        return redirect(url_for("requests_list"))

    return render_template("request_detail.html", req=row)

@app.route("/requests/<int:rid>/decision", methods=["POST"])
@login_required
@roles_required("admin", "fund_manager", "finance_manager", "president")
def request_decision(rid):
    action = request.form["action"]
    note = request.form.get("note", "")

    status_map = {
        "approve": "موافق",
        "reject": "مرفوض",
        "return": "إرجاع للاستكمال"
    }

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM requests WHERE id=?", (rid,))
    req = cur.fetchone()

    new_status = status_map.get(action, "قيد المراجعة")
    decided = datetime.now().strftime("%Y-%m-%d %H:%M")

    cur.execute("""
        UPDATE requests
        SET status=?, approver_name=?, decision_note=?, decided_at=?
        WHERE id=?
    """, (
        new_status,
        current_user()["full_name"],
        note,
        decided,
        rid
    ))
    conn.commit()
    conn.close()

    # إشعار بريد لمقدم الطلب
    send_email(
        to=req["email"],
        subject=f"تحديث حالة الطلب رقم {req['id']}",
        body=f"""
        تم تحديث حالة الطلب:<br><br>
        <b>الحالة الجديدة:</b> {new_status}<br>
        <b>الملاحظة:</b> {note}<br>
        """
    )

    flash("تم تحديث حالة الطلب.", "success")
    return redirect(url_for("request_detail", rid=rid))

# ===================== EXPORT EXCEL ====================

@app.route("/export/excel")
@login_required
def export_excel():
    conn = get_db_connection()
    df = pd.read_sql_query("SELECT * FROM requests", conn)
    conn.close()

    filename = "requests_report.xlsx"
    df.to_excel(filename, index=False)

    return send_file(filename, as_attachment=True)

# ===================== EXPORT PDF ======================

@app.route("/export/pdf")
@login_required
def export_pdf():
    filename = "requests_report.pdf"
    c = canvas.Canvas(filename)
    c.setFont("Helvetica", 10)

    y = 800
    c.drawString(50, y, "تقرير طلبات المشتريات")
    y -= 30

    conn = get_db_connection()
    rows = conn.execute("SELECT * FROM requests").fetchall()
    conn.close()

    for r in rows:
        c.drawString(50, y, f"#{r['id']} | {r['requester_name']} | {r['estimated_total']}")
        y -= 20

    c.save()
    return send_file(filename, as_attachment=True)

# ===================== MAIN ============================

app.jinja_env.globals.update(current_user=current_user)

if __name__ == "__main__":
    init_db()
    app.run(debug=True)
