"""
Testovi za models.py - Pydantic mora odbiti ono sto ne bi smjelo proci
(za razliku od golog dict-a ili dataclassa, koji to ne bi provjerili).
"""

import pytest
from pydantic import ValidationError

from models import ExtractedRequest, OptionType


def test_odbija_nepostojecu_opciju():
    with pytest.raises(ValidationError):
        ExtractedRequest(option="wifi_booster_nesto_izmisljeno", confidence=0.9, reasoning="t")


def test_odbija_confidence_izvan_raspona():
    with pytest.raises(ValidationError):
        ExtractedRequest(confidence=1.5, reasoning="t")


def test_option_se_serijalizira_kao_obican_string():
    req = ExtractedRequest(option=OptionType.EU_ROAMING, confidence=0.9, reasoning="t")
    assert '"eu_roaming"' in req.model_dump_json()


def test_reasoning_je_obavezno_polje():
    with pytest.raises(ValidationError):
        ExtractedRequest(confidence=0.9)  # nema reasoning
