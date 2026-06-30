# Compute hosts — bumblebee & nufan

How to run analysis jobs across the two machines. **nufan** is the preferred
host for CPU-bound work (registration, extract, scoring) — it's faster than the
local box.

## The two hosts

| | bumblebee | nufan |
|---|---|---|
| role | local interactive host | remote compute/build host |
| reach | — (you're on it) | `ssh nufan` (`nufan.local.nufan.net`) |
| OS / cores | Arch Linux, 8 cores | Ubuntu, **16 cores** (Ryzen 5800X) |
| `/home` | local btrfs | local |

## The NFS share (same path on both hosts)

`/home/alson/shared` is an NFS4 mount of `tafi.local.nufan.net:/export/home/staff/alson`
(nufan's storage). It is mounted at the **same path** `/home/alson/shared` on both
machines, so anything written under it from one host is immediately visible on the
other. **All the git repos live here** (`/home/alson/shared/projects/personal/fotografie/...`),
which is what lets you edit on bumblebee and run on nufan with no syncing.

### What is NOT on the share
- `/home/alson/macro-lens-test-output` (the raw capture output, ~500 GB) is
  **bumblebee-local** and does **not** exist on nufan.
- The capture data needed for analysis is mirrored onto the share under
  `/home/alson/shared/files/pics/digikam/test-raw-data/<date>/<session>/`. For the
  2026-05 rig sessions each session dir holds aperture subdirs
  (`f_5_6/ f_8/ f_11/ f_16/`) of `step_NNNN_*.jpg` plus a `shots.csv`
  (documented `rail_position_mm`, `magnification_indicated`, `f_ring`,
  `focal_length_mm`, `phase`, …). Always point nufan jobs at the share copy.
- nufan's `$HOME` reports `/home/alson` but binaries live under
  `/home/staff/alson` (export root `/export/home/staff/alson`). Don't hard-code
  home paths — use `$HOME` or the share path.

## Running on nufan over (non-interactive) ssh

Two gotchas with `ssh nufan '<cmd>'`:

1. **`uv` is only on PATH in a login shell.** It lives at `~/.local/bin/uv` on
   nufan; wrap the command in `bash -lc`.
2. **direnv does not auto-load** for non-interactive logins, so the per-project
   venv isn't activated. Activate it explicitly with **`direnv exec .`**
   (run `direnv allow .` once per repo the first time).

Canonical invocation:

```sh
ssh nufan 'bash -lc "cd /home/alson/shared/projects/personal/fotografie/analyse-lens-test/tile-sharpness \
  && direnv exec . uv run <cmd>"'
```

e.g. `uv run pytest -q`, or `PYTHONPATH=src uv run python scripts/<x>.py …`.
Shard CPU-bound stages across nufan's 16 cores.

For a one-off interactive session, run `! ssh nufan` from the Claude Code prompt.

## Per-host venvs (why `direnv exec` is required)

Each Python subproject's `.envrc` is:

```sh
export UV_PROJECT_ENVIRONMENT="$HOME/.cache/uv-venvs/$(basename "$PWD")"
```

This gives **each host its own venv** at `~/.cache/uv-venvs/<project>/`. A shared
`.venv` on NFS does **not** work across hosts running different distros (mismatched
compiled wheels) — hence the redirect. direnv loading `.envrc` is what points `uv`
at the correct per-host venv; if you bypass direnv you must export
`UV_PROJECT_ENVIRONMENT` yourself, but prefer `direnv exec .`.

## mtf_mapper

The `mtf_mapper` binary is built on nufan and called from bumblebee over SSH
(ControlMaster-multiplexed). See `tile-sharpness/README.md` "SSH setup" for the
build steps and the apt package list.
