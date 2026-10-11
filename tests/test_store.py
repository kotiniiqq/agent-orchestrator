from orchestrator.store import Store
from tests.test_transcript import result


def test_round_trip_and_user_isolation(tmp_path):
    s = Store(tmp_path / "o.db")
    debate_id = s.save(42, result())
    q, md = s.get(debate_id, 42)
    assert q == "Cache <reports> & more?" and "## Round 2" in md
    assert s.get(debate_id, 7) is None
    assert s.get(999, 42) is None
    assert s.save(42, result()) == debate_id + 1
