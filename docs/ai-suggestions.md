# AI suggestions

`flytie suggest` asks the Anthropic Claude API which flies to tie for a given
species, season, and water — grounded in the patterns you already have. This
guide covers setup, exactly what data leaves your machine, and how to get good
results.

## Setup

Install the `ai` extra and set your API key:

```bash
pip install "flytie[ai]"
export ANTHROPIC_API_KEY=sk-ant-...
```

The key is read **only** from the `ANTHROPIC_API_KEY` environment variable. It
is never written to the config file, never logged, and never included in an
error message. flytie has no other way to obtain it — there is deliberately no
`config` key for it.

To keep the key set across shell sessions, add the `export` line to your
shell profile (`~/.zshrc`, `~/.bashrc`, etc.).

## What is — and isn't — sent to the API

Before each call, flytie prints a one-line notice telling you what it is about
to send. Specifically:

- **Sent:** the species, season, water, and conditions you typed; and, as
  grounding context, the **names, hook sizes, and material names** of patterns
  in your library (capped at 40 patterns, and at 12 materials per pattern).
- **Not sent:** your tying instructions, your notes, version history,
  timestamps, or anything else. The full database never leaves your machine.

This is a deliberate data-minimization choice: the model gets enough to ground
its suggestions in your style, and nothing more.

## Running a suggestion

`--species` and `--season` are required; `--water`, `--conditions`, and `--n`
are optional:

```bash
flytie suggest --species "rainbow trout" --season "late October"

flytie suggest -s "brown trout" --season fall \
  --water "Henry's Fork" --conditions "low and clear" --n 5
```

The response streams back and is rendered as a set of panels, one per
suggested fly, with its hook size, key materials, and a one-line rationale.

## Reading the output

Each suggestion carries a badge:

- **`[in library]`** — the fly already exists in your pattern library. The
  model is pointing you at something you can already tie.
- **`[NEW]`** — the fly is not in your library. You can add it directly
  using `--from-suggestion` (see below).

If the model returns more flies than `--n`, the list is trimmed to the number
you asked for.

## Saving and using suggestions

Every `flytie suggest` run automatically saves its results to a JSON file
in your data directory (`last_suggestions.json`). Only the most recent run
is kept — a new `suggest` call overwrites the previous results.

The suggestions are numbered in the output (1, 2, 3, …). You can reference
any suggestion by its number to create a new pattern:

```bash
# Add suggestion #2 as a new draft pattern
flytie add --from-suggestion 2
```

This creates the pattern with the suggestion's name, hook size, and materials
pre-filled. The pattern is marked as a **draft** (a note in the version
history indicates it originated from an AI suggestion) so you know to review
and refine it. Materials are added with category `other` — use `flytie edit`
or `flytie material categorize` (when available) to assign proper categories.

You can override the name or hook size at add time:

```bash
flytie add --from-suggestion 2 --name "My Custom PMD" --hook-size 16
```

If a pattern with the same name already exists, the command exits with an
error rather than silently overwriting — rename with `--name` or edit the
existing pattern instead.

**Important:** `--from-suggestion` references the *last* `suggest` run only.
If you run `suggest` again, the previous results are gone. Act on the
suggestions you want before running a new query.

## Writing good prompts

The more specific your inputs, the more useful the suggestions:

- **Season** accepts natural language — `late October` is better than `fall`,
  because hatch timing is specific.
- **Water** anchors the recommendation to a real fishery — `Henry's Fork`
  carries more signal than leaving it blank.
- **Conditions** is where local knowledge pays off — `low and clear`,
  `high and off-color`, or `first cold snap` all change the answer.

## When something goes wrong

flytie translates every failure into a plain, actionable message — you will
never see a raw traceback:

- **No API key** — exits with a reminder to set `ANTHROPIC_API_KEY`.
- **`ai` extra not installed** — tells you to `pip install "flytie[ai]"`.
- **Bad key / no credit (HTTP 401/403)** — tells you to check the key.
- **Rate limited (429) or overloaded (529)** — tells you to retry shortly.
- **No network** — tells you to check your connection.
- **Response cut off** — suggests retrying with a smaller `--n`.

## A note on cost

Each `flytie suggest` call is a real Anthropic API request and consumes API
credit on your account. It is not free and not unlimited — there is no usage
inside flytie itself, only the standard Anthropic API billing for the call you
make.
