"""
Test koji stvarno zove OpenAI API preko OpenAILLMClient (ne MockLLMClient).

Automatski se preskace ako OPENAI_API_KEY nije postavljen (npr. CI bez
kljuca, ili netko tko pregledava repo bez zelje da trosi API kredit).
Da se pokrene: kopiraj .env.example u .env, upisi OPENAI_API_KEY, i pokreni
normalno 'python -m pytest' - ovaj test ce se sam ukljuciti (ostali testovi
i dalje rade na MockLLMClient, vidi test_intake_agent.py).
"""

import os

import pytest
from dotenv import load_dotenv

load_dotenv()

pytestmark = pytest.mark.skipif(
    not os.environ.get("OPENAI_API_KEY"),
    reason="Treba OPENAI_API_KEY da se stvarno pozove OpenAI API (vidi .env.example)",
)


def test_intake_agent_sa_pravim_openai_pozivom():
    from intake_agent import IntakeAgent
    from llm_client import OpenAILLMClient
    from observability import Tracer, new_id

    agent = IntakeAgent(OpenAILLMClient())
    email = (
        "Predmet: Deaktivacija roaminga\n"
        "Postovani, molim deaktivirajte opciju EU roaming na racunu 4482913. "
        "Vise nam ne treba.\nLijep pozdrav, Ivana K."
    )

    result = agent.run(email, Tracer(new_id("trace")))

    assert result.customer_id == "4482913"
    assert result.action.value == "deactivate"
    assert result.is_out_of_scope is False
