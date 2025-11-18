import os
import sqlite3
from datetime import datetime

from flask import (
    Flask, render_template, request, redirect,
    url_for, session, flash, send_from_directory, send_file, jsonify
)

from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

import pandas as pd
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

import logging
from logging.handlers import RotatingFileHandler
from functools import wraps

# ============================================================
#                   إعدادات النظام العامة
# ============================================================

app = Flask(__name__)
app.secret_key = "CHANGE_THIS_TO_A_REAL_SECRET_KEY"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DB_PATH = os.path.join(BASE_DIR, "database.db")
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
LOG_FOLDER = os.path.join(BASE_DIR, "logs")

ALLOWED_EXTENSIONS = {"pdf", "png", "jpg", "jpeg"}

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(LOG_FOLDER, exist_ok=True)

# ============================================================
#                   إعدادات البريد الإلكتروني
# ============================================================

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587
SMTP_USER = "financial.affairs@hu.edu.iq"   # يمكنك تغييره
SMTP_PASS = "APP_PASSWORD_HERE"             # كلمة مرور التطبيق

def send_email(to, subject, body):
    """
    ترسل إيميل HTML مع تسجيل الحدث في اللوغ.
    إذا حدث خطأ لا يتوقف التطبيق.
    """
    if not SMTP_USER or not SMTP_PASS:
        app.logger.warning("SMTP disabled or not configured; email not sent.")
        return False

    msg = MIMEMultipart()
    msg["From"] = SMTP_USER
    msg["To"] = to
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "html"))

    try:
        server = smtplib.SMTP(SMTP_HOST, SMTP_PORT)
        server.starttls()
        server.login(SMTP_USER, SMTP_PASS)
        server.sendmail(SMTP_USER, to, msg.as_string())
        server.quit()

        app.logger.info(f"📨 Email sent to {to} | {subject}")
        return True

    except Exception as e:
        app.logger.error(f"❌ Email error: {str(e)}")
        return False

# ============================================================
#                   إعداد Logging احترافي
# ============================================================

log_handler = RotatingFileHandler(
    os.path.join(LOG_FOLDER, "app.log"),
    maxBytes=5_000_000,
    backupCount=3,
    encoding="utf-8"
)

log_formatter = logging.Formatter(
    "%(asctime)s | %(levelname)s | %(message)s"
)

log_handler.setFormatter(log_formatter)
log_handler.setLevel(logging.INFO)

app.logger.addHandler(log_handler)
app.logger.setLevel(logging.INFO)
app.logger.info("🔥 Hadbaa Finance Portal v2.0 started")

# ============================================================
#                   دوال قاعدة البيانات
# ============================================================

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()

    # جدول المستخدمين (الأدوار)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            full_name TEXT,
            email TEXT,
            password_hash TEXT,
            role TEXT
        )
    """)

    # جدول أنواع المصروفات
    conn.execute("""
        CREATE TABLE IF NOT EXISTS expense_types (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            description TEXT,
            created_at TEXT
        )
    """)

    # جدول الطلبات
    conn.execute("""
        CREATE TABLE IF NOT EXISTS requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            requester_id INTEGER,
            requester_name TEXT,
            department TEXT,
            email TEXT,
            job_title TEXT,
            item_description TEXT,
            category TEXT,
            quantity INTEGER,
            unit TEXT,
            specs TEXT,
            justification TEXT,
            estimated_total REAL,
            status TEXT,
            created_at TEXT,
            expense_type_id INTEGER
        )
    """)

    # محاولة إضافة العمود الجديد إذا كانت قاعدة قديمة
    try:
        cols = conn.execute("PRAGMA table_info(requests)").fetchall()
        col_names = [c["name"] for c in cols]
        if "expense_type_id" not in col_names:
            conn.execute("ALTER TABLE requests ADD COLUMN expense_type_id INTEGER")
            app.logger.info("✅ Added expense_type_id column to requests")
    except Exception as e:
        app.logger.warning(f"Skipping ALTER TABLE requests: {e}")

    # مرفقات الطلب
    conn.execute("""
        CREATE TABLE IF NOT EXISTS attachments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            request_id INTEGER,
            filename TEXT
        )
    """)

    # سجل الصرف (أمين الصندوق)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS disbursements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            request_id INTEGER,
            amount REAL,
            receipt_no TEXT,
            receipt_date TEXT,
            file TEXT
        )
    """)

    conn.commit()

    # إنشاء المستخدمين الأساسيين لأول مرة
    seed_users(conn)
    seed_expense_types(conn)

    conn.close()
    app.logger.info("📚 Database initialized")

# ============================================================
#             إنشاء المستخدمين الأساسيين (Seed Users)
# ============================================================

def seed_users(conn):
    default_users = [
        ("requester",        "موظف طلبات",         "req@hu.edu.iq",       "123456", "requester"),
        ("fund_manager",     "مدير صندوق المالية", "fund@hu.edu.iq",      "123456", "fund_manager"),
        ("finance_manager",  "مدير الشؤون المالية","finance@hu.edu.iq",   "123456", "finance_manager"),
        ("president",        "رئيس الجامعة",        "president@hu.edu.iq", "123456", "president"),
        ("cashier",          "أمين الصندوق",        "cashier@hu.edu.iq",   "123456", "cashier"),
    ]

    for username, full_name, email, pwd, role in default_users:
        check = conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
        if check is None:
            conn.execute(
                "INSERT INTO users (username,full_name,email,password_hash,role) VALUES (?,?,?,?,?)",
                (username, full_name, email, generate_password_hash(pwd), role)
            )
            conn.commit()
            app.logger.info(f"👤 User created: {username} ({role})")

# ============================================================
#           إنشاء أنواع مصروفات افتراضية (Seed Expense Types)
# ============================================================

def seed_expense_types(conn):
    defaults = [
        "تشغيلية عامة",
        "أثاث وتجهيزات",
        "مواد مختبرية",
        "صيانة وتجهيز",
        "خدمات خارجية",
        "اشتراكات وأنظمة",
        "تطوير تقني",
        "أخرى"
    ]
    for name in defaults:
        check = conn.execute(
            "SELECT * FROM expense_types WHERE name=?", (name,)
        ).fetchone()
        if check is None:
            conn.execute(
                "INSERT INTO expense_types (name, description, created_at) VALUES (?, ?, ?)",
                (name, None, datetime.now().strftime("%Y-%m-%d %H:%M"))
            )
            conn.commit()
            app.logger.info(f"💡 Expense type created: {name}")

# ============================================================
#                دوال مساعدة (Helpers)
# ============================================================

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def current_user():
    """
    يرجع بيانات المستخدم المسجل دخوله حالياً.
    """
    if "user_id" not in session:
        return None

    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE id=?", (session["user_id"],)).fetchone()
    conn.close()
    return user

# ============================================================
#                حماية الصفحات (Login / Role)
# ============================================================

def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            flash("يجب تسجيل الدخول أولاً", "warning")
            return redirect(url_for("login"))
        return fn(*args, **kwargs)
    return wrapper


def role_required(*roles):
    """
    مثال الاستخدام:
    @role_required("finance_manager", "president")
    """
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            user = current_user()
            if user is None or user["role"] not in roles:
                flash("⚠️ ليست لديك صلاحية الوصول لهذه الصفحة", "danger")
                uname = user["username"] if user else "None"
                app.logger.warning(f"🚫 Unauthorized access attempt by user={uname}")
                return redirect(url_for("dashboard"))
            return fn(*args, **kwargs)
        return wrapper
    return decorator

# ============================================================
#             تسجيل كل طلب HTTP في سجل النظام
# ============================================================

@app.before_request
def log_every_request():
    app.logger.info(
        f"➡️ HTTP Request | METHOD={request.method} | PATH={request.path} | IP={request.remote_addr}"
    )

# ============================================================
#                      تسجيل الدخول
# ============================================================

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = (request.form.get("password") or "").strip()

        conn = get_db()
        user = conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
        conn.close()

        if user and check_password_hash(user["password_hash"], password):
            session["user_id"] = user["id"]
            app.logger.info(f"✅ Login success for user={username}")
            return redirect(url_for("dashboard"))
        else:
            flash("❌ اسم المستخدم أو كلمة المرور غير صحيحة", "danger")
            app.logger.warning(f"❌ Login failed for username={username}")

    return render_template("login.html", user=current_user())

# ============================================================
#                      تسجيل الخروج
# ============================================================

@app.route("/logout")
def logout():
    user = current_user()
    if user:
        app.logger.info(f"👋 Logout by user={user['username']}")
    session.clear()
    flash("تم تسجيل الخروج", "info")
    return redirect(url_for("login"))

# ============================================================
#                   لوحة التحكم (Dashboard)
# ============================================================

@app.route("/")
@login_required
def dashboard():
    user = current_user()

    conn = get_db()

    # إحصائيات الطلبات
    stats = conn.execute("""
        SELECT status, COUNT(*) AS c
        FROM requests
        GROUP BY status
    """).fetchall()

    # أحدث 5 طلبات للمستخدم (إن كان مقدم طلب)
    if user["role"] == "requester":
        my_requests = conn.execute("""
            SELECT *
            FROM requests
            WHERE requester_id=?
            ORDER BY created_at DESC
            LIMIT 5
        """, (user["id"],)).fetchall()
    else:
        my_requests = []

    conn.close()

    return render_template(
        "dashboard.html",
        user=user,
        stats=stats,
        my_requests=my_requests
    )

# ============================================================
#         تحديد المرحلة الأولى للموافقة حسب مبلغ الطلب
# ============================================================

def determine_next_approver(amount: float) -> str:
    """
    مراحل الموافقات حسب المبلغ:
    - ≤ 2,000,000  → مدير صندوق المالية (fund_manager)
    - ≤ 20,000,000 → مدير الشؤون المالية (finance_manager)
    - > 20,000,000 → رئيس الجامعة (president)
    """
    if amount <= 2_000_000:
        return "fund_manager"
    elif amount <= 20_000_000:
        return "finance_manager"
    else:
        return "president"

# ============================================================
#                     إنشاء طلب جديد
# ============================================================

@app.route("/requests/new", methods=["GET", "POST"])
@login_required
@role_required("requester")
def new_request():
    user = current_user()   # بيانات المستخدم الحالي

    conn = get_db()
    expense_types = conn.execute(
        "SELECT * FROM expense_types ORDER BY name"
    ).fetchall()
    conn.close()

    if request.method == "POST":
        f = request.form
        estimated_total = float(f.get("estimated_total", "0") or 0)

        # تحديد مرحلة الموافقة المطلوبة
        next_approver = determine_next_approver(estimated_total)

        expense_type_id = f.get("expense_type_id") or None
        if expense_type_id:
            try:
                expense_type_id = int(expense_type_id)
            except ValueError:
                expense_type_id = None

        conn = get_db()
        conn.execute("""
            INSERT INTO requests (
                requester_id, requester_name, department, email, job_title,
                item_description, category, quantity, unit, specs, justification,
                estimated_total, status, created_at, expense_type_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            user["id"], f.get("requester_name"), f.get("department"), f.get("email"),
            f.get("job_title"), f.get("item_description"), f.get("category"),
            f.get("quantity"), f.get("unit"), f.get("specs"), f.get("justification"),
            estimated_total, f"pending_{next_approver}",
            datetime.now().strftime("%Y-%m-%d %H:%M"),
            expense_type_id
        ))

        rid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        # رفع مرفق الطلب
        file = request.files.get("attachment")
        if file and allowed_file(file.filename):
            folder = os.path.join(UPLOAD_FOLDER, f"request_{rid}")
            os.makedirs(folder, exist_ok=True)

            filename = secure_filename(file.filename)
            file.save(os.path.join(folder, filename))

            conn.execute(
                "INSERT INTO attachments (request_id, filename) VALUES (?, ?)",
                (rid, filename)
            )
            app.logger.info(f"📎 Attachment uploaded for request #{rid}: {filename}")

        conn.commit()
        conn.close()

        # إشعار بريد إلكتروني لصاحب الطلب
        if f.get("email"):
            send_email(
                f.get("email"),
                f"تم استلام طلبك #{rid}",
                f"""
                <h3>تم استلام طلبك</h3>
                <p>رقم الطلب: <b>{rid}</b></p>
                <p>قيد التحويل للمراجعة.</p>
                """
            )

        app.logger.info(
            f"📝 New request #{rid} created by {user['username']} | amount={estimated_total}"
        )

        flash("✔️ تم إرسال الطلب بنجاح", "success")
        return redirect(url_for("dashboard"))

    return render_template("new_request.html", user=user, expense_types=expense_types)

# ============================================================
#           عرض الطلبات للمستخدم حسب دوره
# ============================================================

@app.route("/requests")
@login_required
def list_requests():
    user = current_user()
    conn = get_db()

    if user["role"] == "requester":
        rows = conn.execute(
            "SELECT r.*, e.name AS expense_type_name "
            "FROM requests r "
            "LEFT JOIN expense_types e ON r.expense_type_id = e.id "
            "WHERE requester_id=? "
            "ORDER BY created_at DESC",
            (user["id"],)
        ).fetchall()

    elif user["role"] == "fund_manager":
        rows = conn.execute(
            "SELECT r.*, e.name AS expense_type_name "
            "FROM requests r "
            "LEFT JOIN expense_types e ON r.expense_type_id = e.id "
            "WHERE status='pending_fund_manager' "
            "ORDER BY created_at",
        ).fetchall()

    elif user["role"] == "finance_manager":
        rows = conn.execute(
            "SELECT r.*, e.name AS expense_type_name "
            "FROM requests r "
            "LEFT JOIN expense_types e ON r.expense_type_id = e.id "
            "WHERE status='pending_finance_manager' "
            "ORDER BY created_at",
        ).fetchall()

    elif user["role"] == "president":
        rows = conn.execute(
            "SELECT r.*, e.name AS expense_type_name "
            "FROM requests r "
            "LEFT JOIN expense_types e ON r.expense_type_id = e.id "
            "WHERE status='pending_president' "
            "ORDER BY created_at",
        ).fetchall()

    elif user["role"] == "cashier":
        rows = conn.execute(
            "SELECT r.*, e.name AS expense_type_name "
            "FROM requests r "
            "LEFT JOIN expense_types e ON r.expense_type_id = e.id "
            "WHERE status='approved_to_cashier' "
            "ORDER BY created_at",
        ).fetchall()

    else:
        rows = []

    conn.close()
    return render_template("requests_list.html", user=user, rows=rows)

# ============================================================
#                 اتخاذ القرار (Approve / Reject)
# ============================================================

@app.route("/requests/<int:rid>/decision", methods=["POST"])
@login_required
def request_decision(rid):
    user = current_user()
    action = request.form.get("action")  # approve / reject

    conn = get_db()
    row = conn.execute("SELECT * FROM requests WHERE id=?", (rid,)).fetchone()

    if not row:
        conn.close()
        flash("❌ الطلب غير موجود", "danger")
        return redirect(url_for("list_requests"))

    status = row["status"]
    requester_email = row["email"]

    # المرحلة الحالية تطلب هذا الدور تحديدًا
    required_role = None
    if status == "pending_fund_manager":
        required_role = "fund_manager"
    elif status == "pending_finance_manager":
        required_role = "finance_manager"
    elif status == "pending_president":
        required_role = "president"

    if required_role and user["role"] != required_role:
        conn.close()
        flash("⚠️ لا تملك صلاحية اتخاذ القرار على هذا الطلب", "danger")
        app.logger.warning(
            f"🚫 Unauthorized decision attempt on request #{rid} by user={user['username']}"
        )
        return redirect(url_for("list_requests"))

    if action == "approve":
        next_status = "approved_to_cashier"

        conn.execute(
            "UPDATE requests SET status=? WHERE id=?",
            (next_status, rid)
        )
        conn.commit()
        conn.close()

        if requester_email:
            send_email(
                requester_email,
                f"تمت الموافقة على طلبك #{rid}",
                f"""
                <h3>موافقة الطلب</h3>
                <p>تمت الموافقة على طلبك رقم <b>{rid}</b> وتحويله إلى أمين الصندوق للصرف.</p>
                """
            )

        app.logger.info(
            f"✔ APPROVED | Request #{rid} by {user['username']} | Next Status={next_status}"
        )
        flash("✔️ تمت الموافقة على الطلب", "success")
        return redirect(url_for("list_requests"))

    elif action == "reject":
        conn.execute(
            "UPDATE requests SET status='rejected' WHERE id=?",
            (rid,)
        )
        conn.commit()
        conn.close()

        if requester_email:
            send_email(
                requester_email,
                f"تم رفض طلبك #{rid}",
                f"""
                <h3>رفض الطلب</h3>
                <p>نأسف، تم رفض طلبك رقم <b>{rid}</b>.</p>
                <p>يرجى مراجعة قسم الشؤون المالية.</p>
                """
            )

        app.logger.info(
            f"❌ REJECTED | Request #{rid} by {user['username']}"
        )
        flash("❌ تم رفض الطلب", "warning")
        return redirect(url_for("list_requests"))

    else:
        conn.close()
        flash("إجراء غير معروف", "danger")
        return redirect(url_for("list_requests"))

# ============================================================
#              لوحة أمين الصندوق (الطلبات الجاهزة للصرف)
# ============================================================

@app.route("/cashier")
@login_required
@role_required("cashier")
def cashier_dashboard():
    conn = get_db()
    rows = conn.execute("""
        SELECT r.*, e.name AS expense_type_name
        FROM requests r
        LEFT JOIN expense_types e ON r.expense_type_id = e.id
        WHERE status='approved_to_cashier'
        ORDER BY created_at
    """).fetchall()
    conn.close()

    return render_template("cashier.html", rows=rows, user=current_user())

# ============================================================
#                     صفحة صرف الطلب (Disbursement)
# ============================================================

@app.route("/cashier/disburse/<int:rid>", methods=["GET", "POST"])
@login_required
@role_required("cashier")
def disburse(rid):
    user = current_user()

    conn = get_db()
    row = conn.execute("SELECT * FROM requests WHERE id=?", (rid,)).fetchone()
    conn.close()

    if not row:
        flash("❌ الطلب غير موجود", "danger")
        return redirect(url_for("cashier_dashboard"))

    requester_email = row["email"]

    if request.method == "POST":
        f = request.form
        amount = float(f.get("amount", "0") or 0)
        receipt_no = f.get("receipt_no")
        receipt_date = f.get("receipt_date")

        file = request.files.get("attachment")
        filename = None

        if file and allowed_file(file.filename):
            folder = os.path.join(UPLOAD_FOLDER, f"disb_{rid}")
            os.makedirs(folder, exist_ok=True)

            filename = secure_filename(file.filename)
            file.save(os.path.join(folder, filename))

        conn = get_db()
        conn.execute("""
            INSERT INTO disbursements (
                request_id, amount, receipt_no, receipt_date, file
            ) VALUES (?, ?, ?, ?, ?)
        """, (rid, amount, receipt_no, receipt_date, filename))

        conn.execute("""
            UPDATE requests
            SET status='paid'
            WHERE id=?
        """, (rid,))

        conn.commit()
        conn.close()

        if requester_email:
            send_email(
                requester_email,
                f"تم صرف طلبك #{rid}",
                f"""
                <h3>تم صرف المبلغ</h3>
                <p>تم صرف طلبك رقم <b>{rid}</b>.</p>
                <p>رقم الوصل: <b>{receipt_no}</b></p>
                <p>تاريخ الصرف: {receipt_date}</p>
                """
            )

        app.logger.info(
            f"💵 DISBURSEMENT | Request #{rid} | Amount={amount} | Cashier={user['username']}"
        )

        flash("✔️ تم تسجيل عملية الصرف بنجاح", "success")
        return redirect(url_for("cashier_dashboard"))

    return render_template("disburse.html", rid=rid, user=user)

# ============================================================
#           عرض وتحميل مرفقات الطلب
# ============================================================

@app.route("/attachments/<int:rid>/<filename>")
@login_required
def download_attachment(rid, filename):
    folder = os.path.join(UPLOAD_FOLDER, f"request_{rid}")
    return send_from_directory(folder, filename, as_attachment=True)


@app.route("/disb_attachments/<int:rid>/<filename>")
@login_required
def download_disb_attachment(rid, filename):
    folder = os.path.join(UPLOAD_FOLDER, f"disb_{rid}")
    return send_from_directory(folder, filename, as_attachment=True)

# ============================================================
#                     صفحة التقارير الرئيسية
# ============================================================

@app.route("/reports")
@login_required
def reports_home():
    return render_template("reports.html", user=current_user())

@app.route("/reports/unpaid")
@login_required
def report_unpaid():
    conn = get_db()
    rows = conn.execute("""
        SELECT * FROM requests WHERE status='approved_to_cashier'
    """).fetchall()
    conn.close()

    if not rows:
        flash("لا توجد طلبات غير مصروفة", "info")
        return redirect(url_for("reports_home"))

    df = pd.DataFrame(rows)
    file_path = os.path.join(BASE_DIR, "report_unpaid.xlsx")
    df.to_excel(file_path, index=False)

    app.logger.info("📊 Excel report generated: unpaid")
    return send_file(file_path, as_attachment=True)

@app.route("/reports/rejected")
@login_required
def report_rejected():
    conn = get_db()
    rows = conn.execute("""
        SELECT * FROM requests WHERE status='rejected'
    """).fetchall()
    conn.close()

    if not rows:
        flash("لا توجد طلبات مرفوضة", "info")
        return redirect(url_for("reports_home"))

    df = pd.DataFrame(rows)
    file_path = os.path.join(BASE_DIR, "report_rejected.xlsx")
    df.to_excel(file_path, index=False)

    app.logger.info("📊 Excel report generated: rejected")
    return send_file(file_path, as_attachment=True)

@app.route("/reports/pending")
@login_required
def report_pending():
    conn = get_db()
    rows = conn.execute("""
        SELECT * FROM requests
        WHERE status LIKE 'pending_%'
    """).fetchall()
    conn.close()

    if not rows:
        flash("لا توجد طلبات قيد المراجعة", "info")
        return redirect(url_for("reports_home"))

    df = pd.DataFrame(rows)
    file_path = os.path.join(BASE_DIR, "report_pending.xlsx")
    df.to_excel(file_path, index=False)

    app.logger.info("📊 Excel report generated: pending")
    return send_file(file_path, as_attachment=True)

@app.route("/reports/paid")
@login_required
def report_paid():
    conn = get_db()
    rows = conn.execute("""
        SELECT * FROM requests WHERE status='paid'
    """).fetchall()
    conn.close()

    if not rows:
        flash("لا توجد طلبات مدفوعة", "info")
        return redirect(url_for("reports_home"))

    df = pd.DataFrame(rows)
    file_path = os.path.join(BASE_DIR, "report_paid.xlsx")
    df.to_excel(file_path, index=False)

    app.logger.info("📊 Excel report generated: paid")
    return send_file(file_path, as_attachment=True)

# ============================================================
#               إدارة أنواع المصروفات (CRUD)
# ============================================================

@app.route("/expense-types", methods=["GET", "POST"])
@login_required
@role_required("finance_manager", "president")
def expense_types():
    user = current_user()
    conn = get_db()

    if request.method == "POST" and user["role"] == "finance_manager":
        name = (request.form.get("name") or "").strip()
        desc = (request.form.get("description") or "").strip() or None

        if not name:
            flash("يجب إدخال اسم نوع المصروف", "danger")
        else:
            try:
                conn.execute("""
                    INSERT INTO expense_types (name, description, created_at)
                    VALUES (?, ?, ?)
                """, (name, desc, datetime.now().strftime("%Y-%m-%d %H:%M")))
                conn.commit()
                flash("✔️ تم إضافة نوع المصروف", "success")
                app.logger.info(f"💡 Expense type added: {name}")
            except sqlite3.IntegrityError:
                flash("⚠️ هذا النوع موجود مسبقًا", "warning")

    types = conn.execute("""
        SELECT
            t.*,
            (SELECT COUNT(*) FROM requests r WHERE r.expense_type_id = t.id) AS usage_count
        FROM expense_types t
        ORDER BY t.name
    """).fetchall()

    conn.close()
    return render_template("expense_types.html", user=user, types=types)

@app.route("/expense-types/<int:tid>/delete", methods=["POST"])
@login_required
@role_required("finance_manager")
def delete_expense_type(tid):
    conn = get_db()
    usage = conn.execute(
        "SELECT COUNT(*) AS c FROM requests WHERE expense_type_id=?",
        (tid,)
    ).fetchone()["c"]

    if usage > 0:
        flash("⚠️ لا يمكن حذف نوع مستخدم في طلبات. يمكنك تعديله فقط.", "warning")
        conn.close()
        return redirect(url_for("expense_types"))

    conn.execute("DELETE FROM expense_types WHERE id=?", (tid,))
    conn.commit()
    conn.close()

    app.logger.info(f"🗑 Expense type deleted: id={tid}")
    flash("✔️ تم حذف نوع المصروف", "success")
    return redirect(url_for("expense_types"))

@app.route("/expense-types/<int:tid>/update", methods=["POST"])
@login_required
@role_required("finance_manager")
def update_expense_type(tid):
    name = (request.form.get("name") or "").strip()
    desc = (request.form.get("description") or "").strip() or None

    if not name:
        flash("يجب إدخال اسم النوع", "danger")
        return redirect(url_for("expense_types"))

    conn = get_db()
    try:
        conn.execute("""
            UPDATE expense_types
            SET name=?, description=?
            WHERE id=?
        """, (name, desc, tid))
        conn.commit()
        flash("✔️ تم تعديل نوع المصروف", "success")
        app.logger.info(f"✏️ Expense type updated: id={tid} name={name}")
    except sqlite3.IntegrityError:
        flash("⚠️ يوجد نوع آخر بنفس الاسم", "warning")
    finally:
        conn.close()

    return redirect(url_for("expense_types"))

# ============================================================
#            لوحة التحليل المالي (Analytics Dashboard)
# ============================================================

@app.route("/analytics")
@login_required
@role_required("finance_manager", "president")
def analytics():
    user = current_user()
    conn = get_db()

    # بيانات أساسية من disbursements + requests
    rows = conn.execute("""
        SELECT
            r.id,
            r.department,
            r.category,
            r.item_description,
            r.created_at,
            r.status,
            r.expense_type_id,
            e.name AS expense_type_name,
            d.amount,
            d.receipt_date
        FROM disbursements d
        JOIN requests r ON r.id = d.request_id
        LEFT JOIN expense_types e ON r.expense_type_id = e.id
        WHERE r.status='paid'
    """).fetchall()

    # تحويل لِـ DataFrame لتحليل أسهل
    if rows:
        df = pd.DataFrame(rows, columns=rows[0].keys())
    else:
        df = pd.DataFrame(columns=[
            "id", "department", "category", "item_description",
            "created_at", "status", "expense_type_id",
            "expense_type_name", "amount", "receipt_date"
        ])

    # KPIs
    total_spent = float(df["amount"].sum()) if not df.empty else 0.0
    total_paid_requests = int(df["id"].nunique()) if not df.empty else 0
    top_department = None
    top_expense_type = None

    # توزيع حسب القسم
    dept_data = []
    if not df.empty:
        dept_group = df.groupby("department")["amount"].sum().reset_index()
        dept_group = dept_group.sort_values("amount", ascending=False)
        dept_data = dept_group.to_dict(orient="records")
        if not dept_group.empty:
            top_department = dept_group.iloc[0]["department"]

    # توزيع حسب نوع المصروف
    type_data = []
    if not df.empty:
        type_group = df.groupby("expense_type_name")["amount"].sum().reset_index()
        type_group = type_group.sort_values("amount", ascending=False)
        type_data = type_group.to_dict(orient="records")
        if not type_group.empty:
            top_expense_type = type_group.iloc[0]["expense_type_name"]

    # مصروف شهري
    monthly_data = []
    trend_data = []
    if not df.empty:
        df["month"] = pd.to_datetime(df["receipt_date"]).dt.strftime("%Y-%m")
        month_group = df.groupby("month")["amount"].sum().reset_index()
        month_group = month_group.sort_values("month")
        monthly_data = month_group.to_dict(orient="records")
        trend_data = monthly_data

    # أعلى 10 أنواع مصروفات
    top_types_table = type_data[:10] if type_data else []

    # أعلى 10 أقسام
    top_dept_table = dept_data[:10] if dept_data else []

    conn.close()

    return render_template(
        "analytics.html",
        user=user,
        total_spent=total_spent,
        total_paid_requests=total_paid_requests,
        top_department=top_department,
        top_expense_type=top_expense_type,
        dept_data=dept_data,
        type_data=type_data,
        monthly_data=monthly_data,
        trend_data=trend_data,
        top_types_table=top_types_table,
        top_dept_table=top_dept_table
    )

# ============================================================
#                       تشغيل التطبيق
# ============================================================

if __name__ == "__main__":
    init_db()
    # ليتوافق مع Codespaces أو أي سيرفر
    app.run(host="0.0.0.0", port=5000, debug=True)
