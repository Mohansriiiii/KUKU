# Nyay Saathi: AI help for consumer refund problems in India

Talk to it by text or voice, in your language. It builds your case, explains where you stand with verified legal citations, and drafts a refund notice. Other problems (deposit, salary, legal notices, fraud) get an honest referral.

## Run it
```
python -m venv venv
venv\Scripts\activate          (Mac/Linux: source venv/bin/activate)
pip install -r requirements.txt
copy .env.example .env         then add your free Gemini key from aistudio.google.com
python -m streamlit run app.py
```
Terminal version: `python cli.py`

## Test cases and raw outputs
```
python run_tests.py              all 18 cases in tests/cases.json
python run_tests.py 05 17        only some cases
```
Writes one folder per case to `outputs/tests/` (transcript, extracted case, trace with citation audits, notice) and `outputs/tests/summary.csv`.

## Swap the model
Set `CHAT_MODEL` in `.env` for another Gemini model, or set `LLM_PROVIDER=openai` with `OPENAI_BASE_URL`, `OPENAI_API_KEY` and `CHAT_MODEL` for any OpenAI-compatible API. All model calls go through `llm.py`.

## How it avoids invented law
- `rules/rules.json`: hand-written rules, each tied to an exact phrase in the official text. `python rules.py` verifies every phrase is really in the cited section.
- The model may only cite IDs it was given. Code rejects unknown IDs, typed section numbers and court case names, retries once, then falls back to the verified rules.
- Deadlines, commission and fee are computed in code, not by the model.

## Files
| File | Job |
|---|---|
| `build_index.py` | PDFs/OCR text to section chunks and embeddings (run once) |
| `rag.py` | Search over the indexed law |
| `rules.py` | Verified rules, evidence check, rule engine |
| `agent.py` | Conversation flow: intake, routing, gap questions, explanation, citation audit, notice |
| `llm.py` | All model calls (swap point) |
| `app.py` / `cli.py` | Web and terminal interfaces |
| `run_tests.py` | Runs test cases, saves raw outputs |

## Sources indexed
Consumer Protection Act 2019; E-Commerce Rules 2020 (OCR of the scanned Gazette copy); Jurisdiction Rules 2021; Consumer Disputes Redressal Commissions Rules 2020.

Not legal advice. Free legal aid: 15100.
