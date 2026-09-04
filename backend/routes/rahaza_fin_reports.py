"""
PT Rahaza — Phase F1 Finance Reports
Currently: Trial Balance (per account, per period range).
(F2: P&L, Balance Sheet, Journal List; F3: Cash Flow)
"""
from fastapi import APIRouter, Request, HTTPException, Query
from database import get_db
from auth import require_auth, serialize_doc
from datetime import date
from typing import Optional

router = APIRouter(prefix="/api/rahaza/finance/reports", tags=["rahaza-fin-reports"])


@router.get("/trial-balance")
async def trial_balance(
    request: Request,
    from_date: Optional[str] = Query(None, alias="from"),
    to_date: Optional[str] = Query(None, alias="to"),
    show_zero: bool = False,
):
    """Aggregate posted journal lines per account within date range.
    Shows: account_code, account_name, type, total_debit, total_credit, net (debit - credit).
    Opening balance: sum of all lines BEFORE from_date (if provided), then add period movement.
    """
    await require_auth(request)
    db = get_db()
    today = date.today().isoformat()
    if not to_date:
        to_date = today
    # opening range = anything strictly before from_date
    match_period = {"date": {"$lte": to_date}}
    if from_date:
        match_period["date"]["$gte"] = from_date

    # 1) fetch all accounts
    accounts = await db.rahaza_coa_accounts.find({"active": True}, {"_id": 0}).sort("code", 1).to_list(500)

    # 2) Period movement aggregation
    pipeline_period = [
        {"$match": match_period},
        {"$group": {
            "_id": "$account_code",
            "debit": {"$sum": "$debit"},
            "credit": {"$sum": "$credit"},
        }},
    ]
    period_rows = {r["_id"]: r async for r in db.rahaza_journal_lines.aggregate(pipeline_period)}

    # 3) Opening balance aggregation (before from_date)
    opening_rows = {}
    if from_date:
        pipeline_open = [
            {"$match": {"date": {"$lt": from_date}}},
            {"$group": {
                "_id": "$account_code",
                "debit": {"$sum": "$debit"},
                "credit": {"$sum": "$credit"},
            }},
        ]
        opening_rows = {r["_id"]: r async for r in db.rahaza_journal_lines.aggregate(pipeline_open)}

    rows = []
    totals = {"opening_debit": 0, "opening_credit": 0, "period_debit": 0, "period_credit": 0, "end_debit": 0, "end_credit": 0}

    for acc in accounts:
        if acc.get("is_group"):
            continue
        code = acc["code"]
        op = opening_rows.get(code, {"debit": 0, "credit": 0})
        pr = period_rows.get(code, {"debit": 0, "credit": 0})

        opening_net = (op.get("debit", 0) or 0) - (op.get("credit", 0) or 0)
        # Represent opening as debit or credit side based on sign
        if acc["normal_balance"] == "DEBIT":
            opening_debit = max(opening_net, 0)
            opening_credit = max(-opening_net, 0)
        else:
            opening_credit = max(-opening_net, 0) if opening_net < 0 else 0
            opening_debit = max(opening_net, 0) if opening_net > 0 else 0

        period_debit = round(pr.get("debit", 0) or 0, 2)
        period_credit = round(pr.get("credit", 0) or 0, 2)

        end_net = opening_net + (period_debit - period_credit)
        if end_net >= 0:
            end_debit = round(end_net, 2)
            end_credit = 0.0
        else:
            end_debit = 0.0
            end_credit = round(-end_net, 2)

        if not show_zero and (opening_debit + opening_credit + period_debit + period_credit + end_debit + end_credit) == 0:
            continue

        rows.append({
            "code": code,
            "name": acc["name"],
            "type": acc["type"],
            "normal_balance": acc["normal_balance"],
            "opening_debit": round(opening_debit, 2),
            "opening_credit": round(opening_credit, 2),
            "period_debit": period_debit,
            "period_credit": period_credit,
            "end_debit": end_debit,
            "end_credit": end_credit,
        })
        totals["opening_debit"] += round(opening_debit, 2)
        totals["opening_credit"] += round(opening_credit, 2)
        totals["period_debit"] += period_debit
        totals["period_credit"] += period_credit
        totals["end_debit"] += end_debit
        totals["end_credit"] += end_credit

    return {
        "meta": {"from": from_date, "to": to_date},
        "rows": rows,
        "totals": {k: round(v, 2) for k, v in totals.items()},
        "balanced": round(totals["end_debit"], 2) == round(totals["end_credit"], 2),
    }


@router.get("/general-ledger")
async def general_ledger(
    request: Request,
    account_code: str = Query(...),
    from_date: Optional[str] = Query(None, alias="from"),
    to_date: Optional[str] = Query(None, alias="to"),
):
    """Return all lines for a specific account within a date range, with running balance."""
    await require_auth(request)
    db = get_db()
    today = date.today().isoformat()
    if not to_date:
        to_date = today
    acc = await db.rahaza_coa_accounts.find_one({"code": account_code}, {"_id": 0})
    if not acc:
        raise HTTPException(404, f"Akun '{account_code}' tidak ditemukan.")

    # opening balance
    opening_net = 0.0
    if from_date:
        pipe_op = [
            {"$match": {"account_code": account_code, "date": {"$lt": from_date}}},
            {"$group": {"_id": None, "debit": {"$sum": "$debit"}, "credit": {"$sum": "$credit"}}},
        ]
        async for r in db.rahaza_journal_lines.aggregate(pipe_op):
            opening_net = (r.get("debit", 0) or 0) - (r.get("credit", 0) or 0)

    q = {"account_code": account_code}
    if from_date and to_date:
        q["date"] = {"$gte": from_date, "$lte": to_date}
    elif to_date:
        q["date"] = {"$lte": to_date}

    rows_raw = await db.rahaza_journal_lines.find(q, {"_id": 0}).sort([("date", 1), ("created_at", 1)]).to_list(500)

    running = opening_net
    lines = []
    for r in rows_raw:
        running = running + (r.get("debit", 0) or 0) - (r.get("credit", 0) or 0)
        # Convert running to display debit or credit based on normal balance
        if acc["normal_balance"] == "DEBIT":
            balance = running
        else:
            balance = -running
        lines.append({
            "date": r["date"],
            "je_number": r.get("je_number"),
            "description": r.get("description") or "",
            "source": r.get("source_module"),
            "debit": r.get("debit", 0),
            "credit": r.get("credit", 0),
            "balance": round(balance, 2),
        })
    end_balance = lines[-1]["balance"] if lines else (opening_net if acc["normal_balance"] == "DEBIT" else -opening_net)
    return {
        "account": {"code": acc["code"], "name": acc["name"], "type": acc["type"], "normal_balance": acc["normal_balance"]},
        "meta": {"from": from_date, "to": to_date},
        "opening_balance": round((opening_net if acc["normal_balance"] == "DEBIT" else -opening_net), 2),
        "lines": lines,
        "end_balance": round(end_balance, 2),
    }


# ═══════════════════════════════════════════════════════════════════════════
# F2: PROFIT & LOSS / INCOME STATEMENT
# ═══════════════════════════════════════════════════════════════════════════
_BS_KNOWN = {"ASSET", "LIABILITY", "EQUITY", "REVENUE", "COGS", "EXPENSE", "OTHER_INCOME", "OTHER_EXPENSE"}
_BS_LEGACY = {"CURRENT_ASSET": "ASSET", "FIXED_ASSET": "ASSET", "OTHER": "OTHER_INCOME",
              "INCOME": "REVENUE", "CURRENT_LIABILITY": "LIABILITY"}


def _bs_type(acc: dict) -> str:
    """Tipe laporan yang dikenal; tipe legacy/tak dikenal dipetakan (fallback prefix kode)."""
    t = (acc.get("type") or "").upper()
    if t in _BS_KNOWN:
        return t
    if t in _BS_LEGACY:
        return _BS_LEGACY[t]
    return {"1": "ASSET", "2": "LIABILITY", "3": "EQUITY", "4": "REVENUE", "5": "COGS"}.get(
        (acc.get("code") or "")[:1], "EXPENSE")


async def _aggregate_by_account(db, match: dict):
    """Return dict {account_code: {debit, credit}} from posted journal lines."""
    pipeline = [
        {"$match": match},
        {"$group": {
            "_id": "$account_code",
            "debit": {"$sum": "$debit"},
            "credit": {"$sum": "$credit"},
        }},
    ]
    rows = {r["_id"]: r async for r in db.rahaza_journal_lines.aggregate(pipeline)}
    return rows


@router.get("/profit-loss")
async def profit_loss(
    request: Request,
    from_date: Optional[str] = Query(None, alias="from"),
    to_date: Optional[str] = Query(None, alias="to"),
):
    """F2: Income Statement / Profit & Loss.
    Grouping: REVENUE, OTHER_INCOME (credit − debit = income positive)
              COGS, EXPENSE, OTHER_EXPENSE (debit − credit = expense positive)
    Net Income = (Revenue + Other Income) − (COGS + Expense + Other Expense)
    """
    await require_auth(request)
    db = get_db()
    today = date.today().isoformat()
    if not to_date:
        to_date = today
    if not from_date:
        from_date = f"{today[:4]}-01-01"

    match = {"date": {"$gte": from_date, "$lte": to_date}}
    per_acc = await _aggregate_by_account(db, match)

    # Get all leaf accounts for types of interest
    type_groups = {
        "REVENUE": {"label": "Pendapatan", "accounts": []},
        "OTHER_INCOME": {"label": "Pendapatan Lain-lain", "accounts": []},
        "COGS": {"label": "Harga Pokok Penjualan (HPP)", "accounts": []},
        "EXPENSE": {"label": "Beban Operasional", "accounts": []},
        "OTHER_EXPENSE": {"label": "Beban Lain-lain", "accounts": []},
    }
    accounts = await db.rahaza_coa_accounts.find(
        {"type": {"$in": list(type_groups.keys())}, "is_group": False, "active": True},
        {"_id": 0},
    ).sort("code", 1).to_list(500)

    total_revenue = 0.0
    total_other_income = 0.0
    total_cogs = 0.0
    total_expense = 0.0
    total_other_expense = 0.0

    for acc in accounts:
        code = acc["code"]
        agg = per_acc.get(code, {"debit": 0, "credit": 0})
        d = float(agg.get("debit") or 0)
        c = float(agg.get("credit") or 0)
        if acc["type"] in ("REVENUE", "OTHER_INCOME"):
            # income = credit - debit (revenue normal balance = credit)
            amount = round(c - d, 2)
            row = {
                "code": code, "name": acc["name"], "type": acc["type"],
                "amount": amount, "debit": round(d, 2), "credit": round(c, 2),
            }
            type_groups[acc["type"]]["accounts"].append(row)
            if acc["type"] == "REVENUE":
                total_revenue += amount
            else:
                total_other_income += amount
        else:
            # expense/cogs = debit - credit (normal balance = debit)
            amount = round(d - c, 2)
            row = {
                "code": code, "name": acc["name"], "type": acc["type"],
                "amount": amount, "debit": round(d, 2), "credit": round(c, 2),
            }
            type_groups[acc["type"]]["accounts"].append(row)
            if acc["type"] == "COGS":
                total_cogs += amount
            elif acc["type"] == "EXPENSE":
                total_expense += amount
            else:
                total_other_expense += amount

    gross_profit = round(total_revenue - total_cogs, 2)
    operating_income = round(gross_profit - total_expense, 2)
    net_income = round(operating_income + total_other_income - total_other_expense, 2)

    return {
        "meta": {"from": from_date, "to": to_date},
        "groups": {
            "revenue": {"label": type_groups["REVENUE"]["label"], "accounts": type_groups["REVENUE"]["accounts"], "total": round(total_revenue, 2)},
            "cogs": {"label": type_groups["COGS"]["label"], "accounts": type_groups["COGS"]["accounts"], "total": round(total_cogs, 2)},
            "expense": {"label": type_groups["EXPENSE"]["label"], "accounts": type_groups["EXPENSE"]["accounts"], "total": round(total_expense, 2)},
            "other_income": {"label": type_groups["OTHER_INCOME"]["label"], "accounts": type_groups["OTHER_INCOME"]["accounts"], "total": round(total_other_income, 2)},
            "other_expense": {"label": type_groups["OTHER_EXPENSE"]["label"], "accounts": type_groups["OTHER_EXPENSE"]["accounts"], "total": round(total_other_expense, 2)},
        },
        "totals": {
            "revenue": round(total_revenue, 2),
            "cogs": round(total_cogs, 2),
            "gross_profit": gross_profit,
            "expense": round(total_expense, 2),
            "operating_income": operating_income,
            "other_income": round(total_other_income, 2),
            "other_expense": round(total_other_expense, 2),
            "net_income": net_income,
        },
    }


# ═══════════════════════════════════════════════════════════════════════════
# F2: BALANCE SHEET
# ═══════════════════════════════════════════════════════════════════════════
@router.get("/balance-sheet")
async def balance_sheet(
    request: Request,
    as_of: Optional[str] = Query(None),
):
    """F2: Balance Sheet (as of date).
    Assets = Liabilities + Equity.
    Current year earnings derived from P&L net income (YTD up to as_of).
    """
    await require_auth(request)
    db = get_db()
    today = date.today().isoformat()
    if not as_of:
        as_of = today

    # aggregate all posted lines up to as_of
    match = {"date": {"$lte": as_of}}
    per_acc = await _aggregate_by_account(db, match)

    # get leaf accounts for Balance Sheet types + revenue/expense for net income calc
    # C-04: akun NONAKTIF yang punya saldo tetap ikut (kalau tidak, neraca tak seimbang);
    # tipe legacy (CURRENT_ASSET/OTHER/...) dinormalisasi lewat _bs_type().
    accounts = await db.rahaza_coa_accounts.find(
        {"is_group": False},
        {"_id": 0},
    ).sort("code", 1).to_list(5000)

    assets = []
    liabilities = []
    equity = []
    total_assets = 0.0
    total_liabilities = 0.0
    total_equity = 0.0
    # compute net income (same as P&L within YTD)
    total_rev = 0.0
    total_cogs = 0.0
    total_exp = 0.0
    total_oi = 0.0
    total_oe = 0.0
    unknown_types = []

    for acc in accounts:
        code = acc["code"]
        agg = per_acc.get(code, {"debit": 0, "credit": 0})
        d = float(agg.get("debit") or 0)
        c = float(agg.get("credit") or 0)
        if not acc.get("active", True) and d == 0 and c == 0:
            continue
        acc_type = _bs_type(acc)
        if acc_type != (acc.get("type") or "").upper():
            unknown_types.append({"code": code, "type": acc.get("type"), "treated_as": acc_type})

        if acc_type == "ASSET":
            bal = round(d - c, 2)
            if bal != 0:
                assets.append({"code": code, "name": acc["name"], "amount": bal})
            total_assets += bal
        elif acc_type == "LIABILITY":
            bal = round(c - d, 2)
            if bal != 0:
                liabilities.append({"code": code, "name": acc["name"], "amount": bal})
            total_liabilities += bal
        elif acc_type == "EQUITY":
            bal = round(c - d, 2)
            if bal != 0:
                equity.append({"code": code, "name": acc["name"], "amount": bal})
            total_equity += bal
        elif acc_type == "REVENUE":
            total_rev += round(c - d, 2)
        elif acc_type == "COGS":
            total_cogs += round(d - c, 2)
        elif acc_type == "EXPENSE":
            total_exp += round(d - c, 2)
        elif acc_type == "OTHER_INCOME":
            total_oi += round(c - d, 2)
        elif acc_type == "OTHER_EXPENSE":
            total_oe += round(d - c, 2)

    current_earnings = round(total_rev - total_cogs - total_exp + total_oi - total_oe, 2)
    # add "Laba/Rugi Tahun Berjalan" as computed equity line (virtual, from P&L)
    if current_earnings != 0:
        equity.append({
            "code": "LABA_BERJALAN",
            "name": "Laba/Rugi Tahun Berjalan (Komputasi)",
            "amount": current_earnings,
            "computed": True,
        })
        total_equity += current_earnings

    total_liab_equity = round(total_liabilities + total_equity, 2)
    balanced = round(total_assets, 2) == total_liab_equity

    return {
        "meta": {"as_of": as_of},
        "assets": {"accounts": assets, "total": round(total_assets, 2)},
        "liabilities": {"accounts": liabilities, "total": round(total_liabilities, 2)},
        "equity": {"accounts": equity, "total": round(total_equity, 2)},
        "totals": {
            "assets": round(total_assets, 2),
            "liabilities": round(total_liabilities, 2),
            "equity": round(total_equity, 2),
            "liab_plus_equity": total_liab_equity,
            "current_earnings": current_earnings,
            "diff": round(round(total_assets, 2) - total_liab_equity, 2),
        },
        "balanced": balanced,
        "type_warnings": unknown_types,
    }


# ═══════════════════════════════════════════════════════════════════════════
# F2: JOURNAL LIST (audit trail with filter)
# ═══════════════════════════════════════════════════════════════════════════
@router.get("/journal-list")
async def journal_list(
    request: Request,
    from_date: Optional[str] = Query(None, alias="from"),
    to_date: Optional[str] = Query(None, alias="to"),
    source: Optional[str] = None,
    status: Optional[str] = None,
    account_code: Optional[str] = None,
    limit: int = 500,
):
    """F2: filtered journal list (audit trail).
    Optionally filter by account_code: returns only JEs whose lines touch that account.
    """
    await require_auth(request)
    db = get_db()
    q = {}
    if from_date and to_date:
        q["date"] = {"$gte": from_date, "$lte": to_date}
    elif from_date:
        q["date"] = {"$gte": from_date}
    elif to_date:
        q["date"] = {"$lte": to_date}
    if source:
        q["source_module"] = source
    if status:
        q["status"] = status

    if account_code:
        # find JE ids that have line with account_code
        line_rows = await db.rahaza_journal_lines.find(
            {"account_code": account_code, **({"date": q["date"]} if "date" in q else {})},
            {"_id": 0, "je_id": 1},
        ).to_list(500)
        je_ids = list({r["je_id"] for r in line_rows})
        if not je_ids:
            return {"meta": {"from": from_date, "to": to_date, "source": source, "status": status, "account_code": account_code}, "rows": [], "total_debit": 0, "total_credit": 0}
        q["id"] = {"$in": je_ids}

    rows = await db.rahaza_journal_entries.find(q, {"_id": 0}).sort([("date", -1), ("je_number", -1)]).limit(limit).to_list(500)
    # summarize totals (only posted)
    total_debit = sum(float(r.get("total_debit") or 0) for r in rows if r.get("status") == "posted")
    total_credit = sum(float(r.get("total_credit") or 0) for r in rows if r.get("status") == "posted")

    return {
        "meta": {"from": from_date, "to": to_date, "source": source, "status": status, "account_code": account_code},
        "rows": serialize_doc(rows),
        "total_debit": round(total_debit, 2),
        "total_credit": round(total_credit, 2),
        "count": len(rows),
    }


# ═══════════════════════════════════════════════════════════════════════════
# F3: CASH FLOW STATEMENT (direct method via cash_movements ledger)
# ═══════════════════════════════════════════════════════════════════════════
@router.get("/cash-flow")
async def cash_flow(
    request: Request,
    from_date: Optional[str] = Query(None, alias="from"),
    to_date: Optional[str] = Query(None, alias="to"),
):
    """F3: Cash Flow Statement (metode direct).
    Sumber utama: rahaza_cash_movements (category-based grouping ke Operating/Investing/Financing).
    Opening + closing cash dihitung dari cash_accounts balance + ledger.
    """
    await require_auth(request)
    db = get_db()
    today = date.today().isoformat()
    if not to_date:
        to_date = today
    if not from_date:
        from_date = f"{today[:4]}-01-01"

    # Map cash_movements category → activity bucket
    INVESTING_CATS = {"asset_purchase", "asset_sale", "investment"}
    FINANCING_CATS = {"loan_proceeds", "loan_repayment", "owner_investment", "owner_withdrawal", "dividend"}
    # Default fallback: all other categories (ar_payment, ap_payment, expense, payroll, …) → operating

    # 1) Aggregate cash_movements in period
    movements = await db.rahaza_cash_movements.find(
        {"date": {"$gte": from_date, "$lte": to_date}}, {"_id": 0}
    ).to_list(500)

    def _bucket(cat):
        c = (cat or "").lower()
        if c in INVESTING_CATS:
            return "investing"
        if c in FINANCING_CATS:
            return "financing"
        return "operating"  # default

    activities = {"operating": {}, "investing": {}, "financing": {}}
    for mv in movements:
        cat = mv.get("category") or "other_operating"
        bucket = _bucket(cat)
        amt = float(mv.get("amount") or 0)
        if mv.get("direction") == "out":
            amt = -amt
        if cat not in activities[bucket]:
            activities[bucket][cat] = {"inflow": 0.0, "outflow": 0.0, "net": 0.0, "count": 0}
        slot = activities[bucket][cat]
        if amt >= 0:
            slot["inflow"] += amt
        else:
            slot["outflow"] += -amt
        slot["net"] += amt
        slot["count"] += 1

    def _format_bucket(b):
        rows = []
        total = 0.0
        for cat, slot in b.items():
            rows.append({
                "category": cat,
                "label": cat.replace("_", " ").title(),
                "inflow": round(slot["inflow"], 2),
                "outflow": round(slot["outflow"], 2),
                "net": round(slot["net"], 2),
                "count": slot["count"],
            })
            total += slot["net"]
        rows.sort(key=lambda r: r["category"])
        return {"items": rows, "total": round(total, 2)}

    operating = _format_bucket(activities["operating"])
    investing = _format_bucket(activities["investing"])
    financing = _format_bucket(activities["financing"])
    net_change = round(operating["total"] + investing["total"] + financing["total"], 2)

    # 2) Opening & closing cash balances (all cash accounts)
    cash_accs = await db.rahaza_cash_accounts.find({}, {"_id": 0}).to_list(500)
    # current balance (right-now), and opening_balance (start balance)
    closing_cash_now = sum(float(a.get("balance") or 0) for a in cash_accs)

    # Opening = closing at start = current - all movements from `from_date` onwards
    all_from = await db.rahaza_cash_movements.find(
        {"date": {"$gte": from_date}}, {"_id": 0, "direction": 1, "amount": 1}
    ).to_list(500)
    delta_since_from = 0.0
    for m in all_from:
        a = float(m.get("amount") or 0)
        if m.get("direction") == "out":
            a = -a
        delta_since_from += a
    opening_cash = closing_cash_now - delta_since_from

    # Closing at `to_date`: opening + all movements from_date..to_date = opening + net_change
    closing_cash = round(opening_cash + net_change, 2)

    return {
        "meta": {"from": from_date, "to": to_date, "method": "direct"},
        "activities": {
            "operating": {"label": "Aktivitas Operasi", **operating},
            "investing": {"label": "Aktivitas Investasi", **investing},
            "financing": {"label": "Aktivitas Pendanaan", **financing},
        },
        "totals": {
            "operating": operating["total"],
            "investing": investing["total"],
            "financing": financing["total"],
            "net_change_in_cash": net_change,
            "opening_cash": round(opening_cash, 2),
            "closing_cash": closing_cash,
        },
        "cash_accounts": [
            {"id": a.get("id"), "code": a.get("code"), "name": a.get("name"), "type": a.get("type"), "balance": round(float(a.get("balance") or 0), 2)}
            for a in cash_accs
        ],
    }
