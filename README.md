# gpty plugins

The plugin index for [gpty](https://github.com/godot-pty/gpty). The docs site's
browse page renders this file; `registry.json` is the whole content.

## Use a listed plugin

```sh
gpty plugin install godot-pty/gpty-omp
```

Installing never consults the registry: the command clones the repo you name,
validates its `gpty-plugin.toml` with the shipped validator, and asks a human to
review it in the gpty GUI before anything installs — a plugin's content runs as
you, so acceptance is explicit and pinned to the revision you reviewed. The
registry is a catalog: display data only, and nothing in it executes.

## Entries

| field | rule |
|---|---|
| `id` | `owner/repo`, lowercase `[a-z0-9-]`, each part ≤ 63 — exactly the plugin repo's path, and the id its manifest must declare |
| `repo` | `https://github.com/<id>` |
| `name` | display name, 1–64 characters, one line |
| `description` | one line, 1–200 characters. The registry owns this wording — the manifest has no description field |
| `category` | one of `agent`, `editor`, `git`, `multiplexer`, `utility` |
| `min_gpty_version` | the floor the plugin's manifest declares, `X.Y.Z` |
| `platforms` | a non-empty subset of `linux`, `macos`, `windows`, mirroring the manifest |

Unknown keys are rejected (the schema is closed), and the index holds at most
256 entries.

## Add a plugin

A plugin is a repository containing `gpty-plugin.toml` — its schema is the
plugin-manifest section of gpty's `AGENTS.md`, and the CLI's validator is
authoritative. To list a plugin here, open a PR that adds one entry to
`registry.json`. CI runs

```sh
python3 validate.py --check-repos
```

which checks the index structure and then fetches
`https://raw.githubusercontent.com/<id>/HEAD/gpty-plugin.toml` from each listed
repo, requiring it to agree with the entry: `id`, `name`, `min_gpty_version`,
`platforms`, a `X.Y.Z` version, and that the manifest ships at least one
profile / action / event / concept / link handler. Run the same command locally
before pushing. A weekly scheduled run repeats it, so a repo that vanishes or
renames is noticed without waiting for the next PR.

## Policy

- **An id is owned by its repo.** The id is the repo path and does not change
  while the repo exists; renaming or moving a plugin means a new id and the
  removal of the old entry, and nothing else may claim an id that is in use.
- **`min_gpty_version` is a floor the registry states**, not an install gate —
  the CLI's own check is the gate. CI holds it equal to the manifest's at the
  revision it fetched, so a reader learns what they need before installing.
- **Removal stops new installs only.** An install is pinned to a commit SHA, so
  deleting an entry never breaks an existing install; there is no yank
  machinery and none is needed. Entries are removed when their repo is gone
  (the weekly run flags it) or when the owner asks.

## License

[Apache-2.0](LICENSE) — index data, same terms as gpty's shipped defaults.
