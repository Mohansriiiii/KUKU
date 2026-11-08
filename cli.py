import agent

print("Nyay Saathi (terminal). Type your problem. 'notice' drafts a notice, 'new' starts over, 'quit' exits.\n")
msgs, state = [], {}
while True:
    try:
        text = input("You: ").strip()
    except (EOFError, KeyboardInterrupt):
        break
    if not text:
        continue
    if text == "quit":
        break
    if text == "new":
        msgs, state = [], {}
        print("\n--- new case ---\n")
        continue
    if text == "notice":
        if state.get("explained"):
            print("\n" + agent.notice(state["case"], state["ev"]))
        else:
            print("\nTell me the full story first.\n")
        continue
    msgs.append(dict(role="user", content=text))
    reply = agent.step(msgs, state)
    msgs.append(dict(role="assistant", content=reply))
    print(f"\nAssistant: {reply}\n")
