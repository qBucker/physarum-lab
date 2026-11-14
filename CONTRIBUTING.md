# Contributing

This repository is an engineering record for a phase-0 instrument and analysis
pipeline. Contributions should preserve its auditability.

## Non-negotiable rules

1. **No personal identifiers or credentials.** Do not commit real names,
   institutional accounts, tokens, private keys, absolute home paths, or host
   identifiers. The public identity for this repository is the GitHub account
   `qBucker`.
2. **No evidence edits without a ledger.** Files under `data/` and
   `sim/results/` are evidence. Any change must be recorded in
   `SANITIZATION.md` or a dated ledger entry, and the affected `SHA256SUMS`
   must be regenerated.
3. **Label every number.** Use `measured`, `computed`, `projected`, or
   `assumed` as appropriate. A constant claim needs a derivative: state the
   range or the control variable that was varied.
4. **Public text.** No internal run diaries, no first-person narration, no
   metaphorical claims. Engineering report style.
5. **Relative paths only.** Scripts and documents must run from a repository
   checkout without a hard-coded home directory.

## Data

Raw acquisitions are tracked with Git LFS (`data/**/*.bin`,
`data/**/*.csv`). Run `git lfs install && git lfs pull` after cloning. Do not
rewrite raw files. New runs should follow `templates/meta.json` and include a
`SHA256SUMS` file covering every file in the run directory.

## Checks

```bash
python3 scripts/check_repo.py
```

The check verifies path hygiene, secret patterns, JSON syntax, metadata host
fields, and the small-file entries of every `SHA256SUMS`. Large LFS objects
are skipped in CI.
