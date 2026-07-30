"""
Perzistencija RequestRecord-a na disk - jedan JSON file po zahtjevu.

HITL stanje mora preziviti restart procesa: kad Policy agent kaze
"treba odobrenje", pipeline spremi RequestRecord ovdje i program zavrsi.
Odobrenje moze doci minutama, satima ili danima kasnije, u posve novom pokretanju
CLI-ja ('approve' naredba) - ucita se isti file s diska i nastavi tocno
odakle je stalo. Da je ovo memorija (obican dict u Pythonu), restart
procesa bi izbrisao cekajuci zahtjev - zato mora biti na disku.

Za produkciju: prava baza (Postgres i sl.) umjesto JSON fileova - vidi README.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from models import RequestRecord, RequestStatus

DATA_DIR = Path(__file__).parent / "data" / "requests"
DATA_DIR.mkdir(parents=True, exist_ok=True)


def _path(request_id: str) -> Path:
    return DATA_DIR / f"{request_id}.json"


def save(record: RequestRecord) -> None:
    record.updated_at = datetime.now(timezone.utc)
    _path(record.request_id).write_text(record.model_dump_json(indent=2), encoding="utf-8")


def load(request_id: str) -> RequestRecord:
    path = _path(request_id)
    if not path.exists():
        raise FileNotFoundError(f"Zahtjev '{request_id}' ne postoji na disku ({path})")
    return RequestRecord.model_validate_json(path.read_text(encoding="utf-8"))


def list_all() -> list[RequestRecord]:
    return [
        RequestRecord.model_validate_json(p.read_text(encoding="utf-8"))
        for p in sorted(DATA_DIR.glob("*.json"))
    ]


def list_by_status(*statuses: RequestStatus) -> list[RequestRecord]:
    return [r for r in list_all() if r.status in statuses]
