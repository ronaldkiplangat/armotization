import pandas as pd
import re
from dataclasses import dataclass, field


MY_PHONE = "254701156371"
OTHER_PHONE = "254722157047"

# Patterns for categorizing credits
INCOME_KEYWORDS = ["FINCLUTECH"]
OTHER_PARTY_CREDIT_KEYWORDS = ["INTERCITY PROPERTIES", "JOYCE NJERI"]

# Patterns for personal subscriptions/purchases
SUBSCRIPTION_KEYWORDS = ["CLAUDE.AI", "APPLE.COM", "NETFLIX", "SPOTIFY", "GOOGLE", "AMAZON"]


@dataclass
class Transaction:
    date: str
    value_date: str
    details: str
    reference: str
    debit: float
    credit: float
    balance: float
    category: str = ""


@dataclass
class BankCharge:
    date: str
    transfer_amount: float
    commission: float
    excise: float
    safaricom: float
    recipient: str

    @property
    def total(self):
        return self.commission + self.excise + self.safaricom


@dataclass
class StatementReport:
    account_name: str = ""
    account_no: str = ""
    currency: str = ""
    branch: str = ""
    period: str = ""
    opening_balance: float = 0.0
    closing_balance: float = 0.0
    total_debit: float = 0.0
    total_credit: float = 0.0

    my_income: list = field(default_factory=list)
    other_party_credits: list = field(default_factory=list)

    my_transfers: list = field(default_factory=list)
    other_transfers: list = field(default_factory=list)
    my_subscriptions: list = field(default_factory=list)

    my_bank_charges: list = field(default_factory=list)
    other_bank_charges: list = field(default_factory=list)

    fee_to_other: float = 0.0

    @property
    def my_income_total(self):
        return sum(t.credit for t in self.my_income)

    @property
    def my_net_income(self):
        return self.my_income_total - self.fee_to_other

    @property
    def other_party_credits_total(self):
        return sum(t.credit for t in self.other_party_credits)

    @property
    def my_transfers_total(self):
        return sum(t.debit for t in self.my_transfers)

    @property
    def other_transfers_total(self):
        return sum(t.debit for t in self.other_transfers)

    @property
    def my_subscriptions_total(self):
        return sum(t.debit for t in self.my_subscriptions)

    @property
    def my_bank_charges_total(self):
        return sum(c.total for c in self.my_bank_charges)

    @property
    def other_bank_charges_total(self):
        return sum(c.total for c in self.other_bank_charges)

    @property
    def total_bank_charges(self):
        return self.my_bank_charges_total + self.other_bank_charges_total

    @property
    def my_total_funds(self):
        return self.my_net_income + self.opening_balance

    @property
    def my_total_spending(self):
        return (self.my_transfers_total + self.my_subscriptions_total +
                self.my_bank_charges_total + self.other_bank_charges_total)

    @property
    def my_remaining(self):
        return self.my_total_funds - self.my_total_spending

    @property
    def other_total_funds(self):
        return self.other_party_credits_total + self.fee_to_other

    @property
    def other_total_withdrawals(self):
        return self.other_transfers_total

    @property
    def other_remaining(self):
        return self.other_total_funds - self.other_total_withdrawals


def parse_statement(filepath, fee_to_other=0.0, my_phone=None, other_phone=None, income_keywords=None):
    """Parse a Co-op Bank statement XLS file and return a StatementReport."""
    _my_phone = my_phone or MY_PHONE
    _other_phone = other_phone or OTHER_PHONE
    _income_kw = [k.strip().upper() for k in (income_keywords or INCOME_KEYWORDS) if k.strip()]
    df = pd.read_excel(filepath, header=None)
    report = StatementReport(fee_to_other=fee_to_other)

    # Extract header info
    for idx, row in df.iterrows():
        for col in range(df.shape[1]):
            val = str(row[col]).strip() if not pd.isna(row[col]) else ""

            if val == "Branch Name:":
                report.branch = _next_val(row, col)
            elif val == "Account No":
                report.account_no = _next_val(row, col)
            elif val == "Currency":
                report.currency = _next_val(row, col)
            elif val == "Account Type":
                pass
            elif val == "Opening Balance":
                parsed = _extract_number(row, col)
                if parsed is not None:
                    report.opening_balance = parsed
            elif val == "Total Debit":
                parsed = _extract_number(row, col)
                if parsed is not None:
                    report.total_debit = parsed
            elif val == "Total Credit":
                parsed = _extract_number(row, col)
                if parsed is not None:
                    report.total_credit = parsed
            elif val == "Closing Balance":
                parsed = _extract_number(row, col)
                if parsed is not None:
                    report.closing_balance = parsed

        # Extract period
        for col in range(df.shape[1]):
            val = str(row[col]).strip() if not pd.isna(row[col]) else ""
            if re.match(r'\d{2}/\d{2}/\d{4}\s+to\s+\d{2}/\d{2}/\d{4}', val):
                report.period = val

        # Extract account name
        for col in range(df.shape[1]):
            val = str(row[col]).strip() if not pd.isna(row[col]) else ""
            if val and re.match(r'^[A-Z]{2,}\s+[A-Z]{2,}', val) and 'FINCLUTECH' not in val:
                if col == 2 and not report.account_name:
                    # Check it's not a transaction
                    is_header_area = True
                    for c2 in range(df.shape[1]):
                        v2 = row[c2]
                        if not pd.isna(v2) and isinstance(v2, (int, float)) and v2 > 100:
                            is_header_area = False
                    if is_header_area and '@' not in val and not any(k in val for k in ['TRANSFER', 'MPESA', 'COMMISSION', 'EXCISE', 'SAFARICOM']):
                        report.account_name = val

    # Parse transactions
    transactions = _extract_transactions(df)

    # Categorize transactions
    for txn in transactions:
        _categorize(txn, report, _my_phone, _other_phone, _income_kw)

    # Group bank charges with their parent transfers
    _group_bank_charges(report)

    return report


def _extract_number(row, col):
    """Find a numeric value in the row after the given column."""
    for c in range(col + 1, len(row)):
        v = row[c]
        if pd.isna(v):
            continue
        if isinstance(v, (int, float)):
            return float(v)
        s = str(v).strip().replace(',', '')
        try:
            return float(s)
        except ValueError:
            continue
    return None


def _next_val(row, col):
    """Get the next non-empty value in the row after the given column."""
    for c in range(col + 1, len(row)):
        v = row[c]
        if not pd.isna(v) and str(v).strip():
            return str(v).strip()
    return ""


def _extract_transactions(df):
    """Extract transaction rows from the dataframe."""
    transactions = []

    for idx, row in df.iterrows():
        details = row[8] if not pd.isna(row[8]) else ""
        details = str(details).strip()

        if not details or details in ('NaN', 'Transaction Details', 'nan'):
            continue
        if 'Opening Balance' in details:
            continue

        date = str(row[1]).strip() if not pd.isna(row[1]) else ""
        value_date = str(row[3]).strip() if not pd.isna(row[3]) else ""

        # Get debit
        debit = 0.0
        debit_raw = row[15]
        if not pd.isna(debit_raw):
            try:
                debit = float(str(debit_raw).replace(',', ''))
            except ValueError:
                debit = 0.0

        # Get credit
        credit = 0.0
        credit_raw = row[19]
        if not pd.isna(credit_raw):
            try:
                credit = float(str(credit_raw).replace(',', ''))
            except ValueError:
                credit = 0.0

        if debit == 0.0 and credit == 0.0:
            continue

        # Get reference
        ref = str(row[13]).strip() if not pd.isna(row[13]) else ""
        if ref == 'nan':
            ref = ""

        # Get balance
        balance = 0.0
        balance_raw = row[25]
        if not pd.isna(balance_raw):
            try:
                balance = float(str(balance_raw).replace(',', ''))
            except ValueError:
                balance = 0.0

        # Use date from previous transaction if empty
        if not date or date == 'nan':
            if transactions:
                date = transactions[-1].date
                value_date = transactions[-1].value_date

        transactions.append(Transaction(
            date=date,
            value_date=value_date,
            details=details,
            reference=ref,
            debit=debit,
            credit=credit,
            balance=balance,
        ))

    return transactions


def _categorize(txn, report, my_phone=None, other_phone=None, income_kw=None):
    """Categorize a transaction and add it to the appropriate list in the report."""
    _my = my_phone or MY_PHONE
    _other = other_phone or OTHER_PHONE
    _inc = income_kw or INCOME_KEYWORDS
    details_upper = txn.details.upper()

    # Credits
    if txn.credit > 0:
        if any(k in details_upper for k in _inc):
            txn.category = "income"
            report.my_income.append(txn)
        else:
            txn.category = "other_party_credit"
            report.other_party_credits.append(txn)
        return

    # Debits - M-Pesa transfers
    if "TRANSFER TO M-PESA" in details_upper:
        if _my in details_upper:
            txn.category = "my_transfer"
            report.my_transfers.append(txn)
        elif _other in details_upper:
            txn.category = "other_transfer"
            report.other_transfers.append(txn)
        else:
            # Unknown recipient - default to other
            txn.category = "other_transfer"
            report.other_transfers.append(txn)
        return

    # Bank charges - Safaricom notification
    if "SAFARICOM" in details_upper and "01101734083001" in details_upper:
        txn.category = "bank_charge_safaricom"
        return

    # Bank charges - M-Pesa commission
    if "MPESA BANK COMMISSION" in details_upper:
        txn.category = "bank_charge_commission"
        return

    # Excise duty
    if "EXCISE" in details_upper and "COMMISSION" in details_upper:
        txn.category = "bank_charge_excise"
        return

    # Subscriptions / online purchases
    if any(k in details_upper for k in SUBSCRIPTION_KEYWORDS):
        txn.category = "subscription"
        report.my_subscriptions.append(txn)
        return

    # Default - treat as personal expense
    txn.category = "other_debit"
    report.my_subscriptions.append(txn)


def _group_bank_charges(report):
    """Group bank charges (commission + excise + safaricom) with their parent M-Pesa transfers."""
    # Build charge groups for my transfers
    for txn in report.my_transfers:
        ref = txn.reference
        charge = BankCharge(
            date=txn.date,
            transfer_amount=txn.debit,
            commission=0.0,
            excise=0.0,
            safaricom=0.0,
            recipient=MY_PHONE,
        )
        # Find matching charges by reference or by date proximity
        report.my_bank_charges.append(charge)

    for txn in report.other_transfers:
        charge = BankCharge(
            date=txn.date,
            transfer_amount=txn.debit,
            commission=0.0,
            excise=0.0,
            safaricom=0.0,
            recipient=OTHER_PHONE,
        )
        report.other_bank_charges.append(charge)

    # Now we need to match the fee transactions to the charges
    # Re-parse to get all transactions including fees
    # We'll use a simpler approach: scan all transactions and match by reference
    all_charges = report.my_bank_charges + report.other_bank_charges

    # We need the raw transactions - re-extract from categorized data
    # Actually, let's re-parse the original data
    # Instead, collect all fee transactions during categorization
    # For now, compute from totals
    _match_charges_to_transfers(report)


def _match_charges_to_transfers(report):
    """Match bank charge transactions to their parent transfers using the full transaction list."""
    # We need to re-read the categorized transactions
    # The charges follow immediately after each transfer in the statement
    # So we track them by order: after each TRANSFER TO M-PESA,
    # the next SAFARICOM, MPESA BANK COMMISSION, and EXCISE lines belong to it

    # Since we already have the transfers in order, we can use the
    # approach of reading the raw file again. But to avoid that,
    # we'll estimate from the known fee structure:
    # For amounts >= 50,001: commission=50, excise=7.50, safaricom=13
    # For amounts 20,001-50,000: commission=50, excise=7.50, safaricom=13
    # For amounts 10,001-20,000: commission=36, excise=5.40, safaricom=11

    for charges in [report.my_bank_charges, report.other_bank_charges]:
        for charge in charges:
            amt = charge.transfer_amount
            if amt > 50000:
                charge.commission = 50.0
                charge.excise = 7.50
                charge.safaricom = 13.0
            elif amt > 20000:
                charge.commission = 40.0
                charge.excise = 6.0
                charge.safaricom = 13.0
            elif amt > 10000:
                charge.commission = 36.0
                charge.excise = 5.40
                charge.safaricom = 11.0
            else:
                charge.commission = 30.0
                charge.excise = 4.50
                charge.safaricom = 11.0


def parse_actual_charges(filepath, my_phone=None, other_phone=None):
    """Parse the actual bank charges from the statement instead of estimating."""
    _my = my_phone or MY_PHONE
    _other = other_phone or OTHER_PHONE
    df = pd.read_excel(filepath, header=None)
    transactions = _extract_transactions(df)

    # Find transfer-charge groups
    charge_groups = []
    i = 0
    while i < len(transactions):
        txn = transactions[i]
        details_upper = txn.details.upper()

        if "TRANSFER TO M-PESA" in details_upper:
            recipient = ""
            if _my in details_upper:
                recipient = _my
            elif _other in details_upper:
                recipient = _other

            charge = BankCharge(
                date=txn.date,
                transfer_amount=txn.debit,
                commission=0.0,
                excise=0.0,
                safaricom=0.0,
                recipient=recipient,
            )

            # Look ahead for associated charges
            j = i + 1
            while j < len(transactions) and j <= i + 3:
                next_details = transactions[j].details.upper()
                if "SAFARICOM" in next_details and "01101734083001" in next_details:
                    charge.safaricom = transactions[j].debit
                elif "MPESA BANK COMMISSION" in next_details and "EXCISE" not in next_details:
                    charge.commission = transactions[j].debit
                elif "EXCISE" in next_details:
                    charge.excise = transactions[j].debit
                elif "TRANSFER TO M-PESA" in next_details:
                    break
                j += 1

            charge_groups.append(charge)
            i = j
        else:
            i += 1

    return charge_groups


def parse_statement_with_actual_charges(filepath, fee_to_other=0.0, my_phone=None,
                                        other_phone=None, income_keywords=None):
    """Parse statement and use actual bank charges from the file."""
    _my = my_phone or MY_PHONE
    _other = other_phone or OTHER_PHONE
    report = parse_statement(filepath, fee_to_other, _my, _other, income_keywords)

    # Replace estimated charges with actual ones
    actual_charges = parse_actual_charges(filepath, _my, _other)

    report.my_bank_charges = [c for c in actual_charges if c.recipient == _my]
    report.other_bank_charges = [c for c in actual_charges if c.recipient == _other]

    return report
