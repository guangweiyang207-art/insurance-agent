from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

from app.config import get_settings
from app.database import db, row_to_json
from app.responses import ApiList, api_error

router = APIRouter()


@router.get("")
def list_clauses() -> ApiList:
    rows = db.fetch_all(
        "SELECT id, file_name, file_path, clause_type, created_at, updated_at FROM clauses ORDER BY id"
    )
    return ApiList(items=[row_to_json(row) for row in rows])


@router.get("/{clause_id}")
def get_clause(clause_id: int) -> dict:
    row = db.fetch_one(
        "SELECT id, file_name, file_path, clause_type, created_at, updated_at FROM clauses WHERE id = %s",
        (clause_id,),
    )
    if row is None:
        raise api_error(404, "CLAUSE_NOT_FOUND", "Clause not found")
    return row_to_json(row)


@router.get("/{clause_id}/file")
def get_clause_file(clause_id: int) -> FileResponse:
    clause = get_clause(clause_id)
    path = Path(clause["file_path"])
    if not path.is_absolute():
        path = get_settings().app_workspace_root / path.as_posix().lstrip("/")
    if not path.exists():
        raise api_error(404, "CLAUSE_FILE_NOT_FOUND", "Clause file not found")
    return FileResponse(path, media_type="application/pdf", filename=clause["file_name"])

