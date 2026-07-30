"""
Izvrsni agent - poziva prave (mutating) alate iz tools.py i sastavlja
nacrt potvrdnog emaila.

Ovdje se demonstrira obavezni zahtjev "(b) poziv alata ne uspije": obje
moguce greske iz tools.py (CustomerNotFoundError, ToolExecutionError) se
hvataju i pretvaraju u ExecutionResult(success=False, error=...) - pipeline
se ne rusi, samo zahtjev zavrsi u RequestStatus.ERROR s jasnim razlogom.
"""

from __future__ import annotations

from models import ActionType, ConfirmationEmail, ExecutionResult, ExtractedRequest
from observability import Tracer
from tools import (
    CustomerNotFoundError,
    ToolExecutionError,
    activate_option,
    change_package,
    deactivate_option,
)

_ACTION_LABELS = {
    ActionType.ACTIVATE: "aktivirali",
    ActionType.DEACTIVATE: "deaktivirali",
    ActionType.CHANGE_PACKAGE: "promijenili paket na",
}


class ExecutorAgent:
    def run(self, extracted: ExtractedRequest, tracer: Tracer) -> ExecutionResult:
        assert extracted.customer_id is not None and extracted.option is not None and extracted.action is not None, (
            "ExecutorAgent ocekuje potpuno izvucen i vec odobren zahtjev"
        )

        with tracer.span("executor_agent") as span:
            tool_calls: list[str] = []

            try:
                if extracted.action == ActionType.ACTIVATE:
                    tool_calls.append(f"activate_option({extracted.customer_id!r}, {extracted.option.value!r})")
                    customer = activate_option(extracted.customer_id, extracted.option)
                elif extracted.action == ActionType.DEACTIVATE:
                    tool_calls.append(f"deactivate_option({extracted.customer_id!r}, {extracted.option.value!r})")
                    customer = deactivate_option(extracted.customer_id, extracted.option)
                else:
                    tool_calls.append(f"change_package({extracted.customer_id!r}, {extracted.option.value!r})")
                    customer = change_package(extracted.customer_id, extracted.option)
            except (CustomerNotFoundError, ToolExecutionError) as exc:
                span.log("tool_call_failed", error=str(exc), error_type=type(exc).__name__)
                return ExecutionResult(success=False, tool_calls=tool_calls, error=str(exc))

            confirmation = ConfirmationEmail(
                to=customer.email,
                subject="Potvrda izmjene usluge",
                body=(
                    f"Postovani/a {customer.name},\n\n"
                    f"Obavjestavamo Vas da smo {_ACTION_LABELS[extracted.action]} opciju "
                    f"'{extracted.option.value}' na Vasem racunu ({customer.customer_id}).\n\n"
                    f"Lijep pozdrav,\nTim podrske"
                ),
            )
            span.log("execution_result", success=True, tool_calls=tool_calls)
            return ExecutionResult(success=True, tool_calls=tool_calls, confirmation_email=confirmation)
