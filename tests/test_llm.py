from llm import SYSTEM_PROMPT, TRADE_PROMPT_ADDENDUM, build_messages


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


def test_system_prompt_disclaims_data_categories_this_app_does_not_track():
    # Regression guard: the model must not invent contract/cap/injury figures
    # this app has no reliable data source for.
    for term in ("contracts", "cap space", "injury", "draft-pick protections"):
        assert term in SYSTEM_PROMPT.lower()


def test_system_prompt_allows_salary_only_when_given_in_context():
    # Once the partial contracts dataset shipped, the absolute "never has
    # this" framing became inaccurate -- it must now say salary data is
    # partial/unverified and may only be cited when the context provides it.
    lowered = SYSTEM_PROMPT.lower()
    assert "partial" in lowered and "unverified" in lowered
    assert "salary" in lowered


def test_system_prompt_requires_distinguishing_fact_from_prediction():
    assert "hypothetical" in SYSTEM_PROMPT.lower()
    assert "assumption" in SYSTEM_PROMPT.lower()


def test_system_prompt_instructs_asking_when_identity_is_ambiguous():
    assert "ask" in SYSTEM_PROMPT.lower() and "ambiguous" in SYSTEM_PROMPT.lower()


def test_build_messages_appends_trade_addendum_only_in_trade_mode():
    normal = build_messages("Tell me about the Spurs", [], "ctx")
    trade = build_messages("Should they trade for AD?", [], "ctx", trade_mode=True)
    assert normal[0] == ("system", SYSTEM_PROMPT)
    assert trade[0][1] == SYSTEM_PROMPT + TRADE_PROMPT_ADDENDUM
    assert "Verdict:" in trade[0][1]


def test_trade_addendum_forbids_cap_feasibility_claims():
    assert "cap-feasible" in TRADE_PROMPT_ADDENDUM or "cap" in TRADE_PROMPT_ADDENDUM.lower()
    assert "never" in TRADE_PROMPT_ADDENDUM.lower()


def test_system_prompt_guards_against_flipped_yes_no_on_negated_hypotheticals():
    # Regression: "would the Cavs have repeated if KD had NOT joined the
    # Warriors?" got answered "No, the Cavs probably would have won..." --
    # a leading Yes/No that contradicted its own very next clause.
    lowered = SYSTEM_PROMPT.lower()
    assert "negation" in lowered
    assert "re-check" in lowered or "recheck" in lowered


def test_system_prompt_forbids_supplementing_championships_and_coach_from_training():
    lowered = SYSTEM_PROMPT.lower()
    assert "live via nba_api" in lowered
    assert "never supplement" in lowered or "don't supplement" in lowered
    assert "stale" in lowered


def test_system_prompt_mentions_front_office_as_untracked():
    assert "front office" in SYSTEM_PROMPT.lower() or "front-office" in SYSTEM_PROMPT.lower()


def test_system_prompt_scopes_data_to_2025_26():
    lowered = SYSTEM_PROMPT.lower()
    assert "2025-26" in lowered
    assert "2026-27" in lowered


def test_strip_leaked_labels_removes_known_leak_patterns():
    from llm import strip_leaked_labels
    assert strip_leaked_labels("Fact: the Lakers won 50 games.") == "the Lakers won 50 games."
    assert (
        strip_leaked_labels("The Lakers are talented. Judgment: they underachieve.")
        == "The Lakers are talented. they underachieve."
    )
    assert strip_leaked_labels("**Assumption:** this is speculative.") == "this is speculative."


def test_strip_leaked_labels_does_not_touch_ordinary_prose():
    from llm import strip_leaked_labels
    text = "In fact, the Lakers improved their defense this season."
    assert strip_leaked_labels(text) == text


def test_strip_leaked_labels_preserves_intentional_trade_mode_labels():
    from llm import strip_leaked_labels
    text = "Verdict: this trade makes sense. Team fit: both sides benefit."
    assert strip_leaked_labels(text) == text


def test_system_prompt_forbids_labeled_parts_and_meta_commentary():
    lowered = SYSTEM_PROMPT.lower()
    assert "fact:" in lowered and "judgment:" in lowered  # named as forbidden, not as a format to use
    assert "directly from the provided context" in lowered


def test_system_prompt_targets_shorter_answers():
    lowered = SYSTEM_PROMPT.lower()
    assert "3-4 sentences" in lowered
    assert "80 words" in lowered
