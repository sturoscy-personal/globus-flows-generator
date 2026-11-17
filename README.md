# flows-generator

A Globus Flow that moves a data file, extracts metadata from it with Globus Compute, and loads that metadata into Globus Search. The example data is Powerball draws (`data/powerball.json`, 2,023 draws): the flow creates one Search entry per draw plus one summary entry per file.

This is a test and learning project. Most parts have been run end to end against live Globus services, but see [Known limits](#known-limits).

## What it does

```
Source collection ──► Transfer ──► ExtractMetadata ──► Ingest ──► NotifySuccess
 (~/globus-source)   (to dest)     (Compute function    (summary    (email the
                                    ingests one entry    entry)      runner)
                                    per draw)
```

1. **Transfer** copies one file from the source collection to the destination collection.
2. **ExtractMetadata** runs a Globus Compute function on your endpoint. It reads the transferred file, ingests one Search entry per draw (subject `powerball-draw-<date>`), and returns a dataset summary.
3. **Ingest** stores that summary as one entry in the same index, under the subject you give in the input.
4. **NotifySuccess** emails the person who started the run, using your SMTP server.

If Transfer, ExtractMetadata or Ingest fails, a cleanup step deletes the destination file and the run ends in a `Fail` state with a specific error (`TransferFailed`, `ComputeFailed`, `IngestFailed`, or `CleanupFailed`). A failed email ends the run as `NotifyFailed`, with no cleanup.

The Compute endpoint can only see the destination folder, so the file reaches it only after the transfer. Details are in [docker/README.md](docker/README.md).

## What is in this repo

| Path | Purpose |
|---|---|
| `flow.json` | The flow definition (12 states). |
| `schema.json` | The flow's input schema. The Globus web app renders it as the start form. |
| `input.example.json` | Template for a run's input. Copy it and fill in your values. |
| `scripts/extract_powerball_metadata.py` | The Compute function. Running the script registers it and prints a function ID. |
| `docker/` | A local Compute endpoint in Docker. See [docker/README.md](docker/README.md). |
| `dashboard/powerball-dashboard.html` | Standalone dashboard that queries the Search index live from your browser. |
| `data/` | `powerball.json` (full) and `powerball_sample.json` (first 100 draws, for testing). |

`test-input.json`, `full-input.json` and `docker/.env` hold credentials or your own IDs and are git-ignored.

## Prerequisites

- A Globus account, and the [Globus CLI](https://docs.globus.org/cli/) (`globus login`).
- Docker with Compose v2.
- Globus Connect Personal, with one collection that shares two folders on your computer: `~/globus-source` (holds the input file) and `~/globus-destination` (receives it).
- A Globus Search index you own.
- A Globus client (ID and secret) with the writer role on that index. The Compute function uses it to write the per-draw entries. Register one at <https://app.globus.org/settings/developers>.
- An SMTP server and credentials, for the success email.

## Set up

1. **Create the folders** and put the data file in the source folder:

   ```bash
   mkdir -p ~/globus-source ~/globus-destination
   cp data/powerball_sample.json ~/globus-source/
   ```

   Share both folders in Globus Connect Personal. The destination needs write access.

2. **Create a Search index** (the CLI command is `globus search index create`) and give your client the writer role on it.

3. **Start the Compute endpoint.** Follow [docker/README.md](docker/README.md). It covers the one-time interactive login, the environment file (including the `GLOBUS_SEARCH_CLIENT_*` values), and how to get the endpoint ID.

4. **Register the function** and note the function ID it prints:

   ```bash
   cd docker
   docker compose exec -it compute-endpoint python /scripts/extract_powerball_metadata.py
   ```

   Register again whenever you change the script, because each registration produces a new function ID.

5. **Deploy the flow:**

   ```bash
   globus flows create "Powerball transfer and ingest" flow.json --input-schema schema.json
   ```

   Save the flow ID. To update it later: `globus flows update FLOW_ID --definition flow.json --input-schema schema.json`.

## Run it

1. Copy `input.example.json` to `test-input.json` and fill in your IDs, paths and SMTP settings. The `compute.file_path` is the destination file's path as the container sees it: the destination folder is mounted at `/data`. See [docker/README.md](docker/README.md#flow-input-paths).

2. Start a run:

   ```bash
   globus flows start FLOW_ID --input test-input.json
   ```

   Use the sample file first. For the full data, copy `data/powerball.json` into `~/globus-source/`, update the three paths and the subject, and run again.

3. Follow the run in the web app at <https://app.globus.org/runs>. The first run asks you to consent to the Transfer, Compute, Search and notification scopes.

The flow runs every step as the person who starts it. It is private to you by default.

## Check the results

- **In the index:** the entry count should be the number of draws plus the summary entries (2,023 draws plus summaries for the full file).
- **Dashboard (browser):** open `dashboard/powerball-dashboard.html`. If your browser blocks the requests from a local file, serve the folder with `python3 -m http.server 8000` and open it from localhost.
- **Dashboard (Cowork):** the same charts also exist as a Cowork artifact named `powerball-dashboard`, which reads the index through the connected Search tool.

Both dashboards use anonymous Search queries, so they see only entries with `visible_to: public`.

## Tear down

- **The endpoint and container:** see "Tear down" in [docker/README.md](docker/README.md#tear-down).
- **The flow:** `globus flows delete FLOW_ID`.
- **The index:** delete it from the Globus web app, or leave it. Re-running the flow replaces entries with the same subject instead of duplicating them.
- **The client:** delete or rotate the client secret at <https://app.globus.org/settings/developers>.

## Known limits

- **One file per run.** The Transfer item has no `recursive` flag, so the flow is for single files, not directories.
- **Cleanup deletes the destination path.** Never set the destination equal to the source, and use a dedicated folder.
- **No cleanup of Search entries.** If the function fails partway, entries already ingested stay in the index. Re-running replaces them because subjects are stable.
- **The function is Powerball-specific.** It expects a JSON array of draws with `draw_date`, `winning_numbers`, `multiplier` and `double_play_winning_numbers`.
- **The number pools changed in 2015** (white balls 1–59 became 1–69, Powerball range changed). Raw counts are not comparable across eras. The dashboard's "per eligible draw" view corrects the white-ball counts.
- **The email step needs real SMTP settings.** Without them, a run ends as `NotifyFailed`, after the data has been transferred and indexed.

## References

- [Globus Flows documentation](https://docs.globus.org/api/flows/), including [hosted action providers](https://docs.globus.org/api/flows/hosted-action-providers/) and the [Search ingest action provider](https://docs.globus.org/api/flows/hosted-action-providers/ap-search-ingest/)
- [Authoring flows](https://docs.globus.org/api/flows/authoring-flows/)
- [Transfer action providers](https://docs.globus.org/api/transfer/action-providers/)
- [Globus Search documentation](https://docs.globus.org/api/search/)
- [Globus Compute documentation](https://globus-compute.readthedocs.io/)
- [Globus SDK for JavaScript](https://github.com/globus/globus-sdk-javascript) (used by the browser dashboard)
