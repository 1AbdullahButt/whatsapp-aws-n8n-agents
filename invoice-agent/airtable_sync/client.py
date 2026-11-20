"""Write rows to Airtable (Web API v0), and a fake for tests.

Free plan: 1,000 API calls per workspace per month. So we
  - send at most 10 records per request (Airtable's own limit),
  - count every request in self.calls,
  - upsert ("performUpsert") on a key field, so running the sync twice
    updates the same rows instead of creating duplicates.
"""
import time

import httpx

API_URL = "https://api.airtable.com/v0"
BATCH_SIZE = 10          # Airtable accepts at most 10 records per write request
PAUSE_SECONDS = 0.25     # stay under Airtable's 5 requests per second per base


def batches(items, size=BATCH_SIZE):
    """[1..25] -> [1..10], [11..20], [21..25]."""
    return [items[i:i + size] for i in range(0, len(items), size)]


class AirtableClient:
    def __init__(self, token, base_id, base_url=API_URL, timeout=20.0):
        self.token = token
        self.base_id = base_id
        self.base_url = base_url
        self.timeout = timeout
        self.calls = 0

    def _headers(self):
        return {"Authorization": f"Bearer {self.token}"}

    def _request(self, method, url, **kwargs):
        if self.calls:
            time.sleep(PAUSE_SECONDS)
        self.calls += 1
        response = httpx.request(method, url, headers=self._headers(),
                                 timeout=self.timeout, **kwargs)
        if response.is_error:
            # Airtable's error JSON names the problem (e.g. UNKNOWN_FIELD_NAME). No secrets in it.
            raise RuntimeError(f"Airtable {response.status_code}: {response.text[:300]}")
        return response.json()

    def table_fields(self):
        """{table name: {field name: field type}} for the base (1 call, read-only)."""
        data = self._request("GET", f"{self.base_url}/meta/bases/{self.base_id}/tables")
        return {t["name"]: {f["name"]: f["type"] for f in t["fields"]} for t in data["tables"]}

    def upsert(self, table, rows, key_field):
        """Create or update rows matched on key_field. Returns (created, updated) counts."""
        created = updated = 0
        for chunk in batches(rows):
            data = self._request("PATCH", f"{self.base_url}/{self.base_id}/{table}", json={
                "performUpsert": {"fieldsToMergeOn": [key_field]},
                "records": [{"fields": row} for row in chunk],
            })
            created += len(data.get("createdRecords", []))
            updated += len(data.get("updatedRecords", []))
        return created, updated


class FakeAirtableClient:
    """Keeps rows in memory, keyed like Airtable's upsert. Makes no network calls."""

    def __init__(self, schema=None):
        self.tables = {}
        self.calls = 0
        self.schema = schema or {}

    def table_fields(self):
        self.calls += 1
        return self.schema

    def upsert(self, table, rows, key_field):
        stored = self.tables.setdefault(table, {})
        created = updated = 0
        for chunk in batches(rows):
            self.calls += 1
            for row in chunk:
                key = row[key_field]
                if key in stored:
                    stored[key].update(row)
                    updated += 1
                else:
                    stored[key] = dict(row)
                    created += 1
        return created, updated
