# agent-orchestrator

Ask a question or describe a decision you are weighing. Several agents with fixed roles, each on its own
model, answer it independently and then argue in rounds until all of them accept one answer. You get
the decision, the reasons, and every objection that was still open at the end. A disagreement is never
averaged away. The full debate is one tap away. It runs as a Telegram bot or from the command line, and
**without any API keys** in demo mode.

> I built the original as a personal tool, a Telegram bot that sped up my own design decisions. Its
> code was lost, so this repo is a rebuild from scratch. It keeps what defined the original: one bot,
> the debate happens inside it, the roles and their models are fixed, rounds continue until everyone
> agrees, and the reply is the result plus a collapsed record of the debate. The exact protocol below
> belongs to the rebuild.

## Run it

Needs Python 3.12+.

```bash
git clone https://github.com/kotiniiqq/agent-orchestrator && cd agent-orchestrator
python -m venv .venv && . .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[dev]"

orchestrator ask "Do we need Kubernetes for three services?" --transcript debate.md
```

```
Decision
  On "Do we need Kubernetes for three services?": start with a small version behind a flag, and keep it cheap.

Why
  - A small working version shows real problems early.
  - A flag keeps the way back short.

Dissent
  - pragmatist: A flag and a metric are more than the first step needs.

No consensus after 4 rounds
```

`debate.md` holds every proposal, objection and ruling. Without a key, a scripted demo client plays
the agents. The script depends only on the question, so the same question always plays out the same
way. The demo has three scripts: quick consensus, an objection that gets accepted, and a dissent that
lasts to the end. The text is a template; it shows the protocol, not real advice.

**Real models.** Add an [OpenRouter](https://openrouter.ai) key:

```bash
OPENROUTER_API_KEY=sk-or-... orchestrator ask "Postgres or MongoDB for an audit log?" --live
```

The status line then shows tokens and cost per debate, and the Markdown record breaks them down by role.

**Telegram bot.** Create a bot with @BotFather and copy `.env.example` to `.env`. Set
`TELEGRAM_BOT_TOKEN`, `ALLOWED_USER_IDS` (your Telegram user id; everyone else is refused), and
`MODE=live` with the key if you want real models. Then:

```bash
docker compose up -d --build        # or: orchestrator bot
```

While the agents argue, the bot edits one status message as the rounds pass. Then it sends the
summary with a **Show debate** button, which returns the full record as a `.md` file.

## The debate

```
question
   │
   ├─► architect ─┐
   ├─► critic ────┼─► proposals (independent, in parallel)
   └─► pragmatist ┘
                  │
            moderator: one draft
                  │
   ┌──────────────▼───────────────┐
   │ review round                 │  each participant: agree, or objections + the change it wants
   │   everyone agrees? ──► stop  │
   │ moderator rules on every     │  accepted → the draft changes
   │ objection, revises the draft │  rejected → with a reason
   └──────────────┬───────────────┘
                  │ at most MAX_ROUNDS (4)
                  ▼
   moderator: decision + reasons; objections still open = dissent
```

- **Roles and models are fixed** in [`roles.yaml`](roles.yaml).
  - The participants are an architect, a critic and a pragmatist. They vote.
  - The moderator merges the proposals, rules on objections and writes the result, but has no vote.
  - Model ids are plain OpenRouter ids. Change them to any models you can use.
- **Structured replies.** Every turn is a small JSON object, pulled out of whatever prose or code fences
  the model wraps it in. An invalid reply gets one retry with the error explained.
- **When an agent fails.**
  - After a second invalid reply, the agent abstains for the round, and the warning is recorded.
  - A timeout or an API error also counts as a failed turn.
  - Two failed turns in a row make an agent inactive. Consensus then needs every remaining agent, and at
    least two of them.
  - If the moderator fails, the debate stops with the last good draft and says so.
- **Records.** Every debate is stored in SQLite. The Show debate button only works for the user who
  asked.

## Tests

`pytest` runs 77 tests:
- **engine:** consensus, an accepted objection, the round limit with dissent, the invalid-JSON retry,
  abstention, timeouts, an agent going inactive, lost quorum, moderator failure, parallel calls, usage
  totals, repeated rulings;
- **JSON extraction:** code fences, prose, braces inside strings, wrong types;
- **the demo scripts** run end to end;
- **the OpenRouter client**, against recorded API responses (`respx`): request shape, usage and cost,
  401 and 429;
- **rendering:** HTML escaping, splitting under Telegram's 4096-character limit without cutting an
  entity in half, the Markdown record;
- **the store:** per-user access;
- **the CLI;**
- **the bot handlers**, on fake Telegram objects: the allowlist (refused messages are not logged), status
  updates, the summary and its button, one debate per user at a time, crash handling, the debate file
  for its owner only.

CI also runs a demo debate from the command line and builds the container.

The live mode is tested against recorded API shapes, not against OpenRouter itself.

## Layout

```
src/orchestrator/
  engine.py      the debate
  prompts.py     prompts for each phase
  llm.py         OpenRouter client, scripted demo client
  jsonout.py     JSON extraction and checks
  roles.py       roles.yaml
  render.py      Telegram summary, Markdown record
  store.py       SQLite
  bot.py         Telegram bot (aiogram 3)
  cli.py, app.py, config.py
```

## Contact

Feedback, ideas, job offers or custom projects (n8n, MCP, AI automation): [kotiniiqq@gmail.com](mailto:kotiniiqq@gmail.com).
Bug reports and feature requests are welcome in [Issues](https://github.com/kotiniiqq/agent-orchestrator/issues).

## License

MIT
