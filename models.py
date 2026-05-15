from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

db = SQLAlchemy()


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # User's config
    display_name = db.Column(db.String(80), default="")
    other_name = db.Column(db.String(80), default="")
    my_phone = db.Column(db.String(20), default="254701156371")
    other_phone = db.Column(db.String(20), default="254722157047")
    income_keywords = db.Column(db.String(500), default="FINCLUTECH")

    statements = db.relationship("StatementRecord", backref="user", lazy=True,
                                 order_by="StatementRecord.uploaded_at.desc()")

    def set_password(self, password):
        self.password_hash = generate_password_hash(password, method="pbkdf2:sha256")

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class StatementRecord(db.Model):
    __tablename__ = "statements"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Period
    period = db.Column(db.String(50))
    account_name = db.Column(db.String(100))
    account_no = db.Column(db.String(30))
    currency = db.Column(db.String(10))
    branch = db.Column(db.String(50))

    # Summary figures
    opening_balance = db.Column(db.Float, default=0.0)
    closing_balance = db.Column(db.Float, default=0.0)
    total_debit = db.Column(db.Float, default=0.0)
    total_credit = db.Column(db.Float, default=0.0)

    # Split figures
    fee_to_other = db.Column(db.Float, default=0.0)
    my_income_total = db.Column(db.Float, default=0.0)
    my_net_income = db.Column(db.Float, default=0.0)
    other_party_credits_total = db.Column(db.Float, default=0.0)
    my_transfers_total = db.Column(db.Float, default=0.0)
    other_transfers_total = db.Column(db.Float, default=0.0)
    my_subscriptions_total = db.Column(db.Float, default=0.0)
    my_bank_charges_total = db.Column(db.Float, default=0.0)
    other_bank_charges_total = db.Column(db.Float, default=0.0)
    my_remaining = db.Column(db.Float, default=0.0)
    other_remaining = db.Column(db.Float, default=0.0)

    # Store full report as JSON for detailed view
    report_json = db.Column(db.Text)

    @property
    def is_verified(self):
        return abs(self.my_remaining + self.other_remaining - self.closing_balance) < 0.02


class AuditLog(db.Model):
    __tablename__ = "audit_logs"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    action = db.Column(db.String(50), nullable=False)   # login, logout, upload, view_report, delete_report, login_failed
    detail = db.Column(db.String(500), default="")
    ip_address = db.Column(db.String(45), default="")
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship("User", backref=db.backref("audit_logs", lazy=True))

    @property
    def display_name(self):
        return self.user.display_name if self.user else "Unknown"
