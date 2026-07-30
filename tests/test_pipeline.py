"""
End-to-end testovi cijelog pipelinea (process_email) - ne testiraju pojedini
agent izolirano, nego stvarni tok kroz sve njih. Ovi testovi bi uhvatili bug
gdje je email s vise zahtjeva istovremeno imao clarification_question I
prazan missing_fields, pa je pipeline (koji je provjeravao samo
missing_fields) proizvoljno izvrsio prvu pronadenu opciju.
"""

from models import RequestStatus
from pipeline import process_email


def test_happy_path_zavrsava_izvrsenjem():
    record = process_email(
        "Predmet: Deaktivacija roaminga\n"
        "Postovani, molim deaktivirajte opciju EU roaming na racunu 4482913. Vise nam ne treba."
    )

    assert record.status == RequestStatus.EXECUTED
    assert record.execution_result.success is True
    assert record.execution_result.confirmation_email is not None


def test_vise_zahtjeva_ne_smije_izvrsiti_prvu_opciju():
    """Regresijski test - vidi docstring filea. Prije popravka je ovo zavrsavalo
    kao EXECUTED sa stvarnim pozivom deactivate_option, iako je clarification_question
    bio postavljen."""
    record = process_email("Molim deaktivirajte EU roaming i staticki IP na racunu 4482913.")

    assert record.status == RequestStatus.NEEDS_CLARIFICATION
    assert record.extracted.clarification_question is not None
    assert record.execution_result is None


def test_skupa_opcija_trazi_ljudsko_odobrenje():
    record = process_email(
        "Racun 5521004. Molim aktivirajte premium support paket podrske sto prije."
    )

    assert record.status == RequestStatus.NEEDS_APPROVAL
    assert record.execution_result is None


def test_konflikt_pravilo_odbija_zahtjev():
    record = process_email(
        "Postovani, molim deaktivirajte opciju staticki IP na racunu 6633110."
    )

    assert record.status == RequestStatus.REJECTED
    assert record.execution_result is None


def test_nepostojeci_racun_zavrsava_greskom():
    record = process_email("Postovani, molim deaktivirajte EU roaming na racunu 9999999.")

    assert record.status == RequestStatus.ERROR
    assert record.execution_result.success is False
