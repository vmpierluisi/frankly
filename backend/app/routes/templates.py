"""Template setup — artifact parsing + criteria extraction.

Manager-gated. Two endpoints:
  * POST /templates/parse-artifact — upload a PDF/DOCX/txt, get plain text.
  * POST /templates/extract-criteria — take four artifact texts, return
    5-7 suggested criteria (for review before saving on the company).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from .. import schemas
from ..auth import require_manager
from ..services import artifact_parser
from ..services.criteria_extractor import extract_criteria

router = APIRouter(
    prefix="/templates",
    tags=["templates"],
    dependencies=[Depends(require_manager)],
)


@router.post("/parse-artifact")
async def parse_artifact(file: UploadFile = File(...)) -> dict[str, str]:
    """Return the extracted text for a single artifact upload."""
    data = await file.read()
    try:
        text = artifact_parser.parse_upload(filename=file.filename or "upload", data=data)
    except artifact_parser.UnsupportedArtifactType as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"filename": file.filename or "", "text": text}


@router.post("/extract-criteria", response_model=schemas.ExtractCriteriaOut)
async def extract_criteria_route(
    payload: schemas.ExtractCriteriaIn,
    role: str = "",
) -> schemas.ExtractCriteriaOut:
    """Return 5-7 LLM-suggested criteria for the given artifacts.

    Role is passed as a query parameter because it's short context for the LLM
    but doesn't belong on the Company row until save.
    """
    criteria = await extract_criteria(
        role=role or "(unspecified role)",
        artifact_values=payload.artifact_values,
        artifact_role_spec=payload.artifact_role_spec,
        artifact_team_structure=payload.artifact_team_structure,
        artifact_sample_comms=payload.artifact_sample_comms,
    )
    return schemas.ExtractCriteriaOut(
        criteria=[schemas.ExtractedCriterion(**c) for c in criteria],
    )
