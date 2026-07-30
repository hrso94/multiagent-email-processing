"""
Testovi za tools.py - oba nacina na koji stubirani alati mogu "pucati"
(CustomerNotFoundError, ToolExecutionError), koje executor_agent.py mora
uhvatiti (obavezni zahtjev "(b) poziv alata ne uspije").
"""

import pytest

from models import OptionType
from tools import CustomerNotFoundError, ToolExecutionError, activate_option, deactivate_option, get_customer


def test_get_customer_baca_gresku_za_nepostojeci_id():
    with pytest.raises(CustomerNotFoundError):
        get_customer("0000000")


def test_activate_option_baca_gresku_ako_je_vec_aktivna():
    customer = get_customer("4482913")
    assert OptionType.EU_ROAMING in customer.active_options

    with pytest.raises(ToolExecutionError):
        activate_option("4482913", OptionType.EU_ROAMING)


def test_deactivate_option_baca_gresku_ako_nije_aktivna():
    with pytest.raises(ToolExecutionError):
        deactivate_option("4482913", OptionType.PREMIUM_SUPPORT)


def test_deactivate_option_stvarno_mijenja_stanje():
    activate_option("4482913", OptionType.PREMIUM_SUPPORT)
    customer = deactivate_option("4482913", OptionType.PREMIUM_SUPPORT)
    assert OptionType.PREMIUM_SUPPORT not in customer.active_options
