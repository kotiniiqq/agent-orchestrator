from orchestrator.cli import main
from orchestrator.llm import scenario


def q_for(s):
    return next(f"Should we split the monolith? #{i}" for i in range(100) if scenario(f"Should we split the monolith? #{i}") == s)


def test_demo_run_prints_the_result_and_writes_the_debate(tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path.parent)  # roles.yaml is found via ROLES_PATH
    out_md = tmp_path / "debate.md"
    import os
    roles = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "roles.yaml"))
    code = main(["ask", q_for(2), "--transcript", str(out_md)], env={"ROLES_PATH": roles})
    out = capsys.readouterr()
    assert code == 0
    assert "Decision" in out.out and "Dissent" in out.out and "pragmatist" in out.out
    assert "No consensus after 4 rounds" in out.out
    assert "round 1" in out.err  # progress goes to stderr
    assert "## Round 4" in out_md.read_text(encoding="utf-8")


def test_rounds_flag_and_consensus(capsys):
    code = main(["ask", q_for(1), "--rounds", "2"], env={})
    assert code == 0 and "Consensus after 2 rounds" in capsys.readouterr().out


def test_bad_question_and_live_without_key(capsys):
    assert main(["ask", "hi"], env={}) == 2
    assert "3 to 2000" in capsys.readouterr().err
    assert main(["ask", "a real question", "--live"], env={}) == 2
    assert "OPENROUTER_API_KEY" in capsys.readouterr().err


def test_demo_output_has_no_made_up_costs_and_is_ascii_safe(capsys):
    main(["ask", q_for(0)], env={})
    out = capsys.readouterr().out
    assert "tokens" not in out and "$" not in out and "·" not in out
