import re
import sys
import json
import hashlib
from pathlib import Path
from pypdf import PdfReader

RAW = Path("data/raw")
OUT = Path("data/index")
MAX_LEN = 2000

DOCS = [
    ("ECOM", "Consumer Protection (E-Commerce) Rules, 2020", "rule", r"e-?commerce\)?\s*rules"),
    ("JUR", "Consumer Protection (Jurisdiction) Rules, 2021", "rule", r"\(jurisdiction of the dist"),
    ("CDRC", "Consumer Protection (Consumer Disputes Redressal Commissions) Rules, 2020", "rule", r"consumer disputes redressal commissions\)\s*rules"),
    ("CPA", "Consumer Protection Act, 2019", "section", r"consumer protection act,?\s*2019|cp act 2019"),
]

# titles checked against the Act's own text; others fall back to the opening words
CPA_TITLES = {
    "1": "Short title, extent, commencement and application", "2": "Definitions",
    "34": "Jurisdiction of District Commission", "35": "Manner in which complaint shall be made",
    "36": "Proceedings before District Commission", "37": "Reference to mediation",
    "38": "Procedure on admission of complaint", "39": "Findings of District Commission",
    "40": "Review by District Commission in certain cases",
    "41": "Appeal against order of District Commission",
    "47": "Jurisdiction of State Commission", "58": "Jurisdiction of National Commission",
    "69": "Limitation period", "71": "Enforcement of orders",
    "74": "Establishment of consumer mediation cell", "82": "Application of Chapter",
    "83": "Product liability action", "84": "Liability of product manufacturer",
    "85": "Liability of product service provider", "86": "Liability of product sellers",
}

TITLED = re.compile(
    r"^\s*(\d{1,3}[A-Z]?)\.\s+([A-Z][A-Za-z ,'()/\-\n]{2,150}?)(?:\.\s*[—–-]+|\s*[—–]+)",
    re.M,
)
NUMBERED = re.compile(r"^\s*(\d{1,3}[A-Z]?)\.\s+(?=\(\s?\d|[A-Z])", re.M)
CLAUSE = re.compile(r"\n\s*(?=\(\d+[A-Z]?\)|\([a-z]\))")
JUNK = re.compile(r"[ñ¼½ªØ]|^R\.\s*\d+\]")


def bad_line(s):
    if not s or re.fullmatch(r"\d+", s) or JUNK.search(s):
        return True
    dev = sum(1 for c in s if "ऀ" <= c <= "ॿ")
    if dev > 0.3 * len(s):
        return True
    u = s.upper()
    return "GAZETTE OF INDIA" in u or s.startswith("www.") or (s == u and "RULES, 20" in u)


def clean(text):
    text = "\n".join(ln.strip() for ln in text.splitlines() if not bad_line(ln.strip()))
    return text.replace("––", "—").replace("--", "—")


def detect(text, fname):
    for src in (fname, text[:4000]):
        s = re.sub(r"\s+", " ", src.lower())
        for code, name, kind, pat in DOCS:
            if re.search(pat, s):
                return code, name, kind
    return None


def in_order(hits):
    out, last = [], 0
    for m in hits:
        n = int(re.match(r"\d+", m.group(1)).group())
        if last < n <= last + 3 or (m.group(1)[-1].isalpha() and n == last):
            out.append(m)
            last = n
    return out


def heads(text):
    for pat in (TITLED, NUMBERED):
        hits = in_order(pat.finditer(text))
        if len(hits) >= 3:
            return hits, pat is TITLED
    return [], False


def split_long(body):
    if len(body) <= MAX_LEN:
        return [body]
    parts, cur = [], ""
    for piece in CLAUSE.split(body):
        if cur and len(cur) + len(piece) > MAX_LEN:
            parts.append(cur.strip())
            cur = ""
        cur += "\n" + piece
    if cur.strip():
        parts.append(cur.strip())
    return parts


def chunk(text, code, name, kind, fname):
    hits, titled = heads(text)
    chunks = []
    for i, m in enumerate(hits):
        num = m.group(1)
        end = hits[i + 1].start() if i + 1 < len(hits) else len(text)
        body = text[m.start():end].strip()
        if titled:
            title = re.sub(r"\s+", " ", m.group(2)).strip()
        elif code == "CPA" and num in CPA_TITLES:
            title = CPA_TITLES[num]
        else:
            first = re.sub(r"\s+", " ", body[m.end() - m.start():])[:70]
            title = first.rsplit(" ", 1)[0] + "..."
        key = f"{code}_{'S' if kind == 'section' else 'R'}{num}"
        ref = f"{'s.' if kind == 'section' else 'r.'}{num}"
        parts = split_long(body)
        for j, p in enumerate(parts):
            cid = key if len(parts) == 1 else f"{key}_p{j + 1}"
            chunks.append(dict(id=cid, doc=name, kind=kind, num=num, ref=ref,
                               title=title, text=p, file=fname))
    return chunks


def read(f):
    if f.suffix == ".txt":
        return f.read_text(encoding="utf-8")
    return "\n".join(p.extract_text() or "" for p in PdfReader(f).pages)


def main(dry):
    files = sorted(list(RAW.glob("*.pdf")) + list(RAW.glob("*.txt")))
    if not files:
        sys.exit("No files in data/raw")

    OUT.mkdir(parents=True, exist_ok=True)
    chunks = []
    for f in files:
        text = clean(read(f))
        name = f.name[:45]
        if len(text) < 200:
            print(f"{name:45} -> SKIP: no text (scanned PDF, use an OCR .txt instead)")
            continue
        d = detect(text, f.name)
        dbg = OUT / f"debug_{f.stem[:30]}.txt"
        if not d:
            print(f"{name:45} -> SKIP: unknown document, see {dbg}")
            dbg.write_text(text[:20000], encoding="utf-8")
            continue
        c = chunk(text, *d, f.name)
        print(f"{name:45} -> {d[0]:5} {len(c):4} chunks")
        if not c:
            print(f"  0 chunks: see {dbg}")
            dbg.write_text(text[:20000], encoding="utf-8")
        chunks += c

    (OUT / "chunks.json").write_text(
        json.dumps(chunks, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"\nTotal: {len(chunks)} chunks -> data/index/chunks.json")

    for want in ["CPA_S2", "CPA_S34", "CPA_S35", "CPA_S69", "ECOM_R4", "JUR_R3"]:
        hit = [c for c in chunks if c["id"] == want or c["id"].startswith(want + "_")]
        status = f"{hit[0]['title'][:50]} ({len(hit)} part)" if hit else "NOT FOUND"
        print(f"  check {want:8} {status}")

    if dry:
        print("\nDry run: no embeddings made. Check chunks.json, then run without --dry")
        return

    import numpy as np
    from llm import embed

    texts = [f"{c['doc']} {c['ref']} {c['title']}\n{c['text']}" for c in chunks]
    cache = OUT / "cache"
    cache.mkdir(exist_ok=True)
    vecs = []
    for i in range(0, len(texts), 50):
        batch = texts[i:i + 50]
        h = hashlib.md5("\n".join(batch).encode()).hexdigest()[:10]
        f = cache / f"{i}_{h}.npy"
        if f.exists():
            print(f"embedding {i}-{i + len(batch)} of {len(texts)} (saved earlier)")
            vecs.append(np.load(f))
            continue
        print(f"embedding {i}-{i + len(batch)} of {len(texts)}")
        v = embed(batch)
        np.save(f, v)
        vecs.append(v)

    vecs = np.vstack(vecs)
    np.save(OUT / "vectors.npy", vecs)
    print(f"Saved data/index/vectors.npy ({len(vecs)} vectors)")


if __name__ == "__main__":
    main("--dry" in sys.argv)