# Local Globus Compute endpoint (Docker)

Runs a Globus Compute endpoint in a container so the flow's `ExtractMetadata` step can run `scripts/extract_powerball_metadata.py` against files on your machine. Intended for testing, not production.

Status: the image builds, the interactive login works, and the endpoint starts and connects to Globus. Registering the function and running it from the flow have not been verified yet.

## How it fits together

- The container runs `globus-compute-endpoint` on Python 3.11 as a non-root user. (As root, the endpoint is set up as a multi-user endpoint and fails asking for `--contact-email`.) It only makes outbound connections, so no ports are opened.
- Your `DATA_DIR` folder (the destination folder, `~/globus-destination`) is mounted at `/data`. Only this folder is visible to the endpoint, so the file reaches the endpoint only after the flow transfers it. Keep the source folder (`~/globus-source`) outside `DATA_DIR`.
- `../scripts` is mounted read-only at `/scripts`, so you can register the function from inside the container with the same Python and SDK versions as the endpoint.
- The `compute-config` volume holds the endpoint's config, UUID, and Globus login, so they survive restarts.
- The container runs with `init: true` so the endpoint shuts down cleanly on stop.

## Prerequisites

- Docker with Compose v2 (`docker compose`)
- A Globus account
- Globus Connect Personal, with a collection that shares two folders: a source folder (`~/globus-source`) and a destination folder (`~/globus-destination`, which is `DATA_DIR`)

## Set up

1. Create your environment file.

   ```bash
   cd docker
   cp .env.example .env
   ```

2. Edit `.env`.
   - `DATA_DIR`: absolute path of the destination folder, for example `/Users/<you>/globus-destination`. Compose does not expand `~` here.
   - `GLOBUS_COMPUTE_CLIENT_ID` / `GLOBUS_COMPUTE_CLIENT_SECRET`: leave empty for now. See "Authentication" below.

   `.env` is git-ignored. Never commit it.

3. Build the image and log in interactively, once. The login prompt needs a terminal to accept the code, so do not start the container in the background yet.

   ```bash
   docker compose build
   docker compose run --rm compute-endpoint
   ```

   Open the printed login URL, sign in as yourself, and paste the code at the prompt. The endpoint then starts in that terminal and prints its UUID. The login is saved in the `compute-config` volume.

4. Press Ctrl+C to stop it, then start it in the background. A `ProcessLookupError: No such process` traceback on Ctrl+C is harmless: it happens during shutdown, after the endpoint has stopped.

   ```bash
   docker compose up -d
   ```

   `docker compose logs` will be mostly empty. The endpoint writes to a log file; see "Day-to-day" for how to read it. A healthy start ends with `Awaiting messages from queue` and `Ready to send results` lines in that file.

5. Get the endpoint UUID.

   ```bash
   docker compose exec compute-endpoint globus-compute-endpoint list
   ```

   Copy the UUID into the flow input as `compute.endpoint_id`.

## Register the function

Run this inside the container. The first run prints a login URL and asks for the code you receive after signing in.

```bash
docker compose exec -it compute-endpoint python /scripts/extract_powerball_metadata.py
```

It prints `function_id: <uuid>`. Put that in the flow input as `compute.function_id`.

## Flow input paths

The container sees `DATA_DIR` at `/data`. Set `compute.file_path` to the transferred file's path under `/data`. The collection shows real host paths, so a destination of `/Users/<you>/globus-destination/powerball_sample.json` is `/data/powerball_sample.json` in the container:

```json
"file_path": "/data/powerball_sample.json"
```

Check that the file is visible to the endpoint after a transfer:

```bash
docker compose exec compute-endpoint ls -l /data
```

If it is not there, `DATA_DIR` is not the folder the destination path points to. Before the transfer, `/data` should be empty: that confirms the source file is not visible to the endpoint.

## Values for the flow input

| Flow input | Value |
|---|---|
| `compute.endpoint_id` | Endpoint ID from `globus-compute-endpoint list` |
| `compute.function_id` | Printed by the registration command |
| `compute.file_path` | Path under `/data`, as the container sees it |

The endpoint and function must both be created with your own Globus login so that the flow, which runs as you, is allowed to use them.

## Authentication

Use your own login (the default above) for the first test. An endpoint registered with a client ID and secret is owned by that client identity. The flow runs as you, so it may be refused when it submits to that endpoint, and a function registered under the client may not be usable by you. If you need a client identity later, review the endpoint's access policy settings in the Globus Compute docs first.

## Day-to-day

| Task | Command |
|---|---|
| Status | `docker compose ps` |
| Endpoint log (it writes to a file, so `docker compose logs` is mostly empty) | `docker compose exec compute-endpoint tail -f /home/compute/.globus_compute/powerball-local/endpoint.log` |
| Container output (login prompts, startup errors) | `docker compose logs -f compute-endpoint` |
| Restart | `docker compose restart compute-endpoint` |
| Shell inside | `docker compose exec -it compute-endpoint sh` |
| Rebuild after Dockerfile changes | `docker compose up -d --build` |

The compose file sets `restart: unless-stopped`, so the endpoint comes back when Docker restarts. It stops for good only after `docker compose stop` or `down`.

## Troubleshooting

- **Logs keep printing "Please authenticate with Globus here" and the container restarts.** A background container cannot take the login code. Run `docker compose down`, then do the interactive login in step 3 of "Set up".
- **`Email must be specified via --contact-email for multi-user endpoints`.** The endpoint was configured as root. Make sure the Dockerfile has `USER compute`, then run `docker compose down --volumes` (the old config is stored in the volume) and `docker compose up -d --build`.
- **Permission denied on `/data`.** The container user has UID 1000. On Linux, make `DATA_DIR` readable and writable for that UID, or change the UID in the Dockerfile to match yours (`id -u`).
- **`PermissionError` creating `/home/compute/.globus_compute/powerball-local`.** A named volume mounted at a path that does not exist in the image is created root-owned. The Dockerfile creates that directory owned by `compute` to prevent this. If you hit it on an old volume, run `docker compose down --volumes` and `docker compose up -d --build`.
- **Container exits right after starting.** Read `docker compose logs compute-endpoint` for the error. The endpoint stays in the foreground by design, so an immediate exit is a real failure.
- **Endpoint reports already running or won't start after an unclean stop.** A stale PID file may be left in the config volume. Check `docker compose exec compute-endpoint ls /home/compute/.globus_compute/powerball-local`, remove the stale PID file, and restart.
- **Flow's `ExtractMetadata` fails with an endpoint or permission error.** Confirm the endpoint is running and was registered with your own login, not a client identity.
- **Function errors about versions or serialization.** The function must be registered with the same Python version (3.11) and a matching `globus-compute-sdk`. Registering through the container, as above, guarantees that.
- **File not found.** Compare `compute.file_path` with the `ls` output above.
- **Login code rejected.** Authorization codes are single use and expire quickly. Request a fresh login URL by running the command again.
- **`DATA_DIR` errors on compose commands.** The compose file has no default for `DATA_DIR`, so it must be set in `.env`.

## Tear down

Choose the level you need. Each step is separate, and later steps cannot be undone.

### 1. Stop the endpoint (keeps everything)

```bash
cd docker
docker compose stop
```

Start it again with `docker compose start`. The endpoint UUID, config, and login are kept.

### 2. Remove the container (keeps the endpoint config)

```bash
docker compose down
```

This removes the container and network but keeps the `compute-config` volume. `docker compose up -d` brings back the same endpoint.

### 3. Full removal

Do these in order.

1. Delete the endpoint registration from Globus while the config volume still exists. Start the container if it is down, then:

   ```bash
   docker compose up -d
   docker compose exec compute-endpoint globus-compute-endpoint stop powerball-local
   docker compose exec compute-endpoint globus-compute-endpoint delete powerball-local --yes
   ```

   If `delete` rejects `--yes` on your version, run it without the flag and confirm when asked. Run `globus-compute-endpoint --help` if the commands differ.

2. Remove the container, network, and config volume. This deletes the endpoint's local config and your saved Globus login.

   ```bash
   docker compose down --volumes
   ```

3. Remove the image.

   ```bash
   docker compose down --rmi local --volumes
   ```

   (This single command also covers step 2. Use it instead if you prefer one step.)

4. Optional cleanup:
   - Delete the registered function by its UUID using the Globus Compute SDK (`Client().delete_function(function_id)`), if you no longer need it.
   - If you created a Globus client for headless login, delete or rotate its secret at <https://app.globus.org/settings/developers>.
   - Remove your local `.env` if it holds credentials: `rm .env`.
   - Quit Globus Connect Personal, or remove the shared folder from its settings, if you no longer want that collection.

### Verify nothing is left

```bash
docker compose ps -a
docker volume ls | grep compute-config
docker images | grep compute
```

All three should return nothing. You can also check that the endpoint no longer appears at <https://app.globus.org/compute>.
