import os
import json
from flask import Flask, render_template, request, redirect, flash, url_for
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.utils import secure_filename
from models import db, User, StatementRecord, AuditLog
from parser import parse_statement_with_actual_charges

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "coop-statement-splitter-2026")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
ALLOWED_EXTENSIONS = {"xls", "xlsx"}

database_url = os.environ.get(
    "DATABASE_URL",
    f"sqlite:///{os.path.join(BASE_DIR, 'armotization.db')}"
)
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)
app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

db.init_app(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"
login_manager.login_message_category = "info"


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


def log_event(action, detail="", user_id=None):
    """Write an audit log entry."""
    entry = AuditLog(
        user_id=user_id or (current_user.id if current_user and current_user.is_authenticated else None),
        action=action,
        detail=detail,
        ip_address=request.remote_addr or "",
    )
    db.session.add(entry)
    db.session.commit()


def seed_users():
    """Create default Ronald and Hillary accounts if they don't exist."""
    if not User.query.filter_by(username="ronald").first():
        ronald = User(
            username="ronald",
            email="ronaldkiplangat@gmail.com",
            display_name="Ronald",
            other_name="Hillary",
            my_phone="254701156371",
            other_phone="254722157047",
            income_keywords="FINCLUTECH",
        )
        ronald.set_password("ronald2026")
        db.session.add(ronald)

    if not User.query.filter_by(username="hillary").first():
        hillary = User(
            username="hillary",
            email="hillary@gmail.com",
            display_name="Hillary",
            other_name="Ronald",
            my_phone="254722157047",
            other_phone="254701156371",
            income_keywords="INTERCITY PROPERTIES,JOYCE NJERI",
        )
        hillary.set_password("hillary2026")
        db.session.add(hillary)

    db.session.commit()


with app.app_context():
    db.create_all()
    seed_users()


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


# ──────────────────────────────────────────
# Auth routes
# ──────────────────────────────────────────

@app.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        display_name = request.form.get("display_name", "").strip()
        other_name = request.form.get("other_name", "").strip()
        my_phone = request.form.get("my_phone", "").strip()
        other_phone = request.form.get("other_phone", "").strip()

        if not username or not email or not password or not display_name:
            flash("All fields are required")
            return redirect(url_for("register"))

        if User.query.filter((User.username == username) | (User.email == email)).first():
            flash("Username or email already taken")
            return redirect(url_for("register"))

        user = User(
            username=username, email=email,
            display_name=display_name, other_name=other_name,
            my_phone=my_phone, other_phone=other_phone,
        )
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        login_user(user)
        log_event("register", f"New account: {username}")
        return redirect(url_for("dashboard"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user, remember=True)
            log_event("login", f"{user.display_name} logged in")
            next_page = request.args.get("next")
            return redirect(next_page or url_for("dashboard"))

        # Log failed attempt
        log_event("login_failed", f"Failed login for username: {username}",
                  user_id=user.id if user else None)
        flash("Invalid username or password")
        return redirect(url_for("login"))

    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    log_event("logout", f"{current_user.display_name} logged out")
    logout_user()
    flash("Logged out")
    return redirect(url_for("login"))


# ──────────────────────────────────────────
# Dashboard & Settings
# ──────────────────────────────────────────

@app.route("/")
@login_required
def dashboard():
    my_statements = StatementRecord.query.filter_by(user_id=current_user.id)\
        .order_by(StatementRecord.uploaded_at.desc()).all()

    partner = User.query.filter_by(my_phone=current_user.other_phone).first()
    shared_statements = []
    if partner:
        shared_statements = StatementRecord.query.filter_by(user_id=partner.id)\
            .order_by(StatementRecord.uploaded_at.desc()).all()

    return render_template("dashboard.html", statements=my_statements,
                           shared_statements=shared_statements,
                           partner=partner)


@app.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    if request.method == "POST":
        current_user.display_name = request.form.get("display_name", current_user.display_name).strip()
        current_user.other_name = request.form.get("other_name", current_user.other_name).strip()
        current_user.my_phone = request.form.get("my_phone", current_user.my_phone).strip()
        current_user.other_phone = request.form.get("other_phone", current_user.other_phone).strip()
        current_user.income_keywords = request.form.get("income_keywords", current_user.income_keywords).strip()
        db.session.commit()
        flash("Settings updated")
        return redirect(url_for("settings"))
    return render_template("settings.html")


@app.route("/audit")
@login_required
def audit_log():
    logs = AuditLog.query.order_by(AuditLog.timestamp.desc()).limit(200).all()
    return render_template("audit.html", logs=logs)


# ──────────────────────────────────────────
# Upload & Report
# ──────────────────────────────────────────

@app.route("/upload", methods=["GET", "POST"])
@login_required
def upload():
    if request.method == "GET":
        return render_template("upload.html")

    if "statement" not in request.files:
        flash("No file selected")
        return redirect(url_for("upload"))

    file = request.files["statement"]
    if file.filename == "":
        flash("No file selected")
        return redirect(url_for("upload"))

    if not allowed_file(file.filename):
        flash("Only .xls and .xlsx files are supported")
        return redirect(url_for("upload"))

    fee_to_other = request.form.get("fee_to_other", "0")
    try:
        fee_to_other = float(fee_to_other.replace(",", ""))
    except ValueError:
        fee_to_other = 0.0

    filename = secure_filename(file.filename)
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    file.save(filepath)

    try:
        report = parse_statement_with_actual_charges(
            filepath, fee_to_other,
            my_phone=current_user.my_phone,
            other_phone=current_user.other_phone,
            income_keywords=current_user.income_keywords.split(","),
        )

        report_data = _report_to_dict(report)

        # Check for existing record with same filename — regenerate instead of duplicate
        existing = StatementRecord.query.filter_by(
            user_id=current_user.id, filename=filename
        ).first()

        if existing:
            record = existing
            record.uploaded_at = db.func.now()
            action_label = "regenerated"
        else:
            record = StatementRecord(user_id=current_user.id, filename=filename)
            db.session.add(record)
            action_label = "uploaded"

        record.period = report.period
        record.account_name = report.account_name
        record.account_no = report.account_no
        record.currency = report.currency
        record.branch = report.branch
        record.opening_balance = report.opening_balance
        record.closing_balance = report.closing_balance
        record.total_debit = report.total_debit
        record.total_credit = report.total_credit
        record.fee_to_other = report.fee_to_other
        record.my_income_total = report.my_income_total
        record.my_net_income = report.my_net_income
        record.other_party_credits_total = report.other_party_credits_total
        record.my_transfers_total = report.my_transfers_total
        record.other_transfers_total = report.other_transfers_total
        record.my_subscriptions_total = report.my_subscriptions_total
        record.my_bank_charges_total = report.my_bank_charges_total
        record.other_bank_charges_total = report.other_bank_charges_total
        record.my_remaining = report.my_remaining
        record.other_remaining = report.other_remaining
        record.report_json = json.dumps(report_data)

        db.session.commit()

        log_event("upload", f"Statement {action_label}: {filename} (period: {report.period})")

        if action_label == "regenerated":
            flash(f"Statement regenerated (replaced existing {filename})")

        return redirect(url_for("view_report", record_id=record.id))

    except Exception as e:
        flash(f"Error parsing statement: {e}")
        return redirect(url_for("upload"))


@app.route("/report/<int:record_id>")
@login_required
def view_report(record_id):
    record = StatementRecord.query.get_or_404(record_id)
    owner = db.session.get(User, record.user_id)

    is_owner = (record.user_id == current_user.id)
    is_partner = (not is_owner and owner
                  and current_user.my_phone == owner.other_phone)

    if not is_owner and not is_partner:
        flash("Unauthorized")
        return redirect(url_for("dashboard"))

    log_event("view_report", f"Viewed report #{record.id} ({record.filename})")

    report_data = json.loads(record.report_json)

    return render_template("report.html", r=report_data, record=record,
                           my_name=owner.display_name,
                           other_name=owner.other_name,
                           my_phone=owner.my_phone,
                           other_phone=owner.other_phone,
                           is_owner=is_owner)


@app.route("/report/<int:record_id>/delete", methods=["POST"])
@login_required
def delete_report(record_id):
    record = StatementRecord.query.get_or_404(record_id)
    if record.user_id != current_user.id:
        flash("Unauthorized")
        return redirect(url_for("dashboard"))

    log_event("delete_report", f"Deleted report #{record.id} ({record.filename})")
    db.session.delete(record)
    db.session.commit()
    flash("Statement deleted")
    return redirect(url_for("dashboard"))


# ──────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────

def _report_to_dict(report):
    """Convert a StatementReport to a JSON-serializable dict."""

    def txn_list(txns):
        return [{"date": t.date, "details": t.details, "debit": t.debit,
                 "credit": t.credit, "balance": t.balance, "reference": t.reference}
                for t in txns]

    def charge_list(charges):
        return [{"date": c.date, "transfer_amount": c.transfer_amount,
                 "commission": c.commission, "excise": c.excise,
                 "safaricom": c.safaricom, "total": c.total, "recipient": c.recipient}
                for c in charges]

    return {
        "account_name": report.account_name,
        "account_no": report.account_no,
        "currency": report.currency,
        "branch": report.branch,
        "period": report.period,
        "opening_balance": report.opening_balance,
        "closing_balance": report.closing_balance,
        "total_debit": report.total_debit,
        "total_credit": report.total_credit,
        "fee_to_other": report.fee_to_other,
        "my_income": txn_list(report.my_income),
        "my_income_total": report.my_income_total,
        "my_net_income": report.my_net_income,
        "other_party_credits": txn_list(report.other_party_credits),
        "other_party_credits_total": report.other_party_credits_total,
        "my_transfers": txn_list(report.my_transfers),
        "my_transfers_total": report.my_transfers_total,
        "other_transfers": txn_list(report.other_transfers),
        "other_transfers_total": report.other_transfers_total,
        "my_subscriptions": txn_list(report.my_subscriptions),
        "my_subscriptions_total": report.my_subscriptions_total,
        "my_bank_charges": charge_list(report.my_bank_charges),
        "my_bank_charges_total": report.my_bank_charges_total,
        "other_bank_charges": charge_list(report.other_bank_charges),
        "other_bank_charges_total": report.other_bank_charges_total,
        "my_total_funds": report.my_total_funds,
        "my_total_spending": report.my_total_spending,
        "my_remaining": report.my_remaining,
        "other_total_funds": report.other_total_funds,
        "other_total_withdrawals": report.other_total_withdrawals,
        "other_remaining": report.other_remaining,
    }


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 5050)))
