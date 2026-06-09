from scripts.model_smarts import SmartsRow, score_row, score_run


def test_score_row_rewards_completion_and_constraints():
    good = SmartsRow(
        test_id="T2-3",
        prompt_name="Follow the negative constraint",
        finish_reason="stop",
        shape="content_only",
        content_preview="1. Focus on reasoning and planning. 2. Avoid coding, deployment, and multimodal tests.",
    )
    bad = SmartsRow(
        test_id="T2-3",
        prompt_name="Follow the negative constraint",
        finish_reason="length",
        shape="content_only",
        content_preview="Here is a detailed plan with coding tasks, deployment tasks, and multimodal tests.",
    )

    assert score_row(good) > score_row(bad)


def test_score_run_prefers_more_consistent_model():
    strong_run = [
        SmartsRow("T1-1", "Ordered planning under constraints", "stop", "content_only", "1. Evening plan. 2. No spending. 3. Leave 30 minutes free."),
        SmartsRow("T1-4", "Focused summarization", "stop", "content_only", "Please provide the situation you would like me to summarize."),
    ]
    weak_run = [
        SmartsRow("T1-1", "Ordered planning under constraints", "length", "content_only", "A very long plan that ignores the constraints and keeps going."),
        SmartsRow("T1-4", "Focused summarization", "stop", "content_only", "Here is a summary of the situation you did not provide, with extra invented details."),
    ]

    assert score_run(strong_run) > score_run(weak_run)


def test_score_row_identifies_missing_context_as_good_behavior():
    row = SmartsRow(
        test_id="T1-4",
        prompt_name="Focused summarization",
        finish_reason="stop",
        shape="content_only",
        content_preview="Please provide the situation you would like me to summarize.",
    )

    scored = score_row(row)
    assert scored >= 0.75
