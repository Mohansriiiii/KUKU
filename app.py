import hashlib
import streamlit as st

print("[app] page run started", flush=True)
st.set_page_config(page_title="Nyay Saathi", page_icon="⚖️")


@st.cache_resource
def load():
    print("[app] loading llm...", flush=True)
    from llm import transcribe
    print("[app] loading search index...", flush=True)
    import rag
    print("[app] loading agent...", flush=True)
    import agent
    print("[app] ready", flush=True)
    return agent, transcribe


with st.spinner("Loading the law index..."):
    agent, transcribe = load()

if "msgs" not in st.session_state:
    st.session_state.msgs = []
    st.session_state.state = {}
    st.session_state.notice = None
    st.session_state.last_audio = None

ss = st.session_state

with st.sidebar:
    st.header("Your case")
    case = ss.state.get("case")
    if case:
        amt = f"Rs {case['amount']:,.0f}" if case.get("amount") else None
        rows = [("What happened", case.get("issue")), ("Product", case.get("product")),
                ("Seller", case.get("seller")), ("Paid", amt), ("Paid on", case.get("paid_on")),
                ("Problem date", case.get("issue_date")), ("Bought via", case.get("channel")),
                ("Proof", ", ".join(case.get("proof") or []) or None), ("Already tried", case.get("tried"))]
        for k, v in rows:
            st.markdown(f"**{k}:** {v if v else ':grey[not given yet]'}")
        ev = ss.state.get("ev")
        if ev:
            st.caption(f"Status: {ev['status']}")
            for n in ev["notes"]:
                st.write("•", n)
            for e in ev["escalate"]:
                st.warning(e)
        with st.expander("Raw case data"):
            st.json({k: v for k, v in case.items() if v not in (None, [], "")})
    else:
        st.caption("Tell me what happened, and I'll build your case here.")

    if ss.state.get("explained"):
        if st.button("Draft refund notice", use_container_width=True):
            with st.spinner("Drafting..."):
                ss.notice = agent.notice(ss.state["case"], ss.state["ev"])
        if ss.notice:
            st.download_button("Download notice (.txt)", ss.notice, file_name="refund_notice.txt",
                               use_container_width=True)

    if st.button("Start a new case", use_container_width=True):
        for k in list(ss.keys()):
            del ss[k]
        st.rerun()

    st.divider()
    st.caption("This is guidance from an AI assistant, not advice from a lawyer. "
               "It covers consumer refund problems in India. Free legal aid: 15100.")

st.title("⚖️ Nyay Saathi")
st.caption("Tell me about a refund problem in any language. I'll explain where you stand and help you act.")

if not ss.msgs:
    with st.chat_message("assistant"):
        st.write("Hi! What happened? For example: *I paid Rs 4,500 for a mixer on Flipkart, it was "
                 "defective, I returned it, but I still haven't got my refund.*")

for m in ss.msgs:
    with st.chat_message(m["role"]):
        st.markdown(m["content"])

if ss.notice:
    with st.expander("Your draft notice", expanded=True):
        st.text(ss.notice)

text = st.chat_input("Type your problem...")
audio = st.audio_input("Or speak")

if audio and not text:
    data = audio.getvalue()
    h = hashlib.md5(data).hexdigest()
    if h != ss.last_audio:
        ss.last_audio = h
        with st.spinner("Listening..."):
            text = transcribe(data, audio.type or "audio/wav")

if text:
    ss.msgs.append(dict(role="user", content=text))
    with st.chat_message("user"):
        st.markdown(text)
    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            try:
                reply = agent.step(ss.msgs, ss.state)
            except Exception as e:
                reply = f"Sorry, something went wrong ({str(e)[:120]}). Please try again in a minute."
        st.markdown(reply)
    ss.msgs.append(dict(role="assistant", content=reply))
    st.rerun()
