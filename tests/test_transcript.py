from orchestrator.render import LIMIT, debate_markdown, summary_html
from orchestrator.transcript import Entry, Result, Usage


def result(**kw):
    base = dict(
        question="Cache <reports> & more?", decision="Use a <b>small</b> cache & a flag.", reasons=["fast", "safe"],
        dissent={}, consensus=True, rounds=2, usage=Usage(calls=8, tokens_in=4000, tokens_out=321, usd=0.0123),
        warnings=[], transcript=[
            Entry(0, "architect", "proposal", {"position": "P", "reasons": ["a"]}),
            Entry(0, "critic", "proposal", None, "critic abstained in proposal (round 0): timeout"),
            Entry(0, "moderator", "draft", {"draft": "D1"}),
            Entry(1, "critic", "review", {"agree": False, "objections": ["no metric"], "proposed_change": "add one"}),
            Entry(1, "architect", "review", {"agree": True, "objections": [], "proposed_change": ""}),
            Entry(1, "moderator", "revise", {"draft": "D2", "rulings": [{"objection": "no metric", "decision": "accepted", "reason": "fair"}]}),
            Entry(2, "critic", "review", {"agree": True, "objections": [], "proposed_change": ""}),
            Entry(2, "moderator", "final", {"decision": "X", "reasons": ["fast"]}),
        ])
    base.update(kw)
    return Result(**base)


def test_summary_escapes_html():
    text = "".join(summary_html(result()))
    assert "&lt;b&gt;small&lt;/b&gt; cache &amp; a flag" in text
    assert "<b>" in text  # our own formatting stays
    assert "Consensus after 2 rounds" in text and "$0.0123" in text and "4,321 tokens" in text


def test_summary_shows_dissent_and_no_consensus():
    text = "".join(summary_html(result(consensus=False, rounds=4, dissent={"pragmatist": ["too big & slow"]})))
    assert "No consensus after 4 rounds" in text and "pragmatist" in text and "too big &amp; slow" in text


def test_summary_mentions_warnings_and_errors():
    text = "".join(summary_html(result(warnings=["w1", "w2"], error="the moderator failed: down")))
    assert "2 warnings" in text and "the moderator failed" in text


def test_long_summary_is_split_without_breaking_entities():
    long = ("word & <tag> " * 2000).strip()
    parts = summary_html(result(decision=long))
    assert len(parts) > 1 and all(len(p) <= LIMIT for p in parts)
    for p in parts:
        assert p.count("&") == p.count("&amp;") + p.count("&lt;") + p.count("&gt;")  # no entity cut in half


def test_markdown_has_every_round_and_role():
    md = debate_markdown(result())
    for needle in ["Cache <reports> & more?", "## Proposals", "### architect", "abstained", "## Round 1", "## Round 2",
                   "no metric", "accepted", "fair", "D2", "## Result", "Use a <b>small</b> cache", "$0.0123"]:
        assert needle in md, needle


def test_a_giant_word_is_cut_between_entities():
    from orchestrator.render import _chunks

    parts = _chunks("a&b" * 50, 40)
    assert all(len(p) <= 40 for p in parts)
    assert "".join(parts) == "a&amp;b" * 50
    assert all(p.count("&") == p.count("&amp;") for p in parts)
