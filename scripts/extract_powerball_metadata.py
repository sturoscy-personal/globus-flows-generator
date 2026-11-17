"""Globus Compute function: ingest one Search entry per Powerball draw, and
return a dataset-level summary for the flow's own ingest step.

Register once, then put the printed function ID in the flow input:
    python scripts/extract_powerball_metadata.py
Run it in the same Python/globus-compute-sdk environment as the endpoint.

The endpoint needs these environment variables (a Globus client that has the
writer role on the target index):
    GLOBUS_SEARCH_CLIENT_ID
    GLOBUS_SEARCH_CLIENT_SECRET
"""


def extract_and_ingest(path, search_index, visible_to, batch_size=500, timeout=900):
    import hashlib
    import json
    import os
    import time
    from collections import Counter

    import globus_sdk

    with open(path, "rb") as fh:
        raw = fh.read()
    rows = json.loads(raw)
    if not isinstance(rows, list) or not rows:
        raise ValueError("expected a non-empty JSON array of draws")

    file_name = os.path.basename(path)

    def to_ints(text):
        return [int(n) for n in text.split()] if text else []

    # One Search document per draw. The subject is the draw date, so
    # re-running the flow replaces entries instead of duplicating them.
    gmeta = []
    subjects = set()
    for row in rows:
        draw_date = row["draw_date"][:10]
        subject = f"powerball-draw-{draw_date}"
        if subject in subjects:
            raise ValueError(f"duplicate draw date {draw_date}")
        subjects.add(subject)

        numbers = to_ints(row.get("winning_numbers"))
        double_play = to_ints(row.get("double_play_winning_numbers"))
        content = {
            "draw_date": draw_date,
            "winning_numbers": row.get("winning_numbers"),
            "white_balls": numbers[:5],
            "powerball": numbers[5] if len(numbers) > 5 else None,
            "multiplier": int(row["multiplier"]) if row.get("multiplier") else None,
            "double_play_winning_numbers": row.get("double_play_winning_numbers"),
            "double_play_white_balls": double_play[:5],
            "double_play_powerball": double_play[5] if len(double_play) > 5 else None,
            "source_file": file_name,
        }
        content = {k: v for k, v in content.items() if v not in (None, [])}
        gmeta.append({"subject": subject, "visible_to": visible_to, "content": content})

    client_id = os.environ.get("GLOBUS_SEARCH_CLIENT_ID")
    client_secret = os.environ.get("GLOBUS_SEARCH_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise RuntimeError(
            "GLOBUS_SEARCH_CLIENT_ID / GLOBUS_SEARCH_CLIENT_SECRET are not set "
            "on the Compute endpoint"
        )
    auth_client = globus_sdk.ConfidentialAppAuthClient(client_id, client_secret)
    authorizer = globus_sdk.ClientCredentialsAuthorizer(
        auth_client, "urn:globus:auth:scope:search.api.globus.org:all"
    )
    search = globus_sdk.SearchClient(authorizer=authorizer)

    task_ids = []
    for start in range(0, len(gmeta), batch_size):
        batch = gmeta[start:start + batch_size]
        response = search.ingest(
            search_index,
            {"ingest_type": "GMetaList", "ingest_data": {"gmeta": batch}},
        )
        task_id = response["task_id"]
        task_ids.append(task_id)
        deadline = time.time() + timeout
        while True:
            state = search.get_task(task_id)["state"]
            if state == "SUCCESS":
                break
            if state == "FAILED":
                raise RuntimeError(f"Search ingest task {task_id} failed")
            if time.time() > deadline:
                raise TimeoutError(f"Search ingest task {task_id} did not finish")
            time.sleep(2)

    dates = sorted(d["content"]["draw_date"] for d in gmeta)
    latest = max(gmeta, key=lambda d: d["content"]["draw_date"])["content"]
    return {
        "title": "Powerball winning numbers",
        "file_name": file_name,
        "file_size_bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "draw_count": len(rows),
        "entries_ingested": len(gmeta),
        "ingest_task_ids": task_ids,
        "first_draw_date": dates[0],
        "last_draw_date": dates[-1],
        "multiplier_counts": dict(
            Counter(str(d["content"].get("multiplier", "none")) for d in gmeta)
        ),
        "latest_draw": {
            "draw_date": latest["draw_date"],
            "winning_numbers": latest.get("winning_numbers"),
            "multiplier": latest.get("multiplier"),
        },
    }


if __name__ == "__main__":
    from globus_compute_sdk import Client

    print("function_id:", Client().register_function(extract_and_ingest))
