import re
import csv
import sys
import json
import time
import shutil
from pathlib import Path

import llm
import agent

CASES = Path("tests/cases.json")
OUT = Path("outputs/tests")
SCRIPTS = {"telugu": (0x0C00, 0x0C7F), "devanagari": (0x0900, 0x097F)}


def has_script(text, name):
    lo, hi = SCRIPTS[name]
    return sum(lo <= ord(c) <= hi for c in text) > 20


def check(exp, state, replies):
    last = replies[-1]
    case, ev = state.get("case") or {}, state.get("ev") or {}
    res = []
    if "stage" in exp:
        res.append((f"stage={exp['stage']}", state.get("stage") == exp["stage"]))
    if "contains_any" in exp:
        res.append((f"mentions one of {exp['contains_any']}", any(w.lower() in last.lower() for w in exp["contains_any"])))
    for pat in exp.get("not_regex", []):
        res.append((f"no match for {pat}", not re.search(pat, last)))
    if "script" in exp:
        res.append((f"reply in {exp['script']} script", has_script(last, exp["script"])))
    for k, v in exp.get("case", {}).items():
        res.append((f"case.{k}={v}", case.get(k) == v))
    if "escalate" in exp:
        res.append((f"escalate={exp['escalate']}", bool(ev.get("escalate")) == exp["escalate"]))
    leaks = [m for r in replies for m in re.findall(r"\[[A-Za-z_][^\]\n]{0,60}\](?!\()", r)]
    res.append((f"no raw brackets shown to user {leaks[:3]}", not leaks))
    res.append(("no prompt wording leaked", not any("suggest free legal aid" in r.lower() for r in replies)))
    return res


def run(c, gap):
    d = OUT / c["id"]
    shutil.rmtree(d, ignore_errors=True)
    d.mkdir(parents=True)
    agent.LOG = d
    state, msgs, replies = {"sid": "trace"}, [], []
    before = dict(llm.STATS)
    t0 = time.time()
    for turn in c["turns"]:
        msgs.append(dict(role="user", content=turn))
        try:
            r = agent.step(msgs, state)
        except Exception as e:
            r = f"[ERROR] {e}"
        msgs.append(dict(role="assistant", content=r))
        replies.append(r)
        time.sleep(gap)

    notice = None
    if c["expect"].get("notice") and state.get("explained"):
        notice = agent.notice(state["case"], state["ev"])
        (d / "notice.txt").write_text(notice, encoding="utf-8")

    md = [f"# {c['id']}: {c['title']}\n"]
    for m in msgs:
        md.append(f"**{'User' if m['role'] == 'user' else 'Assistant'}:**\n\n{m['content']}\n")
    (d / "transcript.md").write_text("\n".join(md), encoding="utf-8")
    (d / "case.json").write_text(json.dumps(
        dict(case=state.get("case"), ev=state.get("ev")), indent=1, ensure_ascii=False), encoding="utf-8")

    audits = []
    trace = d / "trace.jsonl"
    if trace.exists():
        for line in trace.read_text(encoding="utf-8").splitlines():
            audits += (json.loads(line).get("info") or {}).get("audit") or []
    fb = any(a.get("fallback") for a in audits)

    errs = [r for r in replies if r.startswith("[ERROR]")]
    checks = [] if errs else check(c["expect"], state, replies)
    if errs:
        checks.append((f"no errors ({errs[0][:150]})", False))
    if c["expect"].get("notice"):
        checks.append(("notice drafted", notice is not None))
    if c["expect"].get("fallback") is False:
        checks.append(("answered without falling back", not fb))
    row = dict(
        id=c["id"], title=c["title"], model=f"{llm.PROVIDER}:{llm.CHAT_MODEL}", stage=state.get("stage"),
        passed=all(ok for _, ok in checks),
        failed="; ".join(n for n, ok in checks if not ok),
        retries=sum(1 for a in audits if a.get("attempt") == 2),
        fallback=fb,
        llm_calls=llm.STATS["calls"] - before["calls"],
        tokens_in=llm.STATS["in"] - before["in"],
        tokens_out=llm.STATS["out"] - before["out"],
        seconds=round(time.time() - t0, 1),
    )
    (d / "result.json").write_text(json.dumps(dict(row, checks=checks), indent=1), encoding="utf-8")
    return row


def main():
    global OUT
    args = sys.argv[1:]
    gap = 4.0
    if "--gap" in args:
        gap = float(args[args.index("--gap") + 1])
    if "--out" in args:
        OUT = Path(args[args.index("--out") + 1])
    cases = json.loads(CASES.read_text(encoding="utf-8"))
    skip = {args[args.index(f) + 1] for f in ("--gap", "--out") if f in args}
    pick = [a for a in args if not a.startswith("--") and a not in skip]
    if pick:
        cases = [c for c in cases if any(p in c["id"] for p in pick)]

    print(f"Model: {llm.PROVIDER} {llm.CHAT_MODEL} | {len(cases)} cases\n")
    rows = []
    for c in cases:
        print(f"{c['id']:28}", end=" ", flush=True)
        row = run(c, gap)
        rows.append(row)
        print(("PASS" if row["passed"] else "FAIL"), f"{row['stage'] or '':10} {row['llm_calls']:2} calls",
              f"{row['seconds']:5}s", row["failed"])

    summary = OUT / "summary.csv"
    old = {}
    if summary.exists() and pick:
        old = {r["id"]: r for r in csv.DictReader(open(summary, encoding="utf-8"))}
    for r in rows:
        old[r["id"]] = r
    with open(summary, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        for k in sorted(old):
            w.writerow(old[k])

    n = sum(r["passed"] for r in rows)
    calls = sum(r["llm_calls"] for r in rows)
    tin = sum(r["tokens_in"] for r in rows)
    tout = sum(r["tokens_out"] for r in rows)
    print(f"\n{n}/{len(rows)} passed | {calls} LLM calls | {tin} tokens in, {tout} out")
    print(f"Per case avg: {calls / len(rows):.1f} calls, {(tin + tout) / len(rows):.0f} tokens")
    print(f"Saved: {summary} and one folder per case in {OUT}")


if __name__ == "__main__":
    main()
