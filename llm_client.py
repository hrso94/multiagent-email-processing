"""
LLM sloj s dvije zamjenjive implementacije istog sucelja:

- MockLLMClient: rule-based/regex simulacija, besplatna i deterministicka,
  radi bez API kljuca (default, LLM_PROVIDER=mock).
- OpenAILLMClient: stvarni poziv na OpenAI API (LLM_PROVIDER=openai).

Kljucna dizajnerska odluka: LLMClient je apstraktno sucelje s jednom metodom,
complete(prompt) -> str (sirovi tekst, ocekivano JSON). IntakeAgent zove SAMO
to sucelje i ne zna koja se implementacija nalazi iza njega - zamjena mocka
pravim pozivom (ili npr. Anthropic API-jem) ne dira nista u intake_agent.py.
"""

from __future__ import annotations

import os
import re
from abc import ABC, abstractmethod
from typing import Optional

from models import ActionType, ExtractedRequest, OptionType, Urgency


class LLMClient(ABC):
    """Sucelje koje mora implementirati svaki 'provider' - mock ili pravi."""

    @abstractmethod
    def complete(self, prompt: str) -> str:
        """Vraca sirovi tekstualni odgovor modela."""
        raise NotImplementedError


# Sentinel koji nas MOCK prepoznaje kao "simuliraj da je LLM vratio pokvaren
# izlaz". Sluzi iskljucivo za demonstraciju obaveznog zahtjeva "(a) LLM vrati
# neispravan izlaz" - koristi se u emails/06_malformed_llm_demo.txt.
MALFORMED_OUTPUT_TRIGGER = "TRIGGER_MALFORMED_LLM"


_OPTION_KEYWORDS: list[tuple[OptionType, tuple[str, ...]]] = [
    (OptionType.EU_ROAMING, ("eu roaming", "roaming")),
    (OptionType.STATIC_IP, ("staticki ip", "statički ip", "static ip", "static_ip")),
    (OptionType.PREMIUM_SUPPORT, ("premium support", "premium podrsk", "premium podršk")),
    (OptionType.PACKAGE_PREMIUM, ("premium paket", "paket premium")),
    (OptionType.PACKAGE_STANDARD, ("standard paket", "paket standard")),
    (OptionType.PACKAGE_BASIC, ("basic paket", "paket basic", "osnovni paket")),
]

_ACTION_KEYWORDS: list[tuple[ActionType, tuple[str, ...]]] = [
    (ActionType.DEACTIVATE, ("deaktivir", "iskljuc", "isključ", "ugasi", "ukinite")),
    (ActionType.ACTIVATE, ("aktivir", "dodaj", "ukljuc", "uključ")),
    (ActionType.CHANGE_PACKAGE, ("promijeni", "promjen", "prebacite")),
]

_URGENT_MARKERS = ("hitno", "odmah", "sto prije", "što prije", "asap")

_INJECTION_MARKERS = (
    "ignoriraj sve prethodne upute",
    "ignoriraj prethodne upute",
    "svim racunima",
    "svim računima",
    "svim korisnicima",
)


def _extract_email_body(prompt: str) -> str:
    """intake_agent.py salje LLM-u CIJELI prompt (upute + JSON shema + email,
    email omeden s tri navodnika). Nas rule-based mock, za razliku od
    pravog LLM-a, ne zna sam razlikovati "ovo su upute" od "ovo je email" -
    ako bi pretrazivao cijeli prompt, zbunio bi se na primjere fraza koje
    SAM spominjemo u uputama (npr. 'svim racunima' kao opis onoga na sto
    LLM treba paziti). Zato prvo izvucemo samo dio unutar navodnika."""
    match = re.search(r'"""(.*)"""', prompt, re.DOTALL)
    return match.group(1) if match else prompt


def _find_customer_id(text: str) -> Optional[str]:
    match = re.search(r"\b\d{6,8}\b", text)
    return match.group(0) if match else None


def _find_options(lower_text: str) -> list[OptionType]:
    return [opt for opt, keywords in _OPTION_KEYWORDS if any(k in lower_text for k in keywords)]


def _find_action(lower_text: str) -> Optional[ActionType]:
    for action, keywords in _ACTION_KEYWORDS:
        if any(k in lower_text for k in keywords):
            return action
    return None


def _rule_based_extract(email_text: str) -> ExtractedRequest:
    """
    Simulira ono sto bi Intake prompt trazio od pravog LLM-a: procitaj email,
    vrati strukturiran zahtjev. Umjesto stvarnog modela, koristim
    kljucne rijeci/regex - dovoljno za 3 zadana primjera i pripadne
    varijante, uz jasnu granicu da je ovo zamjena za pravi poziv, ne
    tvrdnja da je ovo "kako se radi NLP".
    """

    lower = email_text.lower()
    customer_id = _find_customer_id(email_text)
    options = _find_options(lower)
    action = _find_action(lower)
    urgency = Urgency.HIGH if any(m in lower for m in _URGENT_MARKERS) else Urgency.NORMAL

    if any(marker in lower for marker in _INJECTION_MARKERS):
        return ExtractedRequest(
            customer_id=customer_id,
            urgency=urgency,
            confidence=0.95,
            is_out_of_scope=True,
            reasoning=(
                "Email sadrzi pokusaj zaobilazenja uputa (npr. 'ignoriraj prethodne upute') "
                "i/ili trazi masovnu akciju na svim racunima bez konkretnog jednog ID-a - "
                "prepoznato kao izvan opsega ovog pipelinea, ne izvrsavam nista."
            ),
        )

    if action is None and not options and customer_id is None:
        return ExtractedRequest(
            urgency=urgency,
            confidence=0.9,
            is_out_of_scope=True,
            reasoning="Email ne spominje ni racun, ni opciju, ni akciju nad opcijom - vjerojatno nije zahtjev za izmjenu usluge.",
        )

    missing_fields = []
    if customer_id is None:
        missing_fields.append("customer_id")
    if not options:
        missing_fields.append("option")
    if action is None:
        missing_fields.append("action")

    multiple_requests = len(options) > 1

    if missing_fields or multiple_requests:
        questions = []
        if "customer_id" in missing_fields:
            questions.append("Koji je broj racuna/korisnika na koji se zahtjev odnosi?")
        if multiple_requests:
            names = ", ".join(o.value for o in options)
            questions.append(f"Prepoznao sam vise zeljenih izmjena ({names}) u istoj poruci - koju obraditi, ili posaljite zaseban email za svaku?")
        if "option" in missing_fields:
            questions.append("Koju tocno opciju ili paket zelite izmijeniti?")

        reasoning = "Nedostaju obavezna polja (" + ", ".join(missing_fields) + ")" if missing_fields else ""
        if multiple_requests:
            reasoning = (reasoning + "; " if reasoning else "") + "email sadrzi vise od jednog zahtjeva u istoj poruci"
        reasoning += " - trazim pojasnjenje umjesto pogadanja."

        return ExtractedRequest(
            customer_id=customer_id,
            option=options[0] if options else None,
            action=action,
            urgency=urgency,
            confidence=0.55,
            missing_fields=missing_fields,
            clarification_question=" ".join(questions),
            reasoning=reasoning,
        )

    option = options[0]
    return ExtractedRequest(
        customer_id=customer_id,
        option=option,
        action=action,
        urgency=urgency,
        confidence=0.9,
        reasoning=f"Prepoznat jasan i potpun zahtjev: {action.value} opcije {option.value} na racunu {customer_id}.",
    )


class MockLLMClient(LLMClient):
    """Stand-in za pravi LLM poziv - vidi napomenu na vrhu filea."""

    def complete(self, prompt: str) -> str:
        if MALFORMED_OUTPUT_TRIGGER in prompt:
            # Namjerno vracamo pokvaren/skraceni JSON - simulira stvarni
            # scenarij gdje LLM vrati izlaz koji ne prolazi parsiranje
            # (prekinut stream, model "zaboravi" zatvoriti JSON, itd).
            # Intake agent ovo mora uhvatiti (ValidationError/JSONDecodeError),
            # ne smije pustiti da eksplodira cijeli pipeline.
            return '{"customer_id": "12345", "option": "eu_roaming", "acti'

        extracted = _rule_based_extract(_extract_email_body(prompt))
        return extracted.model_dump_json()


class OpenAILLMClient(LLMClient):
    """Pravi poziv na OpenAI API. Zahtijeva OPENAI_API_KEY u okruzenju.

    Import 'openai' paketa je namjerno OVDJE (u __init__), ne na vrhu
    filea - tako MockLLMClient (pa i testovi koji ga koriste) rade i bez
    instaliranog 'openai' paketa, i bez API kljuca. Realan poziv se desi
    samo ako netko stvarno zatrazi ovu klasu.
    """

    def __init__(self, model: str = "gpt-4o-mini"):
        from openai import OpenAI

        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError(
                "OPENAI_API_KEY nije postavljen u okruzenju. "
                "Kopiraj .env.example u .env i upisi svoj kljuc, ili koristi "
                "LLM_PROVIDER=mock (default) za mockirani sloj."
            )
        self._client = OpenAI(api_key=api_key)
        self._model = model

    def complete(self, prompt: str) -> str:
        if MALFORMED_OUTPUT_TRIGGER in prompt:
            # Isti deterministicki okidac kao u mocku (gore) - demo grešku
            # ne zelimo prepustiti slucaju/needeterminizmu pravog modela.
            return '{"customer_id": "12345", "option": "eu_roaming", "acti'

        response = self._client.chat.completions.create(
            model=self._model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0,
        )
        return response.choices[0].message.content


def build_llm_client() -> LLMClient:
    """Tvornicka funkcija - odlucuje koji LLMClient koristiti na temelju
    LLM_PROVIDER env varijable (default: mock, siguran/besplatan izbor).

    export LLM_PROVIDER=openai   -> pravi OpenAI poziv (treba OPENAI_API_KEY)
    (bez toga, ili LLM_PROVIDER=mock) -> MockLLMClient
    """
    provider = os.environ.get("LLM_PROVIDER", "mock").lower()
    if provider == "mock":
        return MockLLMClient()
    if provider == "openai":
        return OpenAILLMClient()
    raise ValueError(f"Nepoznat LLM_PROVIDER: {provider!r}. Dozvoljene vrijednosti su 'mock' i 'openai'.")
