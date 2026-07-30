"""
Orkestrator - jedino mjesto u sustavu koje zna redoslijed koraka:
Intake -> (get_customer) -> Policy -> [HITL gate] -> Executor.

Namjerno je ovo obican Python (funkcije + if/else), ne LangGraph/CrewAI graf.
Za 3 agenta i jedan HITL gate, custom orchestrator od ~70 linija je citljiviji
i lakse se brani na intervjuu nego uvodenje cijelog frameworka za ovoliko
malen pipeline - vidi README "kljucne dizajnerske odluke".
"""

from __future__ import annotations

from executor_agent import ExecutorAgent
from intake_agent import IntakeAgent, IntakeError
from llm_client import build_llm_client
from models import ExecutionResult, RequestRecord, RequestStatus, TraceEvent
from observability import Tracer, new_id
from policy_agent import PolicyAgent
from tools import CustomerNotFoundError, get_customer

import storage


def process_email(raw_email: str) -> RequestRecord:
    """Ulazna tocka - novi email stize u sustav. Vraca RequestRecord u bilo
    kojem statusu na kojem se pipeline za sada zaustavio (moze biti EXECUTED
    ako je sve autoodobreno, ili NEEDS_APPROVAL/NEEDS_CLARIFICATION ako
    treba covjeka, ili ERROR/OUT_OF_SCOPE/REJECTED)."""

    trace_id = new_id("trace")
    tracer = Tracer(trace_id)
    record = RequestRecord(
        request_id=new_id("req"),
        raw_email=raw_email,
        status=RequestStatus.RECEIVED,
        trace_id=trace_id,
    )

    intake = IntakeAgent(build_llm_client())
    try:
        extracted = intake.run(raw_email, tracer)
    except IntakeError:
        return _finish(record, tracer, RequestStatus.ERROR)

    record.extracted = extracted

    if extracted.is_out_of_scope:
        return _finish(record, tracer, RequestStatus.OUT_OF_SCOPE)

    if extracted.missing_fields:
        return _finish(record, tracer, RequestStatus.NEEDS_CLARIFICATION)

    # Intake garantira da su customer_id/option/action popunjeni kad
    # missing_fields prazan - vidi assert na pocetku PolicyAgent.run().
    try:
        customer = get_customer(extracted.customer_id)
    except CustomerNotFoundError as exc:
        record.execution_result = ExecutionResult(success=False, error=str(exc))
        return _finish(record, tracer, RequestStatus.ERROR)

    decision = PolicyAgent().run(extracted, customer, tracer)
    record.policy_decision = decision

    if not decision.approved:
        return _finish(record, tracer, RequestStatus.REJECTED)

    if decision.requires_human_approval:
        # HITL GATE: stajemo ovdje. RequestRecord se sprema na disk u
        # ovom statusu i cijeli proces moze zavrsiti - nitko ne "ceka" u
        # memoriji. Nastavak je zaseban poziv, moguce danima kasnije,
        # moguce sasvim drugi proces: vidi resume_after_approval().
        return _finish(record, tracer, RequestStatus.NEEDS_APPROVAL)

    record = _run_executor(record, tracer)
    return _finish(record, tracer, record.status)


def resume_after_approval(request_id: str, reviewer: str) -> RequestRecord:
    """Poziva CLI 'approve' naredba - moze biti posve nov proces/dan kasnije
    od onog koji je zapeo na NEEDS_APPROVAL. Sve sto treba je vec na disku."""

    record = storage.load(request_id)
    if record.status != RequestStatus.NEEDS_APPROVAL:
        raise ValueError(
            f"Zahtjev '{request_id}' nije u stanju NEEDS_APPROVAL (trenutno: {record.status.value})"
        )

    record.reviewed_by = reviewer
    tracer = Tracer(record.trace_id)  # nova Tracer instanca (nov proces), isti business trace_id
    record = _run_executor(record, tracer)

    # Nastavljamo trag, ne brisemo ono sto je vec zabiljezeno u proslom pokretanju.
    # record.status je vec postavljen unutar _run_executor (EXECUTED/ERROR).
    record.trace_events = record.trace_events + tracer.events
    storage.save(record)
    return record


def reject(request_id: str, reviewer: str, reason: str) -> RequestRecord:
    """Covjek odbija zahtjev koji ceka na NEEDS_APPROVAL ili NEEDS_CLARIFICATION."""

    record = storage.load(request_id)
    if record.status not in (RequestStatus.NEEDS_APPROVAL, RequestStatus.NEEDS_CLARIFICATION):
        raise ValueError(
            f"Zahtjev '{request_id}' nije u stanju koje covjek moze odbiti (trenutno: {record.status.value})"
        )

    record.status = RequestStatus.REJECTED
    record.reviewed_by = reviewer
    record.trace_events.append(
        TraceEvent(span_id=new_id("span"), agent="human", event="manual_rejection", data={"reason": reason})
    )
    storage.save(record)
    return record


def _run_executor(record: RequestRecord, tracer: Tracer) -> RequestRecord:
    result = ExecutorAgent().run(record.extracted, tracer)
    record.execution_result = result
    record.status = RequestStatus.EXECUTED if result.success else RequestStatus.ERROR
    return record


def _finish(record: RequestRecord, tracer: Tracer, status: RequestStatus) -> RequestRecord:
    record.trace_events = tracer.events
    record.status = status
    storage.save(record)
    return record
