import re
import json
from datetime import date

RULES = json.load(open("rules/rules.json", encoding="utf-8"))
BY_ID = {r["id"]: r for r in RULES}
REF = json.load(open("rules/referrals.json", encoding="utf-8"))


def norm(s):
    s = re.sub(r"\s+", " ", s.lower())
    for a, b in (("“", '"'), ("”", '"'), ("’", "'"), ("( ", "("), ("- ", "-")):
        s = s.replace(a, b)
    return s


def squash(s):
    return norm(s).replace(" ", "")


def check(chunks):
    bad = []
    for r in RULES:
        if r["kind"] != "law":
            continue
        parts = [c for c in chunks if c["id"] == r["src"] or c["id"].startswith(r["src"] + "_")]
        if not parts:
            bad.append((r["id"], f"section {r['src']} not in index"))
        elif not any(squash(r["evidence"]) in squash(c["text"]) for c in parts):
            bad.append((r["id"], f"'{r['evidence']}' not found in {r['src']}"))
    return bad


def commission(amount):
    if amount is None:
        return None
    if amount <= 50_00_000:
        return "District Commission", "DISTRICT_LIMIT"
    if amount <= 2_00_00_000:
        return "State Commission", "STATE_LIMIT"
    return "National Commission", "NATIONAL_LIMIT"


def evaluate(case, today=None):
    today = today or date.today()
    hit, notes, escalate, missing = [], [], [], []

    purpose = case.get("purpose")
    if purpose in ("resale", "commercial"):
        escalate.append("Bought for resale or business use, so consumer law may not apply. Talk to a lawyer.")
        return dict(status="not_covered", rules=["CONSUMER"], notes=notes,
                    escalate=escalate, missing=missing, late=False)
    hit.append("CONSUMER")
    if purpose is None:
        missing.append("purpose")

    hit += ["DEFECT", "DEFICIENCY"]

    late = False
    when = case.get("issue_date")
    if when:
        d = date.fromisoformat(when)
        notes.append(f"Time limit counted from {d:%d %B %Y}. Tell me if that date is wrong.")
        try:
            due = d.replace(year=d.year + 2)
        except ValueError:
            due = date(d.year + 2, 3, 1)
        left = (due - today).days
        hit.append("LIMITATION")
        if left < 0:
            late = True
            notes.append(f"The 2-year limit to file passed {-left} days ago. A late complaint is accepted only if the commission accepts a good reason for the delay.")
            escalate.append(f"The 2-year limit passed {-left} days ago. A late complaint needs a good reason for the delay. Talk to a lawyer or legal aid.")
        elif left <= 60:
            notes.append(f"Only {left} days left to file. File soon.")
        else:
            notes.append(f"About {left // 30} months left to file a complaint.")
    else:
        missing.append("issue_date")

    amt = case.get("amount")
    c = commission(amt)
    if c:
        notes.append(f"Your complaint would go to the {c[0]}.")
        hit.append(c[1])
        if amt <= 5_00_000:
            hit.append("FEE_NIL")
            notes.append("There is no filing fee for this amount.")
        if c[0] != "District Commission":
            escalate.append("Claims above Rs 50 lakh go to higher commissions. A lawyer is strongly advised.")
    else:
        missing.append("amount")

    ch = case.get("channel")
    if ch == "online_marketplace":
        hit += ["ECOM_SELLER_REFUND", "ECOM_SELLER_GRIEVANCE", "ECOM_REFUND_PAYMENT"]
    elif ch == "online_store":
        hit += ["ECOM_INVENTORY_REFUND", "ECOM_REFUND_PAYMENT"]
    elif ch is None:
        missing.append("channel")

    hit += ["WHERE_TO_FILE", "E_FILING", "ADMISSION_TIME", "DECISION_TIME", "REMEDIES",
            "STEP_NOTICE", "STEP_NCH", "STEP_COMPLAINT"]

    status = "escalate" if escalate else "covered"
    return dict(status=status, rules=hit, notes=notes, escalate=escalate, missing=missing, late=late)


if __name__ == "__main__":
    chunks = json.load(open("data/index/chunks.json", encoding="utf-8"))
    bad = check(chunks)
    n = sum(r["kind"] == "law" for r in RULES)
    print(f"Evidence check: {n - len(bad)}/{n} law rules verified")
    for rid, why in bad:
        print(f"  FAIL {rid}: {why}")

    case = dict(amount=4500, purpose="personal", channel="online_marketplace",
                issue_date="2026-09-20")
    out = evaluate(case, today=date(2026, 11, 7))
    print("\nSample case:", case)
    print("Status:", out["status"])
    print("Notes:", out["notes"])
    print("Rules:", ", ".join(out["rules"]))
    print("Missing:", out["missing"], "| Escalate:", out["escalate"])
