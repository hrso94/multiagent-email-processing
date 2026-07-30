"""
Pydantic sheme koje razmjenjuju agenti.
Ovo je "ugovor" cijelog sustava - svaki agent prima i vraća jedan od ovih modela,
nikad slobodan tekst. To je razlog zašto ih pišemo prve, prije ijednog agenta.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field


def _now() -> datetime:
    return datetime.now(timezone.utc)


# --- Enumi -------------------------------------------------------------
# Zatvoren skup dozvoljenih vrijednosti umjesto golog stringa - LLM ne moze
# "izmisliti" npr. opciju koja ne postoji, Pydantic ce odbiti sve sto nije
# u listi.

class OptionType(str, Enum):
    EU_ROAMING = "eu_roaming"
    STATIC_IP = "static_ip"
    PREMIUM_SUPPORT = "premium_support"
    PACKAGE_BASIC = "package_basic"
    PACKAGE_STANDARD = "package_standard"
    PACKAGE_PREMIUM = "package_premium"


class ActionType(str, Enum):
    ACTIVATE = "activate"
    DEACTIVATE = "deactivate"
    CHANGE_PACKAGE = "change_package"


class Urgency(str, Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"


class RequestStatus(str, Enum):
    """Stanja kroz koja zahtjev prolazi - ovo je naš state machine."""
    RECEIVED = "received"
    NEEDS_CLARIFICATION = "needs_clarification"
    NEEDS_APPROVAL = "needs_approval"
    REJECTED = "rejected"
    APPROVED = "approved"
    EXECUTED = "executed"
    ERROR = "error"
    OUT_OF_SCOPE = "out_of_scope"


# --- Intake agent izlaz -------------------------------------------------

class ExtractedRequest(BaseModel):
    """Ono što Intake agent vadi iz sirovog emaila."""

    customer_id: Optional[str] = Field(
        default=None, description="ID korisnika/računa spomenut u emailu"
    )
    option: Optional[OptionType] = Field(
        default=None, description="Opcija na koju se zahtjev odnosi"
    )
    action: Optional[ActionType] = Field(
        default=None, description="Tražena akcija nad opcijom"
    )
    urgency: Urgency = Field(default=Urgency.NORMAL)
    confidence: float = Field(
        ge=0.0, le=1.0, description="Koliko je LLM siguran u ekstrakciju"
    )
    missing_fields: list[str] = Field(
        default_factory=list,
        description="Koja obavezna polja nedostaju - prazno ako je sve jasno",
    )
    clarification_question: Optional[str] = Field(
        default=None,
        description="Pitanje za korisnika ako missing_fields nije prazno",
    )
    is_out_of_scope: bool = Field(
        default=False,
        description="True ako email uopce nije zahtjev za izmjenu opcije",
    )
    reasoning: str = Field(
        description="Kratko objasnjenje zasto je LLM ovako protumacio email - za observability"
    )


# --- Policy agent izlaz --------------------------------------------------

class PolicyDecision(BaseModel):
    approved: bool
    requires_human_approval: bool
    reason: str = Field(description="Zasto je odluka takva - obavezno, radi audit traga")
    violated_rules: list[str] = Field(default_factory=list)


# --- Stub podaci o korisniku (izlaz get_customer alata) -------------------

class CustomerRecord(BaseModel):
    customer_id: str
    name: str
    email: str
    package: OptionType
    active_options: list[OptionType] = Field(default_factory=list)


# --- Execution agent izlaz ------------------------------------------------

class ConfirmationEmail(BaseModel):
    to: str
    subject: str
    body: str


class ExecutionResult(BaseModel):
    success: bool
    tool_calls: list[str] = Field(default_factory=list)
    error: Optional[str] = None
    confirmation_email: Optional[ConfirmationEmail] = None


# --- Observability -----------------------------------------------------
# Umjesto da se trace samo ispisuje u log file, spremamo ga i unutar samog
# RequestRecord-a. Tako je "zasto je sustav ovo odlucio" pitanje odgovoreno
# citanjem jednog perzistiranog JSON-a, a ne grepanjem po log datotekama.

class TraceEvent(BaseModel):
    span_id: str
    agent: str
    event: str
    data: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=_now)


# --- Cjelokupno stanje jednog zahtjeva (ono sto se perzistira za HITL) ----

class RequestRecord(BaseModel):
    request_id: str
    raw_email: str
    status: RequestStatus
    extracted: Optional[ExtractedRequest] = None
    policy_decision: Optional[PolicyDecision] = None
    execution_result: Optional[ExecutionResult] = None
    trace_id: str
    trace_events: list[TraceEvent] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)
    reviewed_by: Optional[str] = None
