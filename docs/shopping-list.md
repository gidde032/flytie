# Shopping list cookbook

`flytie shop` turns any set of patterns into a single deduplicated list of
materials — the thing you actually take to the fly shop. This guide covers how
it works and the practical ways to use it.

## How it works

You select patterns three ways, and they combine. Every flag is repeatable:

```bash
flytie shop --pattern "Parachute Adams" --pattern "Zebra Midge"
flytie shop --tag dry
flytie shop --species "rainbow trout" --tag nymph
```

flytie then collects the materials from the current version of every selected
pattern and **deduplicates** them:

- Materials are matched by their canonical name, so `Grizzly Hackle` and
  `grizzly hackle` are treated as the same item.
- Quantities are summed **when the units match**. Unit comparison is
  case-insensitive, so `feather` and `Feather` combine cleanly.
- A material that appears both with and without a quantity shows a `?` marker
  (`?` means "some unquantified amount", and `5+?` means "at least 5, plus
  more from patterns that didn't specify").

The result is grouped by material category (thread, hook, hackle, …) so the
list reads in the order you'd shop.

## Recipe: a weekend trip list

Tag the patterns you plan to tie for the trip, then shop the tag:

```bash
flytie tag add "Parachute Adams" octobertrip
flytie tag add "October Caddis" octobertrip
flytie shop --tag octobertrip
```

## Recipe: leave out what you already own

`--exclude` (repeatable) drops materials you already have, so the list is only
what you need to buy:

```bash
flytie shop --tag octobertrip \
  --exclude "black thread" \
  --exclude "head cement"
```

## Recipe: a Markdown checklist

`--format markdown` produces a list you can paste into notes or a checklist
app:

```bash
flytie shop --tag octobertrip --format markdown > trip-list.md
```

`--format text` produces the same content as plain text with no Markdown
markup — handy for printing or pasting somewhere that doesn't render Markdown.

## Recipe: feed the list to another tool

`--format json` emits structured data you can pipe into a script — for
example, to cross-check against a spreadsheet inventory:

```bash
flytie shop --tag octobertrip --format json | jq '.items[].canonical_name'
```

## Tips

- If two patterns spell a material slightly differently (`hare's ear dubbing`
  vs `hares ear dubbing`), they will **not** merge. Keep material names
  consistent when adding patterns, or edit the older pattern to match.
- `shop` always uses each pattern's **current** version. To shop an older
  recipe, `flytie restore` it first so it becomes current again.
- There's no limit on how many `--pattern` / `--tag` / `--species` flags you
  combine — build the list however you think about the trip.
