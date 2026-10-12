"""Public retrieval API contracts. Hashes are deliberately absent."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


class RetrievalModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


SessionStatus = Literal["issued", "validated", "completed", "expired", "cancelled"]


class CreateRetrievalRequest(RetrievalModel):
    match_candidate_id: UUID


class IssuedRetrievalResponse(RetrievalModel):
    id: UUID
    raw_token: str
    qr_payload: str
    issued_at: AwareDatetime
    expires_at: AwareDatetime
    status: SessionStatus
    item_summary: str


class RetrievalStatusResponse(RetrievalModel):
    id: UUID
    status: SessionStatus
    issued_at: AwareDatetime
    expires_at: AwareDatetime
    item_summary: str
    validated_at: AwareDatetime | None = None
    completed_at: AwareDatetime | None = None
    slot_code: str | None = None
    section: Literal["pocket", "medium"] | None = None
    wrong_item_out: bool = False
    retriever: str | None = None
    can_replace: bool
    completed: bool


class ValidateQrRequest(RetrievalModel):
    qr_payload: str = Field(min_length=1, max_length=200)


class ValidatedRetrievalResponse(RetrievalModel):
    id: UUID
    status: Literal["validated"]
    item_summary: str
    slot_code: str
    section: Literal["pocket", "medium"]
    slot_status: Literal["occupied"]
    action_token: str


class SimulatedRetrievalResponse(RetrievalModel):
    id: UUID
    status: Literal["validated", "completed"]
    wrong_item_out: bool = False
    completed_at: datetime | None = None


class RetrievalLogResponse(RetrievalModel):
    id: UUID
    retrieval_session_id: UUID
    retriever: str
    item_summary: str
    slot_code: str
    retrieved_at: AwareDatetime
    completion_source: str
