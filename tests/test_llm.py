from llm import SYSTEM_PROMPT, build_messages


def test_build_messages_includes_system_prompt_first():
    messages = build_messages("Tell me about the Spurs", [], "Spurs context")
    assert messages[0] == ("system", SYSTEM_PROMPT)


def test_build_messages_includes_history_in_order():
    history = [
        {"role": "user", "content": "Tell me about the Spurs"},
        {"role": "assistant", "content": "They have great continuity."},
    ]
    messages = build_messages("What about their draft picks?", history, "Spurs context")
    assert messages[1] == ("user", "Tell me about the Spurs")
    assert messages[2] == ("assistant", "They have great continuity.")
    assert messages[-1] == (
        "user",
        "Context:\nSpurs context\n\nQuestion: What about their draft picks?",
    )


def test_build_messages_caps_history_to_last_ten():
    history = [{"role": "user", "content": f"msg {i}"} for i in range(15)]
    messages = build_messages("latest", history, "")
    # system + 10 capped history turns + final question = 12
    assert len(messages) == 12
    assert messages[1] == ("user", "msg 5")
    assert messages[-2] == ("user", "msg 14")


def test_build_messages_handles_empty_history():
    messages = build_messages("Tell me about the Spurs", [], "Spurs context")
    assert len(messages) == 2
