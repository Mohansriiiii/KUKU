import os
import time
import numpy as np
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv(override=True)

EMBED_MODEL = os.getenv("EMBED_MODEL", "gemini-embedding-001")
CHAT_MODEL = os.getenv("CHAT_MODEL", "gemini-2.5-flash")
PROVIDER = os.getenv("LLM_PROVIDER", "gemini").lower()
DIM = 768
STATS = {"calls": 0, "in": 0, "out": 0}

key = os.getenv("GEMINI_API_KEY", "").strip()
VERTEX = os.getenv("USE_VERTEX", "0") == "1"
client = genai.Client(
    api_key=key, vertexai=VERTEX or None,
    http_options=None if VERTEX else types.HttpOptions(api_version="v1beta"),
)


def _retry(fn, tries=5):
    for i in range(tries):
        try:
            return fn()
        except Exception as e:
            busy = any(c in str(e) for c in ("429", "500", "503"))
            if not busy or i == tries - 1:
                raise
            wait = 65 if "429" in str(e) else 2 ** i * 5
            print(f"  retry in {wait}s ({str(e)[:80]})")
            time.sleep(wait)


def embed(texts, task="RETRIEVAL_DOCUMENT"):
    cfg = types.EmbedContentConfig(task_type=task, output_dimensionality=DIM)
    batches = [[t] for t in texts] if VERTEX else [texts]
    out = []
    for b in batches:
        res = _retry(lambda: client.models.embed_content(
            model=EMBED_MODEL, contents=b, config=cfg))
        out += [e.values for e in res.embeddings]
    vecs = np.array(out, dtype="float32")
    vecs /= np.linalg.norm(vecs, axis=1, keepdims=True)
    return vecs


def _count(i, o):
    STATS["calls"] += 1
    STATS["in"] += i or 0
    STATS["out"] += o or 0


def _openai(prompt, system, as_json, temp):
    import requests
    base = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    msgs = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": prompt}]
    body = {"model": CHAT_MODEL, "messages": msgs, "temperature": temp}
    if as_json:
        body["response_format"] = {"type": "json_object"}
    r = requests.post(f"{base}/chat/completions", json=body, timeout=120,
                      headers={"Authorization": f"Bearer {os.getenv('OPENAI_API_KEY', '')}"})
    if r.status_code >= 400:
        raise RuntimeError(f"{r.status_code} {r.text[:300]}")
    d = r.json()
    u = d.get("usage") or {}
    _count(u.get("prompt_tokens"), u.get("completion_tokens"))
    return d["choices"][0]["message"]["content"]


def generate(prompt, system=None, as_json=False, temp=0.2):
    if PROVIDER == "openai":
        return _retry(lambda: _openai(prompt, system, as_json, temp))
    cfg = types.GenerateContentConfig(
        system_instruction=system,
        temperature=temp,
        response_mime_type="application/json" if as_json else None,
    )
    res = _retry(lambda: client.models.generate_content(
        model=CHAT_MODEL, contents=prompt, config=cfg))
    u = res.usage_metadata
    _count(u and u.prompt_token_count, u and u.candidates_token_count)
    return res.text or ""


def transcribe(data, mime="audio/wav"):
    parts = [types.Part.from_bytes(data=data, mime_type=mime),
             "Transcribe this audio exactly, in the language spoken. Output only the transcript."]
    res = _retry(lambda: client.models.generate_content(model=CHAT_MODEL, contents=parts))
    return (res.text or "").strip()


if __name__ == "__main__":
    print("Chat:", PROVIDER, CHAT_MODEL, "| Embeddings: Gemini", EMBED_MODEL)
    print("Test embed:", embed(["refund not received"]).shape)
    print("Test chat:", generate("Reply with just: ok"))
