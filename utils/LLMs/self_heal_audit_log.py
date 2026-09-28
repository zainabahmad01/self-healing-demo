import json
import os
from datetime import datetime, timezone
from typing import TypedDict


class SelfHealAuditAppendInput(TypedDict):
    brokenPrimary: str
    fixedLocator: str
    backupStrategy: str
    pageUrl: str


def append_self_heal_audit(record: SelfHealAuditAppendInput) -> None:
    """Appends one JSON line to `logs/self-heal-audit.jsonl` when a backup locator wins."""
    directory = os.path.join(os.getcwd(), "logs")
    file_path = os.path.join(directory, "self-heal-audit.jsonl")
    line = (
        json.dumps(
            {
                "ts": datetime.now(timezone.utc)
                .isoformat(timespec="milliseconds")
                .replace("+00:00", "Z"),
                "brokenPrimary": record["brokenPrimary"],
                "fixedLocator": record["fixedLocator"],
                "backupStrategy": record["backupStrategy"],
                "pageUrl": record["pageUrl"],
            }
        )
        + "\n"
    )

    try:
        os.makedirs(directory, exist_ok=True)
        with open(file_path, "a", encoding="utf8") as f:
            f.write(line)
        print(f"[Self-heal] Audit: appended -> {file_path}")
    except Exception as e:
        print(f"[Self-heal] Audit write failed: {e}")
