import re
import json
from datetime import date, datetime
from pathlib import Path

from llm import generate
from rules import BY_ID, REF, evaluate
import rag

NEED = {
    "amount": "how much they paid, in rupees",
    "issue_date": "when the problem happened, or when the seller refused or stopped replying",
    "channel": "where they bought it: an app like Amazon/Flipkart, a brand's own website, a physical shop, or a service",
    "purpose": "whether they bought it for their own or family use, or for resale/business",
    "seller": "the seller's or company's name",
}

ABBR = {
    "Consumer Protection Act, 2019": "CP Act 2019",
    "Consumer Protection (E-Commerce) Rules, 2020": "E-Commerce Rules 2020",
    "Consumer Protection (Jurisdiction) Rules, 2021": "Jurisdiction Rules 2021",
    "Consumer Protection (Consumer Disputes Redressal Commissions) Rules, 2020": "Commission Rules 2020",
}

INTAKE = """You extract facts from a conversation about a legal problem in India.
Return JSON only. Use only what the person said. Do not guess: use null when unknown.
Today is {today}. Write dates as YYYY-MM-DD. If only a month is given, use the 1st.
If a date has no year, use the most recent such date that is not after today.
If the person corrects something later, use the corrected value.

Fields:
- category: refund (paid for goods or a service that was defective, not delivered, not as promised, or not refunded),
  deposit (rent or security deposit), salary (unpaid wages), notice (they received a legal notice, summons or court papers),
  criminal (fraud, scam, theft, threats, cyber crime, police matters), other
- language: the language the person writes in, e.g. English, Hindi, Telugu, Hinglish
- user_name, user_city
- seller: company or shop name
- seller_address
- product: what they bought
- amount: number in rupees that they paid
- paid_on: date paid
- issue_date: when the problem happened, or when the seller refused or stopped replying
- purpose: personal, resale or commercial. Use personal only if it is clearly for their own or family use.
- channel: online_marketplace (apps like Amazon, Flipkart, Meesho), online_store (a brand's own website or app),
  offline (a physical shop), service (courier, airline, telecom, repair and similar)
- issue: one short line in English
- proof: list of evidence they mention (bill, order email, screenshots, chats)
- tried: what they have already done, in English
- urgent: true if there is a court date, summons, threat, police involvement or risk of harm

Conversation:
{chat}"""

GAPS = """You are a friendly legal helper for ordinary people in India.
Conversation so far:
{chat}

Ask the person for these missing details, in {language}, in one short message:
{need}
{style}Ask about at most two things. Briefly acknowledge what they already told you.
Do not greet again if you already greeted. Do not give legal advice yet."""

EXPLAIN = """You help an ordinary person in India understand their consumer problem.
Write in {language}. {style}Use plain words and short sentences, no legal jargon.

Strict rules:
- Use ONLY the case facts, computed notes, rules and law extracts given below.
- Put the ID in square brackets after every legal point, e.g. [LIMITATION] or [CPA_S69].
- Copy IDs exactly as given, in English capitals, even when writing in another language. Never put anything else in square brackets.
- Never write section or rule numbers yourself. Never mention court cases. Never add laws that are not given.
- For the time limit, which commission hears the case and the fee, use the computed notes exactly.
  Never work out time left or money limits yourself.
- Rules marked "practice" are practical advice, not law. Mention once that sending a notice is not legally required. Do not write the word "practice" as a label.
- If something is not covered, say you are not sure and that they can call free legal aid at 15100.
- Keep it under 250 words. Pick the points that matter most for this person; you do not have to use every rule.

Use these four headings, in bold, each on its own line, written in {language}:
Where you stand (2-3 sentences)
What you can do (3-4 numbered steps; put filing details like fee, place and online filing inside the last step)
Keep ready (short bullet list)
What I couldn't check (1-2 sentences)

Case facts:
{case}

Computed notes:
{notes}

Rules:
{rules}

Law extracts:
{extracts}"""

FOLLOW = """You answer a follow-up question from an ordinary person in India about their consumer problem.
Write in {language}, in plain short sentences. {style}

Strict rules:
- Use ONLY the case facts, computed notes, rules and law extracts given below.
- Put the ID in square brackets after every legal point, e.g. [CPA_S39].
- Copy IDs exactly as given, in English capitals, even when writing in another language. Never put anything else in square brackets.
- Never write section or rule numbers yourself. Never add laws that are not given.
- Never name court cases. If asked for one, say you only use the Act and Rules and can't cite court judgments.
- For the time limit, use the computed notes exactly. Never work out time left yourself.
- If the person is correcting a fact, confirm the corrected fact in one line and say whether it changes anything.
- If the material below does not answer the question, say clearly that you don't know and that they can call free legal aid at 15100.
- If your answer makes no legal point at all (for example, you are only saying you don't know), end it with [NONE].

Computed notes:
{notes}

Case facts:
{case}

Rules:
{rules}

Law extracts:
{extracts}

Question: {q}"""

FACTS = """Write 3 to 5 formal sentences in English, in first person, stating these facts for a notice to a seller.
Only use these facts. Do not mention any law, section or penalty. Do not threaten.
Facts: {facts}"""

TRANSLATE = """Translate this into {language}. Keep the meaning exactly. Do not add or remove anything.
Keep phone numbers and website names unchanged.

{text}"""

REFERRALS = {
    "deposit": "Rent or security deposit disputes are usually civil matters, and the rules depend on your state and rent agreement. I don't cover this in depth yet.\n\nWhat helps now:\n1. Keep your rent agreement, rent receipts and messages with the landlord.\n2. Ask the landlord for the deposit in writing, with a date.\n3. For free advice, contact your District Legal Services Authority or call the legal aid helpline {legal_aid}.",
    "salary": "Unpaid salary depends on your type of job and your state's labour rules. I don't cover this in depth yet.\n\nWhat helps now:\n1. Keep your offer letter, salary slips, bank statements and messages.\n2. Ask your employer for the dues in writing.\n3. You can approach your state's labour department, or get free advice from your District Legal Services Authority or the legal aid helpline {legal_aid}.",
    "notice": "Please don't ignore a legal notice or court paper, and don't reply before getting advice.\n\nWhat to do now:\n1. Check it for any deadline or court date and note it down.\n2. Show it to a lawyer soon. If you can't afford one, call the free legal aid helpline {legal_aid} or visit your District Legal Services Authority.\n\nI can't advise on this safely.",
    "criminal": "This sounds like it may involve a crime, which needs the police, not just consumer law.\n\nWhat to do now:\n1. For online fraud, call {cyber_fraud} quickly. Faster reporting improves the chance of stopping the money.\n2. For threats or danger, call {police}.\n3. For free legal advice, call {legal_aid}.\n\nIf you also lost money on a purchase, tell me more and I can explain the consumer side.",
    "other": "I can only help in depth with consumer refund problems right now, so I don't want to guess about this.\n\nFor free legal advice, call the legal aid helpline {legal_aid} or visit your District Legal Services Authority.",
}

LAW_NUM = re.compile(r"(\b(section|sec\.?|s\.|rule|r\.|article)|धारा|नियम|సెక్షన్|నిబంధన|నియమం)\s*\d{1,3}(?!\d)", re.I)
EN_HEADS = ["Where you stand", "What you can do", "Keep ready", "What I couldn't check"]
HEADS = {
    "hindi": ["आपकी स्थिति", "आप क्या कर सकते हैं", "तैयार रखें", "जो मैं जाँच नहीं सका"],
    "telugu": ["మీ పరిస్థితి", "మీరు ఏమి చేయవచ్చు", "సిద్ధంగా ఉంచుకోండి", "నేను తనిఖీ చేయలేనివి"],
}
CASE_LAW = re.compile(r"\b[A-Z][\w.&]* (?:v\.|vs\.?|versus) [A-Z]|\bAIR \d{4}\b|\(\d{4}\) \d+ SCC\b|\b\d{4} SCC\b")
GROUP = re.compile(r"\[([^\[\]\n]{1,80})\](?!\()")
LATE_BAD = re.compile(r"well within|within the (two|2)[- ]year|months? left|plenty of time|still have time", re.I)
LOG = Path("outputs/sessions")


def today():
    return date.today().isoformat()


def transcript(msgs):
    return "\n".join(f"{m['role'].title()}: {m['content']}" for m in msgs)


def intake(msgs):
    raw = generate(INTAKE.format(today=today(), chat=transcript(msgs)), as_json=True, temp=0) or ""
    m = re.search(r"[\[{].*[\]}]", raw, re.S)
    try:
        case = json.loads(m.group()) if m else {}
    except json.JSONDecodeError:
        case = {}
    if isinstance(case, list):
        case = case[0] if case else {}
    try:
        case["amount"] = float(str(case.get("amount")).replace(",", "")) if case.get("amount") else None
    except ValueError:
        case["amount"] = None
    case["language"] = case.get("language") or "English"
    case["category"] = case.get("category") or "other"
    return case


def assess(case):
    c = dict(case)
    if not c.get("issue_date") and c.get("paid_on"):
        c["issue_date"] = c["paid_on"]
    ev = evaluate(c)
    if not case.get("issue_date") and case.get("paid_on"):
        ev["notes"].append("I counted the time limit from your payment date, which is the safe side.")
    if not case.get("seller"):
        ev["missing"].append("seller")
    if case.get("urgent"):
        ev["escalate"].append(f"You mentioned a threat, court date or police matter. If you feel unsafe, call {REF['police']} now. "
                              f"Please also get a lawyer or legal aid ({REF['legal_aid']}) quickly.")
        ev["status"] = "escalate"
    return ev


def lang(case):
    return case.get("language") or "English"


def style(case):
    if "hinglish" in lang(case).lower():
        return "Write the way the person did: Hindi in Roman letters mixed with English. "
    return ""


def translate(text, case):
    if lang(case).lower() == "english":
        return text
    return generate(TRANSLATE.format(language=lang(case), text=text), temp=0)


def referral(case):
    text = REFERRALS.get(case.get("category"), REFERRALS["other"]).format(**REF)
    return translate(text, case)


def ask(case, missing, msgs):
    need = "\n".join(f"- {NEED[m]}" for m in missing[:2])
    return generate(GAPS.format(chat=transcript(msgs), language=lang(case), style=style(case), need=need), temp=0.4)


def abbr(s):
    for k, v in ABBR.items():
        s = s.replace(k, v)
    return s


def short(cid):
    if cid in BY_ID:
        r = BY_ID[cid]
        return abbr(r["ref"]) if r["kind"] == "law" else None
    c = rag.by_id(cid)
    return f"{abbr(c['doc'])}, {c['ref']}" if c else None


def rules_text(ids):
    return "\n".join(f"[{i}] ({BY_ID[i]['kind']}) {BY_ID[i]['rule']}" for i in ids)


def extracts_text(hits):
    if not hits:
        return "(none matched)"
    return "\n\n".join(f"[{h['id']}] {h['doc']} {h['ref']} ({h['title']}):\n{h['text'][:1500]}" for h in hits)


def facts_text(case):
    keep = ["seller", "product", "amount", "paid_on", "issue_date", "purpose", "channel", "issue", "proof", "tried"]
    return json.dumps({k: case.get(k) for k in keep if case.get(k)}, ensure_ascii=False)


def ids_in(text):
    return [t.strip() for g in GROUP.findall(text) for t in g.split(",") if t.strip()]


def audit(text, allowed, late=False):
    ids = ids_in(text)
    bad = sorted({i for i in ids if i not in allowed and i != "NONE"})
    probs = []
    if bad:
        probs.append(f"unknown IDs or bracket text {bad}")
    if LAW_NUM.search(GROUP.sub("", text)):
        probs.append("wrote a section or rule number directly")
    if CASE_LAW.search(text):
        probs.append("mentioned a court case, which is not allowed")
    if late and LATE_BAD.search(text):
        probs.append("said there is still time, but the computed notes say the 2-year limit has passed")
    if not ids:
        probs.append("no citations (end with [NONE] if there is no legal point)")
    return probs


def render(text):
    used = []

    def sub(m):
        refs = []
        for t in m.group(1).split(","):
            ref = short(t.strip())
            if ref and ref not in refs:
                refs.append(ref)
            if ref and ref not in used:
                used.append(ref)
        return f" ({'; '.join(refs)})" if refs else ""

    out = re.sub(r" +\(", " (", GROUP.sub(sub, text))
    out = re.sub(r"\)\s*\((?=CP Act|E-Commerce|Jurisdiction|Commission)", "; ", out)
    out = re.sub(r"[ \t]+([.,;:!?।])", r"\1", out)
    out = "\n".join(ln.rstrip() for ln in out.splitlines())
    if used:
        out += "\n\n**Sources:** " + "; ".join(used)
    return out


def checked(prompt, allowed, fallback, late=False):
    log = []
    for attempt in range(2):
        text = generate(prompt, temp=0.2)
        probs = audit(text, allowed, late)
        log.append(dict(attempt=attempt + 1, problems=probs))
        if not probs:
            return render(text), log
        prompt += (f"\n\nYour last answer had problems: {'; '.join(probs)}. Fix them and follow the strict rules. "
                   f"The only IDs you may use are: {', '.join(sorted(allowed))}, or [NONE].")
    log.append(dict(fallback=True))
    return fallback(), log


def fallback_text(case, ev):
    key = {"LIMITATION", "ECOM_SELLER_REFUND", "ECOM_INVENTORY_REFUND", "REMEDIES",
           "STEP_NOTICE", "STEP_NCH", "STEP_COMPLAINT"}
    lines = ["I couldn't write a reliable explanation, so here are the verified rules for your case:"]
    lines += [f"- {n}" for n in ev["notes"]]
    for i in ev["rules"]:
        if i in key:
            r = BY_ID[i]
            lines.append(f"- {r['rule']} ({abbr(r['ref'])})")
    return translate("\n".join(lines), case)


def explain(case, ev):
    q = f"{case.get('issue') or ''} {case.get('product') or ''} refund"
    hits = rag.search(q, k=4)
    allowed = set(ev["rules"]) | {h["id"] for h in hits}
    prompt = EXPLAIN.format(
        language=lang(case), style=style(case), case=facts_text(case), notes="\n".join(ev["notes"]) or "(none)",
        rules=rules_text(ev["rules"]), extracts=extracts_text(hits))
    text, log = checked(prompt, allowed, lambda: fallback_text(case, ev), ev.get("late"))
    for en, tr in zip(EN_HEADS, HEADS.get(lang(case).lower(), EN_HEADS)):
        text = text.replace(f"**{en}**", f"**{tr}**")
    if ev["escalate"]:
        text = translate("**Please talk to a lawyer or legal aid:** " + " ".join(ev["escalate"]), case) + "\n\n" + text
    return text, dict(hits=[h["id"] for h in hits], audit=log)


def follow_up(case, ev, q):
    hits = rag.search(q, k=4)
    allowed = set(ev["rules"]) | {h["id"] for h in hits}
    prompt = FOLLOW.format(language=lang(case), style=style(case), case=facts_text(case),
                           notes="\n".join(ev["notes"]) or "(none)", rules=rules_text(ev["rules"]),
                           extracts=extracts_text(hits), q=q)
    dunno = lambda: translate(f"I'm not sure about that, and I don't want to guess. For free legal advice, call {REF['legal_aid']}.", case)
    text, log = checked(prompt, allowed, dunno, ev.get("late"))
    return text, dict(hits=[h["id"] for h in hits], audit=log)


def notice(case, ev):
    v = lambda k, d: case.get(k) or d
    amt = f"Rs {case['amount']:,.0f}" if case.get("amount") else "[amount]"
    facts = generate(FACTS.format(facts=facts_text(case)), temp=0.2).strip()
    basis = ["CONSUMER", "DEFECT", "DEFICIENCY"]
    if case.get("channel") == "online_marketplace":
        basis.append("ECOM_SELLER_REFUND")
    elif case.get("channel") == "online_store":
        basis.append("ECOM_INVENTORY_REFUND")
    law = "\n".join(f"- {BY_ID[b]['rule']} ({BY_ID[b]['ref']})" for b in basis)
    return f"""NOTICE FOR REFUND

Date: {datetime.now():%d %B %Y}

To,
{v('seller', '[Seller / company name]')}
{v('seller_address', '[Seller address]')}

From,
{v('user_name', '[Your name]')}
{v('user_city', '[Your address]')}

Subject: Demand for refund of {amt} for {v('product', '[product or service]')}

Sir/Madam,

{facts}

I rely on the following provisions:
{law}

I request you to refund {amt} within 15 days of receiving this notice. If you do not, I will file a complaint before the appropriate Consumer Disputes Redressal Commission under the Consumer Protection Act, 2019, and seek a refund, compensation and costs.

Documents I hold: {', '.join(case.get('proof') or []) or '[list your bill, order details, messages]'}

Yours faithfully,
{v('user_name', '[Your name]')}

---
Draft prepared with an AI assistant. Check every fact before sending. This is not legal advice from a lawyer.
"""


def step(msgs, state):
    case = intake(msgs)
    state["case"] = case
    info = dict(stage=None)

    if case.get("category") != "refund":
        reply = referral(case)
        info["stage"] = "referral"
    else:
        ev = assess(case)
        state["ev"] = ev
        if ev["status"] == "not_covered":
            reply = translate(" ".join(ev["escalate"]) + f" For free advice, call {REF['legal_aid']}.", case)
            info["stage"] = "not_covered"
        elif not state.get("explained"):
            if ev["missing"] and state.get("asked", 0) < 2:
                reply = ask(case, ev["missing"], msgs)
                state["asked"] = state.get("asked", 0) + 1
                info["stage"] = "gaps"
            else:
                reply, info = explain(case, ev)
                state["explained"] = True
                info["stage"] = "explain"
        else:
            reply, info = follow_up(case, ev, msgs[-1]["content"])
            info["stage"] = "follow_up"

    state["stage"] = info["stage"]
    write_log(state, msgs[-1]["content"], reply, info)
    return reply


def write_log(state, user, reply, info):
    LOG.mkdir(parents=True, exist_ok=True)
    sid = state.setdefault("sid", datetime.now().strftime("%Y%m%d_%H%M%S"))
    row = dict(time=datetime.now().isoformat(timespec="seconds"), user=user, case=state.get("case"),
               ev=state.get("ev"), info=info, reply=reply)
    with open(LOG / f"{sid}.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")