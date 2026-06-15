# Forge Commands

This document describes each `forge` command, the options it accepts, and the
runtime behavior shared across commands.

## Common Behavior

All Forge commands start a container from the configured runtime image and mount
the selected workspace into the container at `/workspace`.

Forge also mounts host authentication state needed by in-container tools:

- `~/.codex` is mounted at `/home/forge/.codex`
- `$HOME/.config/gh` is mounted at `/home/forge/.config/gh` as read-only

The container entrypoint remaps the in-container `forge` user to the invoking
host UID and GID, so files created in the workspace keep host-compatible
ownership.

### Shared Options

These options apply to every command:

- `--image IMAGE`
  Use a different runtime image instead of the default
  `ghcr.io/dbrennand/forge:latest`.

- `--keep-container`
  Leave the container behind after it exits instead of auto-removing it.

- `--volume HOST:CTR[:ro|rw]`
  Add an extra bind mount. Repeat the flag to add more than one mount.

Notes about `--volume`:

- `HOST` may be absolute or relative to the current working directory.
- `CTR` must be an absolute container path.
- The optional mode defaults to `rw`.
- Extra mounts cannot overlap Forge-managed paths such as `/workspace`,
  `/home/forge/.codex`, `/home/forge/.config/gh`, or the SSH agent socket path.

### Image Selection

Forge resolves the runtime image in this order:

1. `--image`
2. `FORGE_IMAGE`
3. `ghcr.io/dbrennand/forge:latest`

### Forwarded Environment

Forge forwards a limited set of host environment variables into the container
when they are present:

- `OPENAI_API_KEY`
- `GITHUB_TOKEN`
- `GH_TOKEN`
- `TERM`
- `COLORTERM`
- `LANG`
- `LC_ALL`

## SSH Agent Mounting

When the host session has a valid `SSH_AUTH_SOCK`, Forge mounts SSH agent access
into the container automatically and sets `SSH_AUTH_SOCK` inside the container.
This allows tools such as `git` to use the host SSH agent without copying keys
into the image.

Behavior by platform:

- On Linux and other non-macOS hosts, Forge mounts the resolved host socket path
  directly.
- On macOS, Forge uses the container runtime host-services socket at
  `/run/host-services/ssh-auth.sock` as the mount source. This matches Docker
  Desktop's documented SSH agent forwarding approach for Mac and Linux:
  [Docker Desktop networking how-tos](https://docs.docker.com/desktop/features/networking/networking-how-tos/#network-how-tos-for-mac-and-linux).

Inside the container, the socket is exposed at:

- `/tmp/forge-ssh-auth.sock`

If `SSH_AUTH_SOCK` is unset, missing, or not a real socket, Forge skips this
mount.

## `forge run`

Run Codex non-interactively against a workspace.

Synopsis:

```bash
forge run --workspace /path/to/repo [options] "prompt"
```

Options:

- `--workspace PATH`
  Required. Mount the workspace at `/workspace`.

- `--yolo`
  Run `codex exec` with approval and sandbox bypass enabled.

- `--image IMAGE`
- `--keep-container`
- `--volume HOST:CTR[:ro|rw]`

Behavior:

- Runs `codex exec` inside the container.
- Sets the working directory to `/workspace`.
- Uses Codex ephemeral execution mode.
- Uses workspace-write sandboxing unless `--yolo` is set.
- Adds `--skip-git-repo-check` automatically when the workspace is not a Git
  repository or worktree.

Examples:

```bash
forge run --workspace ~/src/forge "Summarize this repository"
forge run --workspace ~/src/forge --volume ~/notes:/notes:ro "Compare the code to /notes/design.md"
forge run --workspace ~/src/forge --yolo "Apply the requested refactor and run tests"
```

## `forge codex`

Start an interactive Codex session inside the container.

Synopsis:

```bash
forge codex /path/to/repo [options]
```

Options:

- `PROJECT`
  Required positional workspace path. Mounted at `/workspace`.

- `--yolo`
  Run Codex with approval and sandbox bypass enabled.

- `--image IMAGE`
- `--keep-container`
- `--volume HOST:CTR[:ro|rw]`

Behavior:

- Runs interactive `codex` inside the container.
- Sets the working directory to `/workspace`.
- Uses workspace-write sandboxing with on-request approvals unless `--yolo` is
  set.
- Adds `--skip-git-repo-check` automatically when the workspace is not a Git
  repository or worktree.

Examples:

```bash
forge codex ~/src/forge
forge codex ~/src/forge --volume ~/scratch:/scratch
forge codex ~/src/forge --image ghcr.io/dbrennand/forge:0.1.0
```

## `forge shell`

Open an interactive shell in the prepared Forge runtime without launching
Codex.

Synopsis:

```bash
forge shell /path/to/repo [options]
```

Options:

- `PROJECT`
  Required positional workspace path. Mounted at `/workspace`.

- `--image IMAGE`
- `--keep-container`
- `--volume HOST:CTR[:ro|rw]`

Behavior:

- Starts `/bin/bash` inside the runtime container.
- Sets the working directory to `/workspace`.
- Does not enable nested Codex sandbox settings because Codex is not launched.

Examples:

```bash
forge shell ~/src/forge
forge shell ~/src/forge --volume ~/.ssh:/tmp/host-ssh:ro
forge shell ~/src/forge --keep-container
```
