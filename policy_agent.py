"""
Policy agent - provjerava ExtractedRequest protiv jednostavnog skupa pravila,
uz trenutno stanje korisnika (CustomerRecord).

Namjerno cista funkcija/klasa bez poziva alata: get_customer se poziva
JEDNOM u pipelineu (prije Policy provjere), a activate/deactivate_option
tek u Izvrsnom agentu ako Policy odobri. Tako se Policy agent moze
testirati potpuno izolirano - samo predas ExtractedRequest i CustomerRecord,
bez mockiranja tools.py.

Dva pravila, izravno iz primjera u zadatku:
  1. Konflikt: "opcija X se ne moze deaktivirati ako je aktivna opcija Y"
  2. Prag: "zahtjevi iznad praga Z zahtijevaju ljudsko odobrenje"
"""

from __future__ import annotations

from models import ActionType, CustomerRecord, ExtractedRequest, OptionType, PolicyDecision
from observability import Tracer

# Pravilo 2: mjesecna cijena opcije/paketa u eurima - Z je APPROVAL_THRESHOLD_EUR.
MONTHLY_PRICE_EUR: dict[OptionType, float] = {
    OptionType.EU_ROAMING: 5.0,
    OptionType.STATIC_IP: 8.0,
    OptionType.PREMIUM_SUPPORT: 25.0,
    OptionType.PACKAGE_BASIC: 0.0,
    OptionType.PACKAGE_STANDARD: 15.0,
    OptionType.PACKAGE_PREMIUM: 40.0,
}
APPROVAL_THRESHOLD_EUR = 15.0

# Pravilo 1: opcija -> koje druge aktivne opcije blokiraju njenu deaktivaciju.
DEACTIVATION_BLOCKED_BY: dict[OptionType, set[OptionType]] = {
    OptionType.STATIC_IP: {OptionType.PREMIUM_SUPPORT},
}


def _cost_delta_eur(extracted: ExtractedRequest, customer: CustomerRecord) -> float:
    """Koliko ce se mjesecni racun promijeniti ako se zahtjev izvrsi."""
    if extracted.action == ActionType.ACTIVATE:
        return MONTHLY_PRICE_EUR.get(extracted.option, 0.0)
    if extracted.action == ActionType.CHANGE_PACKAGE:
        return MONTHLY_PRICE_EUR.get(extracted.option, 0.0) - MONTHLY_PRICE_EUR.get(customer.package, 0.0)
    return 0.0  # DEACTIVATE nikad ne poskupljuje uslugu


class PolicyAgent:
    def run(self, extracted: ExtractedRequest, customer: CustomerRecord, tracer: Tracer) -> PolicyDecision:
        assert extracted.option is not None and extracted.action is not None, (
            "PolicyAgent ocekuje potpuno izvucen zahtjev - pipeline ne smije zvati "
            "Policy dok Intake ne vrati i option i action"
        )

        with tracer.span("policy_agent") as span:
            blockers = DEACTIVATION_BLOCKED_BY.get(extracted.option, set())
            conflicting = blockers & set(customer.active_options)

            if extracted.action == ActionType.DEACTIVATE and conflicting:
                reason = (
                    f"Opcija '{extracted.option.value}' se ne moze deaktivirati dok je "
                    f"aktivna opcija '{next(iter(conflicting)).value}' na racunu {customer.customer_id}."
                )
                decision = PolicyDecision(
                    approved=False,
                    requires_human_approval=False,
                    reason=reason,
                    violated_rules=[reason],
                )
                span.log("policy_decision", approved=False, requires_human_approval=False, reason=reason)
                return decision

            delta = _cost_delta_eur(extracted, customer)
            if delta > APPROVAL_THRESHOLD_EUR:
                reason = (
                    f"Zahtjev poskupljuje uslugu za {delta:.2f} EUR/mj, iznad praga od "
                    f"{APPROVAL_THRESHOLD_EUR:.2f} EUR/mj - potrebno ljudsko odobrenje."
                )
                decision = PolicyDecision(
                    approved=True, requires_human_approval=True, reason=reason, violated_rules=[]
                )
                span.log(
                    "policy_decision",
                    approved=True,
                    requires_human_approval=True,
                    reason=reason,
                    cost_delta_eur=delta,
                )
                return decision

            reason = "Nijedno pravilo nije prekrseno i zahtjev je ispod praga za odobrenje - automatski odobreno."
            decision = PolicyDecision(
                approved=True, requires_human_approval=False, reason=reason, violated_rules=[]
            )
            span.log("policy_decision", approved=True, requires_human_approval=False, reason=reason)
            return decision
