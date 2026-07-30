"""
Testovi za oba pravila iz policy_agent.py. PolicyAgent je namjerno cista
funkcija (ExtractedRequest + CustomerRecord -> PolicyDecision, bez poziva
alata), pa je testiranje izravno - ne treba mockirati nista iz tools.py.
"""

from models import ActionType, CustomerRecord, ExtractedRequest, OptionType
from observability import Tracer, new_id
from policy_agent import PolicyAgent


def _extracted(option: OptionType, action: ActionType, customer_id: str = "1") -> ExtractedRequest:
    return ExtractedRequest(customer_id=customer_id, option=option, action=action, confidence=0.9, reasoning="t")


def _customer(package=OptionType.PACKAGE_BASIC, active_options=None) -> CustomerRecord:
    return CustomerRecord(
        customer_id="1", name="Test", email="t@test.hr", package=package, active_options=active_options or []
    )


def _run(extracted, customer):
    return PolicyAgent().run(extracted, customer, Tracer(new_id("trace")))


def test_deaktivacija_bez_konflikta_i_ispod_praga_je_auto_odobrena():
    extracted = _extracted(OptionType.EU_ROAMING, ActionType.DEACTIVATE)
    customer = _customer(active_options=[OptionType.EU_ROAMING])

    decision = _run(extracted, customer)

    assert decision.approved is True
    assert decision.requires_human_approval is False


def test_aktivacija_iznad_praga_trazi_ljudsko_odobrenje():
    extracted = _extracted(OptionType.PREMIUM_SUPPORT, ActionType.ACTIVATE)
    customer = _customer()

    decision = _run(extracted, customer)

    assert decision.approved is True
    assert decision.requires_human_approval is True
    assert "iznad praga" in decision.reason


def test_deaktivacija_static_ip_uz_aktivan_premium_support_je_konflikt():
    extracted = _extracted(OptionType.STATIC_IP, ActionType.DEACTIVATE)
    customer = _customer(active_options=[OptionType.STATIC_IP, OptionType.PREMIUM_SUPPORT])

    decision = _run(extracted, customer)

    assert decision.approved is False
    assert decision.requires_human_approval is False
    assert len(decision.violated_rules) == 1


def test_deaktivacija_static_ip_bez_premium_supporta_prolazi():
    extracted = _extracted(OptionType.STATIC_IP, ActionType.DEACTIVATE)
    customer = _customer(active_options=[OptionType.STATIC_IP])

    decision = _run(extracted, customer)

    assert decision.approved is True


def test_promjena_paketa_gleda_razliku_cijena_ne_apsolutnu_cijenu():
    # basic -> standard je +15 EUR, tocno na pragu (ne iznad) - ne bi trebalo traziti odobrenje
    extracted = _extracted(OptionType.PACKAGE_STANDARD, ActionType.CHANGE_PACKAGE)
    customer = _customer(package=OptionType.PACKAGE_BASIC)

    decision = _run(extracted, customer)

    assert decision.requires_human_approval is False

    # basic -> premium je +40 EUR, jasno iznad praga
    extracted = _extracted(OptionType.PACKAGE_PREMIUM, ActionType.CHANGE_PACKAGE)
    decision = _run(extracted, customer)

    assert decision.requires_human_approval is True
