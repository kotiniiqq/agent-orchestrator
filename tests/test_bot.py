import asyncio
import logging

from orchestrator.bot import BotDeps, handle_question, handle_show_debate, handle_start
from orchestrator.store import Store
from tests.test_transcript import result


class FakeUser:
    def __init__(self, uid):
        self.id = uid


class FakeMessage:
    def __init__(self, uid, text=None, log=None):
        self.from_user = FakeUser(uid)
        self.text = text
        self.log = log if log is not None else []

    async def answer(self, text, parse_mode=None, reply_markup=None):
        self.log.append(("answer", text, parse_mode, reply_markup))
        return FakeMessage(self.from_user.id, text, self.log)

    async def edit_text(self, text, **kw):
        self.log.append(("edit", text))

    async def answer_document(self, document, caption=None):
        self.log.append(("document", document.filename, document.data, caption))


class FakeCallback:
    def __init__(self, uid, data):
        self.from_user = FakeUser(uid)
        self.data = data
        self.message = FakeMessage(uid)
        self.answers = []

    async def answer(self, text=None, show_alert=False):
        self.answers.append((text, show_alert))


class FakeEngine:
    def __init__(self, on_event, gate=None):
        self.on_event = on_event
        self.gate = gate

    async def run(self, question):
        await self.on_event(("round", 0))
        await self.on_event(("round", 1))
        if self.gate:
            await self.gate.wait()
        return result(question=question)


def deps(tmp_path, gate=None):
    return BotDeps(engine_factory=lambda on_event: FakeEngine(on_event, gate), store=Store(tmp_path / "b.db"), allowed=frozenset({1}))


async def test_strangers_are_refused_and_their_text_is_not_logged(tmp_path, caplog):
    caplog.set_level(logging.INFO)
    m = FakeMessage(99, "my secret plan for the company")
    await handle_question(m, deps(tmp_path))
    assert m.log[0][0] == "answer" and "private" in m.log[0][1]
    assert len(m.log) == 1
    assert "secret" not in caplog.text and "99" in caplog.text


async def test_question_gets_status_updates_and_a_summary_with_a_button(tmp_path):
    d = deps(tmp_path)
    m = FakeMessage(1, "Should we cache the reports?")
    await handle_question(m, d)
    kinds = [x[0] for x in m.log]
    assert kinds[0] == "answer" and "edit" in kinds
    assert any(x[0] == "edit" and "round 1" in x[1] for x in m.log)
    final = [x for x in m.log if x[0] == "answer"][-1]
    assert final[2] == "HTML" and "<b>Decision</b>" in final[1]
    button = final[3].inline_keyboard[0][0]
    assert button.text == "Show debate" and button.callback_data == "debate:1"
    assert d.running == set()


async def test_bad_question_is_explained(tmp_path):
    m = FakeMessage(1, "hi")
    await handle_question(m, deps(tmp_path))
    assert "3 to 2000" in m.log[0][1]


async def test_one_debate_per_user(tmp_path):
    gate = asyncio.Event()
    d = deps(tmp_path, gate)
    first = asyncio.create_task(handle_question(FakeMessage(1, "first question?"), d))
    await asyncio.sleep(0.01)
    second = FakeMessage(1, "second question?")
    await handle_question(second, d)
    assert "still working" in second.log[0][1].lower()
    gate.set()
    await first
    assert d.running == set()


async def test_engine_crash_is_reported_and_releases_the_user(tmp_path):
    class Boom:
        async def run(self, q):
            raise RuntimeError("kaput")

    d = BotDeps(engine_factory=lambda on_event: Boom(), store=Store(tmp_path / "b.db"), allowed=frozenset({1}))
    m = FakeMessage(1, "a question?")
    await handle_question(m, d)
    assert "went wrong" in m.log[-1][1] and "kaput" not in m.log[-1][1]
    assert d.running == set()


async def test_show_debate_sends_the_markdown_only_to_its_owner(tmp_path):
    d = deps(tmp_path)
    debate_id = d.store.save(1, result())
    cb = FakeCallback(1, f"debate:{debate_id}")
    await handle_show_debate(cb, d)
    kind, filename, data, caption = cb.message.log[0]
    assert kind == "document" and filename == f"debate-{debate_id}.md" and b"## Round 2" in data
    other = FakeCallback(2, f"debate:{debate_id}")
    await handle_show_debate(other, d)
    assert other.message.log == [] and other.answers[0][1] is True


async def test_show_debate_with_garbage_data(tmp_path):
    cb = FakeCallback(1, "debate:abc")
    await handle_show_debate(cb, deps(tmp_path))
    assert cb.message.log == [] and cb.answers


async def test_start_explains_the_bot(tmp_path):
    m = FakeMessage(1, "/start")
    await handle_start(m, deps(tmp_path))
    assert "architect" in m.log[0][1] and "critic" in m.log[0][1]
    stranger = FakeMessage(5, "/start")
    await handle_start(stranger, deps(tmp_path))
    assert "private" in stranger.log[0][1]


def test_dispatcher_registers_the_handlers(tmp_path):
    from orchestrator.bot import build_dispatcher

    dp = build_dispatcher(deps(tmp_path))
    assert len(dp.message.handlers) == 3 and len(dp.callback_query.handlers) == 1
