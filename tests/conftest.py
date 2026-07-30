"""
Zajednicki fixture za sve testove: tools._CUSTOMERS je obican Python
rjecnik u memoriji (nasa stub "baza"), pa bi testovi mogli utjecati jedni
na druge ako jedan test aktivira/deaktivira opciju, a drugi poslije
ocekuje pocetno stanje. Ovaj fixture (autouse=True znaci "primijeni na
SVAKI test bez da ga test mora eksplicitno traziti") napravi duboku kopiju
prije svakog testa i vrati je nakon - svaki test pocinje s cistim stanjem.
"""

import copy

import pytest

import tools


@pytest.fixture(autouse=True)
def _reset_customers():
    original = copy.deepcopy(tools._CUSTOMERS)
    yield
    tools._CUSTOMERS.clear()
    tools._CUSTOMERS.update(original)
