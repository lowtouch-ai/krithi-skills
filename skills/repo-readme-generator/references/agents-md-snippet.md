# AGENTS.md integration

Add this block to the repository's `AGENTS.md` (create the file if the user wants it) so Codex keeps the README current during normal development. Only edit AGENTS.md when the user asks for it or approves; keep any existing content and place this under its own heading. If a CLAUDE.md is the repo's instruction file, offer the same block there.

```markdown
## README maintenance

The root `README.md` documents architecture, setup, build, run, test and configuration. Keep it accurate as part of every change.

Update the README and the affected files under `docs/` (use the `repo-readme-generator` skill in update mode) when a change:
- adds, removes, renames or re-wires a service, module, package or major directory;
- changes an entry point, port, route, public API, event, or CLI command;
- adds or changes a build, run, test or lint command, or a package.json / Makefile / pyproject script;
- adds, removes or changes an environment variable or config file;
- changes a runtime or dependency version requirement, a datastore, or an external integration;
- changes Dockerfiles, compose files, CI/CD workflows or infrastructure code.

Before finishing such a change:
1. `python <skill-dir>/scripts/check_drift.py README.md --docs docs` and fix what it reports.
2. Edit only the affected README sections; preserve accurate existing text.
3. `python <skill-dir>/scripts/validate_docs.py` (or `validate_readme.py README.md` if there is no `docs/` folder) and resolve errors.
   If you changed a diagram spec in `docs/diagrams/src/`, re-run `make_svg.py` for it.
4. Mention in the final message which README sections changed.

Never document behavior that is not implemented; mark it `Planned` or `TBD`.

## Code comments

New or changed code must carry adequate comments: explain non-obvious logic, intent and the reason for the change, following the repository's comment style. Do not add comments that only restate the code.

## Commit messages and pull requests

Write descriptive commit messages and PR descriptions, never a single line. A commit message has a short summary line plus a body that covers every change in that commit (what changed, in which files or components, and why). A PR description covers every item in the PR: a summary, the list of changes, and how it was tested or verified.
```

`<skill-dir>` is the installed skill folder, for example `~/.codex/skills/repo-readme-generator`.
