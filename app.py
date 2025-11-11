
from flask import Flask, render_template, request, redirect, url_for
import sqlite3
from datetime import datetime
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "database.db")

app = Flask(__name__)


def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        \"\"\"
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
            created_at TEXT NOT NULL
        )
        \"\"\"
    )
    conn.commit()
    conn.close()


def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def determine_approver_title(amount):
    \"\"\"Return approver title based on Iraqi private university thresholds.\"\"\"
    # لحد 2,000,000 دينار: مدير صندوق المالية
    # من 2,000,001 إلى 20,000,000 دينار: مدير الشؤون المالية
    # أكثر من 20,000,000 دينار: رئيس الجامعة
    if amount <= 2_000_000:
        return "مدير صندوق المالية"
    elif amount <= 20_000_000:
        return "مدير الشؤون المالية"
    else:
        return "رئيس الجامعة"


@app.route("/")
def index():
    return redirect(url_for("list_requests"))


@app.route("/requests")
def list_requests():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM requests ORDER BY created_at DESC")
    rows = cur.fetchall()
    conn.close()
    return render_template("requests_list.html", requests=rows)


@app.route("/requests/new", methods=["GET", "POST"])
def new_request():
    if request.method == "POST":
        requester_name = request.form.get("requester_name", "").strip()
        department = request.form.get("department", "").strip()
        email = request.form.get("email", "").strip()
        job_title = request.form.get("job_title", "").strip()
        item_description = request.form.get("item_description", "").strip()
        category = request.form.get("category", "").strip()
        quantity = request.form.get("quantity", "0").strip() or "0"
        unit = request.form.get("unit", "").strip()
        specs = request.form.get("specs", "").strip()
        justification = request.form.get("justification", "").strip()
        estimated_total_raw = request.form.get("estimated_total", "0").replace(",", "").strip() or "0"
        try:
            estimated_total = float(estimated_total_raw)
        except ValueError:
            estimated_total = 0.0

        approver_title = determine_approver_title(estimated_total)
        created_at = datetime.now().strftime("%Y-%m-%d %H:%M")
        status = "قيد التدقيق"

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            \"\"\"
            INSERT INTO requests (
                requester_name, department, email, job_title,
                item_description, category, quantity, unit,
                specs, justification, estimated_total,
                approver_title, status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            \"\"\",
            (
                requester_name, department, email, job_title,
                item_description, category, int(quantity or 0), unit,
                specs, justification, estimated_total,
                approver_title, status, created_at
            )
        )
        conn.commit()
        conn.close()

        return redirect(url_for("list_requests"))

    return render_template("new_request.html")


@app.route("/requests/<int:req_id>")
def request_detail(req_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM requests WHERE id = ?", (req_id,))
    row = cur.fetchone()
    conn.close()
    if row is None:
        return "الطلب غير موجود", 404
    return render_template("request_detail.html", req=row)


@app.route("/requests/<int:req_id>/update_status", methods=["POST"])
def update_status(req_id):
    new_status = request.form.get("status", "").strip()
    if new_status not in ("موافق", "مرفوض", "قيد التدقيق"):
        return "حالة غير صالحة", 400

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("UPDATE requests SET status = ? WHERE id = ?", (new_status, req_id))
    conn.commit()
    conn.close()

    return redirect(url_for("request_detail", req_id=req_id))


if __name__ == "__main__":
    init_db()
    app.run(debug=True)
