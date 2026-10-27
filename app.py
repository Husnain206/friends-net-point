import os, sqlite3, csv, io
from urllib.parse import quote
from datetime import date, datetime
from functools import wraps
from flask import Flask, g, request, redirect, url_for, render_template, session, flash, send_file
from werkzeug.security import generate_password_hash, check_password_hash

APP_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("FNP_DB_PATH", os.path.join(APP_DIR, "friends_net_point.db"))
app = Flask(__name__)
app.secret_key = os.environ.get("FNP_SECRET_KEY", "CHANGE-THIS-TO-A-LONG-RANDOM-SECRET-BEFORE-DEPLOYING")

def db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db

@app.teardown_appcontext
def close_db(exc):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS users (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      username TEXT UNIQUE NOT NULL,
      password_hash TEXT NOT NULL,
      role TEXT NOT NULL DEFAULT 'admin',
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS packages (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      name TEXT NOT NULL,
      speed TEXT NOT NULL DEFAULT '',
      monthly_fee REAL NOT NULL DEFAULT 0,
      active INTEGER NOT NULL DEFAULT 1
    );
    CREATE TABLE IF NOT EXISTS customers (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      customer_code TEXT UNIQUE,
      name TEXT NOT NULL,
      father_name TEXT DEFAULT '',
      phone TEXT DEFAULT '',
      address TEXT DEFAULT '',
      area TEXT DEFAULT '',
      package_id INTEGER,
      install_date TEXT DEFAULT '',
      status TEXT NOT NULL DEFAULT 'Active',
      notes TEXT DEFAULT '',
      opening_balance REAL NOT NULL DEFAULT 0,
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      FOREIGN KEY(package_id) REFERENCES packages(id) ON DELETE SET NULL
    );
    CREATE TABLE IF NOT EXISTS bills (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      customer_id INTEGER NOT NULL,
      bill_month TEXT NOT NULL,
      amount REAL NOT NULL DEFAULT 0,
      previous_balance REAL NOT NULL DEFAULT 0,
      total_due REAL NOT NULL DEFAULT 0,
      due_date TEXT DEFAULT '',
      status TEXT NOT NULL DEFAULT 'Unpaid',
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      UNIQUE(customer_id, bill_month),
      FOREIGN KEY(customer_id) REFERENCES customers(id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS payments (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      customer_id INTEGER NOT NULL,
      bill_id INTEGER,
      amount REAL NOT NULL,
      payment_date TEXT NOT NULL,
      method TEXT NOT NULL DEFAULT 'Cash',
      reference TEXT DEFAULT '',
      notes TEXT DEFAULT '',
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      FOREIGN KEY(customer_id) REFERENCES customers(id) ON DELETE CASCADE,
      FOREIGN KEY(bill_id) REFERENCES bills(id) ON DELETE SET NULL
    );
    CREATE TABLE IF NOT EXISTS sms_log (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      customer_id INTEGER,
      phone TEXT NOT NULL,
      message TEXT NOT NULL,
      status TEXT NOT NULL DEFAULT 'Not configured',
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      FOREIGN KEY(customer_id) REFERENCES customers(id) ON DELETE SET NULL
    );
    """)
    # Safe migration for databases created by earlier versions.
    customer_columns = [row[1] for row in conn.execute("PRAGMA table_info(customers)").fetchall()]
    if "opening_balance" not in customer_columns:
        conn.execute("ALTER TABLE customers ADD COLUMN opening_balance REAL NOT NULL DEFAULT 0")
    count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    if count == 0:
        username = os.environ.get("FNP_ADMIN_USER", "admin")
        password = os.environ.get("FNP_ADMIN_PASSWORD", "ChangeMe123!")
        conn.execute("INSERT INTO users(username,password_hash,role) VALUES(?,?,?)",
                     (username, generate_password_hash(password), "admin"))
    conn.commit()
    conn.close()

def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("login"))
        return fn(*args, **kwargs)
    return wrapper

def money(v):
    return f"Rs. {float(v or 0):,.2f}"
app.jinja_env.filters["money"] = money

@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user_id"):
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        username = request.form.get("username","").strip()
        password = request.form.get("password","")
        user = db().execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            session["role"] = user["role"]
            return redirect(url_for("dashboard"))
        flash("Username ya password ghalat hai.", "error")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/")
@login_required
def dashboard():
    conn = db()
    total = conn.execute("SELECT COUNT(*) FROM customers").fetchone()[0]
    active = conn.execute("SELECT COUNT(*) FROM customers WHERE status='Active'").fetchone()[0]
    due = conn.execute("SELECT COALESCE(SUM(total_due),0) FROM bills WHERE status='Unpaid'").fetchone()[0]
    month = date.today().strftime("%Y-%m")
    received = conn.execute("SELECT COALESCE(SUM(amount),0) FROM payments WHERE substr(payment_date,1,7)=?", (month,)).fetchone()[0]
    recent = conn.execute("""SELECT p.*, c.name, c.customer_code FROM payments p
                             JOIN customers c ON c.id=p.customer_id
                             ORDER BY p.id DESC LIMIT 8""").fetchall()
    return render_template("dashboard.html", total=total, active=active, due=due, received=received, recent=recent)

@app.route("/customers")
@login_required
def customers():
    q = request.args.get("q","").strip()
    sql = """SELECT c.*, p.name AS package_name, p.monthly_fee,
             (c.opening_balance + COALESCE((SELECT SUM(b.total_due) FROM bills b WHERE b.customer_id=c.id),0)
              - COALESCE((SELECT SUM(pay.amount) FROM payments pay WHERE pay.customer_id=c.id),0)) AS current_balance
             FROM customers c LEFT JOIN packages p ON p.id=c.package_id"""
    params = []
    if q:
        sql += " WHERE c.name LIKE ? OR c.phone LIKE ? OR c.customer_code LIKE ? OR c.address LIKE ?"
        params = [f"%{q}%"]*4
    sql += " ORDER BY c.id DESC"
    rows = db().execute(sql, params).fetchall()
    return render_template("customers.html", customers=rows, q=q)

@app.route("/customers/add", methods=["GET","POST"])
@app.route("/customers/<int:customer_id>/edit", methods=["GET","POST"])
@login_required
def customer_form(customer_id=None):
    conn = db()
    customer = conn.execute("SELECT * FROM customers WHERE id=?", (customer_id,)).fetchone() if customer_id else None
    if customer_id and not customer:
        flash("Customer nahi mila.", "error")
        return redirect(url_for("customers"))
    packages = conn.execute("SELECT * FROM packages WHERE active=1 ORDER BY name").fetchall()
    if request.method == "POST":
        data = {k: request.form.get(k,"").strip() for k in ["customer_code","name","phone","address","area","install_date","status","notes"]}
        package_id = request.form.get("package_id") or None
        try:
            opening_balance = float(request.form.get("opening_balance", "0") or 0)
        except ValueError:
            opening_balance = -1
        if opening_balance < 0:
            flash("Previous balance 0 ya us se zyada enter karein.", "error")
            return render_template("customer_form.html", customer=customer, packages=packages)
        if not data["name"]:
            flash("Customer ka naam zaroori hai.", "error")
            return render_template("customer_form.html", customer=customer, packages=packages)
        try:
            if customer:
                conn.execute("""UPDATE customers SET customer_code=?,name=?,father_name=?,phone=?,address=?,area=?,
                                package_id=?,install_date=?,status=?,notes=?,opening_balance=? WHERE id=?""",
                             (data["customer_code"] or None,data["name"],"",data["phone"],data["address"],
                              data["area"],package_id,data["install_date"],data["status"],data["notes"],opening_balance,customer_id))
            else:
                cur = conn.execute("""INSERT INTO customers(customer_code,name,father_name,phone,address,area,package_id,install_date,status,notes,opening_balance)
                                VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                             (data["customer_code"] or None,data["name"],"",data["phone"],data["address"],
                              data["area"],package_id,data["install_date"],data["status"],data["notes"],opening_balance))
                new_customer_id = cur.lastrowid
                payment_status = request.form.get("payment_status", "Unpaid")
                pkg = conn.execute("SELECT monthly_fee FROM packages WHERE id=?", (package_id,)).fetchone() if package_id else None
                if pkg:
                    current_month = date.today().strftime("%Y-%m")
                    due_date = current_month + "-05"
                    total_due = float(pkg["monthly_fee"] or 0) + opening_balance
                    cur_bill = conn.execute("""INSERT INTO bills(customer_id,bill_month,amount,previous_balance,total_due,due_date,status)
                                      VALUES(?,?,?,?,?,?,?)""",
                                    (new_customer_id,current_month,float(pkg["monthly_fee"] or 0),opening_balance,total_due,due_date,
                                     "Paid" if payment_status == "Paid" else "Unpaid"))
                    if payment_status == "Paid" and total_due > 0:
                        conn.execute("INSERT INTO payments(customer_id,bill_id,amount,payment_date,method,notes) VALUES(?,?,?,?,?,?)",
                                     (new_customer_id,cur_bill.lastrowid,total_due,date.today().isoformat(),"Cash","Initial payment marked Paid while adding customer"))
            conn.commit()
            flash("Customer save ho gaya.", "success")
            return redirect(url_for("customers"))
        except sqlite3.IntegrityError:
            flash("Customer code duplicate hai. Doosra code dein.", "error")
    return render_template("customer_form.html", customer=customer, packages=packages)

@app.route("/customers/<int:customer_id>")
@login_required
def customer_detail(customer_id):
    conn = db()
    c = conn.execute("""SELECT c.*, p.name AS package_name, p.speed, p.monthly_fee FROM customers c
                        LEFT JOIN packages p ON p.id=c.package_id WHERE c.id=?""", (customer_id,)).fetchone()
    if not c:
        flash("Customer nahi mila.", "error")
        return redirect(url_for("customers"))
    bills = conn.execute("SELECT * FROM bills WHERE customer_id=? ORDER BY bill_month DESC", (customer_id,)).fetchall()
    payments = conn.execute("SELECT * FROM payments WHERE customer_id=? ORDER BY payment_date DESC, id DESC LIMIT 30", (customer_id,)).fetchall()
    billed = conn.execute("SELECT COALESCE(SUM(total_due),0) FROM bills WHERE customer_id=?", (customer_id,)).fetchone()[0]
    paid_total = conn.execute("SELECT COALESCE(SUM(amount),0) FROM payments WHERE customer_id=?", (customer_id,)).fetchone()[0]
    current_balance = float(c["opening_balance"] or 0) + float(billed) - float(paid_total)
    latest_payment = payments[0] if payments else None
    latest_bill = bills[0] if bills else None
    phone_digits = ''.join(ch for ch in (c["phone"] or '') if ch.isdigit())
    if phone_digits.startswith('0'):
        phone_digits = '92' + phone_digits[1:]
    elif phone_digits and not phone_digits.startswith('92'):
        phone_digits = '92' + phone_digits
    wa_lines = [f"*FNP | Friends Net Point*", f"Dear {c['name']},"]
    if latest_bill:
        wa_lines += [f"Bill: {latest_bill['bill_month']}", f"Bill amount: Rs. {float(latest_bill['total_due']):,.0f}", f"Bill status: {latest_bill['status']}"]
    if latest_payment:
        wa_lines += [f"Latest payment received: Rs. {float(latest_payment['amount']):,.0f}", f"Payment date: {latest_payment['payment_date']}"]
    wa_lines += [f"Current outstanding balance: Rs. {current_balance:,.0f}", "Note: This message is only to confirm the amount received and has no connection with any other matter.", "نوٹ: یہ پیغام صرف جمع شدہ رقم کی تصدیق کے لیے ہے۔ اس کا کسی اور معاملے سے کوئی تعلق نہیں۔"]
    wa_url = f"https://wa.me/{phone_digits}?text={quote(chr(10).join(wa_lines))}" if phone_digits else ''
    return render_template("customer_detail.html", c=c, bills=bills, payments=payments, current_balance=current_balance, paid_total=paid_total, wa_url=wa_url)

@app.route("/packages")
@login_required
def packages():
    rows = db().execute("SELECT * FROM packages ORDER BY active DESC, name").fetchall()
    return render_template("packages.html", packages=rows)

@app.route("/packages/add", methods=["GET","POST"])
@app.route("/packages/<int:package_id>/edit", methods=["GET","POST"])
@login_required
def package_form(package_id=None):
    conn = db()
    package = conn.execute("SELECT * FROM packages WHERE id=?", (package_id,)).fetchone() if package_id else None
    if request.method == "POST":
        name = request.form.get("name","").strip()
        speed = request.form.get("speed","").strip()
        try: fee = float(request.form.get("monthly_fee","0") or 0)
        except ValueError: fee = -1
        active = 1 if request.form.get("active") == "on" else 0
        if not name or fee < 0:
            flash("Package name aur sahi fee enter karein.", "error")
        else:
            if package:
                conn.execute("UPDATE packages SET name=?,speed=?,monthly_fee=?,active=? WHERE id=?", (name,speed,fee,active,package_id))
            else:
                conn.execute("INSERT INTO packages(name,speed,monthly_fee,active) VALUES(?,?,?,?)", (name,speed,fee,active))
            conn.commit()
            flash("Package save ho gaya.", "success")
            return redirect(url_for("packages"))
    return render_template("package_form.html", package=package)

@app.route("/bills")
@login_required
def bills():
    month = request.args.get("month", date.today().strftime("%Y-%m"))
    rows = db().execute("""SELECT b.*, c.name, c.customer_code, c.phone FROM bills b
                           JOIN customers c ON c.id=b.customer_id WHERE b.bill_month=?
                           ORDER BY b.status DESC, c.name""", (month,)).fetchall()
    return render_template("bills.html", bills=rows, month=month)

@app.route("/bills/generate", methods=["POST"])
@login_required
def generate_bills():
    month = request.form.get("month", date.today().strftime("%Y-%m"))
    due_date = request.form.get("due_date","")
    if not due_date and len(month) == 7:
        due_date = month + "-05"
    conn = db()
    customers = conn.execute("""SELECT c.id, p.monthly_fee FROM customers c JOIN packages p ON p.id=c.package_id
                                WHERE c.status='Active' AND p.active=1""").fetchall()
    created = 0
    for c in customers:
        previous = conn.execute("""SELECT COALESCE(SUM(total_due),0) FROM bills
                                   WHERE customer_id=? AND status='Unpaid' AND bill_month < ?""", (c["id"],month)).fetchone()[0]
        try:
            conn.execute("""INSERT INTO bills(customer_id,bill_month,amount,previous_balance,total_due,due_date,status)
                            VALUES(?,?,?,?,?,?, 'Unpaid')""",
                         (c["id"],month,c["monthly_fee"],previous,c["monthly_fee"]+previous,due_date))
            created += 1
        except sqlite3.IntegrityError:
            pass
    conn.commit()
    flash(f"{created} naye bills generate hue. Pehle se maujood bills skip kiye gaye.", "success")
    return redirect(url_for("bills", month=month))

@app.route("/bills/<int:bill_id>")
@login_required
def bill_detail(bill_id):
    conn = db()
    b = conn.execute("""SELECT b.*, c.name,c.customer_code,c.phone,c.address,c.area,p.name AS package_name
                        FROM bills b JOIN customers c ON c.id=b.customer_id
                        LEFT JOIN packages p ON p.id=c.package_id WHERE b.id=?""", (bill_id,)).fetchone()
    if not b: return redirect(url_for("bills"))
    payments = conn.execute("SELECT * FROM payments WHERE bill_id=? ORDER BY id DESC", (bill_id,)).fetchall()
    paid = sum(float(x["amount"]) for x in payments)
    remaining = max(float(b["total_due"])-paid, 0)
    phone_digits = ''.join(ch for ch in (b["phone"] or '') if ch.isdigit())
    if phone_digits.startswith('0'):
        phone_digits = '92' + phone_digits[1:]
    elif phone_digits and not phone_digits.startswith('92'):
        phone_digits = '92' + phone_digits
    wa_message = f"*FNP | Friends Net Point*\nDear {b['name']},\nBill month: {b['bill_month']}\nBill amount: Rs. {float(b['total_due']):,.0f}\nPayment received: Rs. {paid:,.0f}\nRemaining balance: Rs. {remaining:,.0f}\nStatus: {b['status']}\nNote: This message is only to confirm the amount received and has no connection with any other matter.\nنوٹ: یہ پیغام صرف جمع شدہ رقم کی تصدیق کے لیے ہے۔ اس کا کسی اور معاملے سے کوئی تعلق نہیں۔"
    wa_url = f"https://wa.me/{phone_digits}?text={quote(wa_message)}" if phone_digits else ''
    return render_template("bill_detail.html", b=b, payments=payments, paid=paid, remaining=remaining, wa_url=wa_url)

@app.route("/payments/add", methods=["GET","POST"])
@login_required
def payment_form():
    conn = db()
    customers = conn.execute("SELECT id,name,customer_code FROM customers ORDER BY name").fetchall()
    selected_customer = request.args.get("customer_id", type=int)
    bills_rows = conn.execute("""SELECT b.*,c.name,c.customer_code FROM bills b JOIN customers c ON c.id=b.customer_id
                                 ORDER BY b.bill_month DESC,c.name""").fetchall()
    if request.method == "POST":
        customer_id = request.form.get("customer_id", type=int)
        bill_id = request.form.get("bill_id", type=int) or None
        try: amount = float(request.form.get("amount","0"))
        except ValueError: amount = 0
        pdate = request.form.get("payment_date") or date.today().isoformat()
        method = request.form.get("method","Cash")
        reference = request.form.get("reference","").strip()
        notes = request.form.get("notes","").strip()
        if not customer_id or amount <= 0:
            flash("Customer aur amount sahi enter karein.", "error")
        else:
            conn.execute("""INSERT INTO payments(customer_id,bill_id,amount,payment_date,method,reference,notes)
                            VALUES(?,?,?,?,?,?,?)""", (customer_id,bill_id,amount,pdate,method,reference,notes))
            if bill_id:
                bill = conn.execute("SELECT total_due FROM bills WHERE id=? AND customer_id=?", (bill_id,customer_id)).fetchone()
                if bill:
                    paid = conn.execute("SELECT COALESCE(SUM(amount),0) FROM payments WHERE bill_id=?", (bill_id,)).fetchone()[0]
                    status = "Paid" if paid >= bill["total_due"] else "Unpaid"
                    conn.execute("UPDATE bills SET status=? WHERE id=?", (status,bill_id))
            conn.commit()
            flash("Payment save ho gayi.", "success")
            return redirect(url_for("payments"))
    return render_template("payment_form.html", customers=customers, bills=bills_rows, selected_customer=selected_customer)

@app.route("/payments")
@login_required
def payments():
    rows = db().execute("""SELECT p.*, c.name,c.customer_code FROM payments p JOIN customers c ON c.id=p.customer_id
                           ORDER BY p.payment_date DESC,p.id DESC LIMIT 500""").fetchall()
    total = sum(float(r["amount"]) for r in rows)
    return render_template("payments.html", payments=rows, total=total)

@app.route("/sms", methods=["GET","POST"])
@login_required
def sms():
    conn = db()
    customers = conn.execute("SELECT id,name,phone,customer_code FROM customers WHERE phone!='' ORDER BY name").fetchall()
    if request.method == "POST":
        customer_id = request.form.get("customer_id", type=int)
        message = request.form.get("message","").strip()
        payment_note = "This slip/SMS is only to confirm the amount received and has no connection with any other matter. / یہ سلپ/SMS صرف جمع شدہ رقم کی تصدیق کے لیے ہے۔ اس کا کسی اور معاملے سے کوئی تعلق نہیں۔"
        if message and payment_note not in message:
            message = message + "\n\n" + payment_note
        c = conn.execute("SELECT * FROM customers WHERE id=?", (customer_id,)).fetchone()
        if not c or not c["phone"] or not message:
            flash("Customer ka mobile number aur message zaroori hai.", "error")
        else:
            # SMS gateway deliberately not configured by default. Log message for setup/testing.
            conn.execute("INSERT INTO sms_log(customer_id,phone,message,status) VALUES(?,?,?,?)",
                         (customer_id,c["phone"],message,"Not sent — SMS gateway not configured"))
            conn.commit()
            flash("Message log ho gaya, lekin SMS asal mein nahi bheja gaya. SMS gateway API configure karni hogi.", "error")
            return redirect(url_for("sms"))
    logs = conn.execute("SELECT s.*,c.name FROM sms_log s LEFT JOIN customers c ON c.id=s.customer_id ORDER BY s.id DESC LIMIT 30").fetchall()
    return render_template("sms.html", customers=customers, logs=logs)

@app.route("/reports")
@login_required
def reports():
    month = request.args.get("month", date.today().strftime("%Y-%m"))
    conn = db()
    income = conn.execute("SELECT COALESCE(SUM(amount),0) FROM payments WHERE substr(payment_date,1,7)=?", (month,)).fetchone()[0]
    billed = conn.execute("SELECT COALESCE(SUM(total_due),0) FROM bills WHERE bill_month=?", (month,)).fetchone()[0]
    unpaid = conn.execute("SELECT COALESCE(SUM(total_due),0) FROM bills WHERE status='Unpaid' AND bill_month=?", (month,)).fetchone()[0]
    count = conn.execute("SELECT COUNT(*) FROM bills WHERE bill_month=?", (month,)).fetchone()[0]
    return render_template("reports.html", month=month, income=income, billed=billed, unpaid=unpaid, count=count)

@app.route("/export/customers.csv")
@login_required
def export_customers():
    rows = db().execute("""SELECT c.customer_code,c.name,c.phone,c.address,c.area,p.name AS package,
                           p.monthly_fee,c.install_date,c.status,c.notes FROM customers c
                           LEFT JOIN packages p ON p.id=c.package_id ORDER BY c.name""").fetchall()
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["Customer Code","Name","Phone","Address","Area","Package","Monthly Fee","Install Date","Status","Notes"])
    for row in rows: writer.writerow(list(row))
    mem = io.BytesIO(("\ufeff"+out.getvalue()).encode("utf-8"))
    return send_file(mem, mimetype="text/csv", as_attachment=True, download_name="friends_net_point_customers.csv")

@app.route("/settings", methods=["GET","POST"])
@login_required
def settings():
    if request.method == "POST":
        current = request.form.get("current_password","")
        new = request.form.get("new_password","")
        confirm = request.form.get("confirm_password","")
        user = db().execute("SELECT * FROM users WHERE id=?", (session["user_id"],)).fetchone()
        if not check_password_hash(user["password_hash"], current):
            flash("Current password ghalat hai.", "error")
        elif len(new) < 10:
            flash("Naya password kam az kam 10 characters ka ho.", "error")
        elif new != confirm:
            flash("Naye passwords match nahi karte.", "error")
        else:
            db().execute("UPDATE users SET password_hash=? WHERE id=?", (generate_password_hash(new), user["id"]))
            db().commit()
            flash("Password update ho gaya.", "success")
            return redirect(url_for("settings"))
    return render_template("settings.html")

if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)
