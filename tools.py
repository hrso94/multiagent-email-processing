"""
Stubirani "alati" koje zove Izvrsni agent: get_customer, activate_option,
deactivate_option, change_package.

Ovo simulira poziv pravom OSS/BSS sustavu (billing/provisioning API).
U pravom sustavu bi ovo bile HTTP pozivi prema internom servisu; ovdje
je in-memory rjecnik da cijeli zadatak radi bez ikakve infrastrukture.
"""

from __future__ import annotations

from models import CustomerRecord, OptionType


class CustomerNotFoundError(Exception):
    """Baca se kad customer_id ne postoji - simulira 404 od pravog API-ja."""


class ToolExecutionError(Exception):
    """Baca se kad je poziv sam po sebi neizvediv (npr. opcija vec u trazenom stanju)."""


# Pocetno stanje "baze" korisnika. Mutira se tijekom rada (activate/deactivate
# stvarno mijenjaju ovaj rjecnik) da demo emailovi mogu graditi jedni na drugima.
_CUSTOMERS: dict[str, CustomerRecord] = {
    "4482913": CustomerRecord(
        customer_id="4482913",
        name="Ivana K.",
        email="ivana.k@acme.hr",
        package=OptionType.PACKAGE_STANDARD,
        active_options=[OptionType.EU_ROAMING],
    ),
    "5521004": CustomerRecord(
        customer_id="5521004",
        name="Marko P.",
        email="marko.p@example.com",
        package=OptionType.PACKAGE_BASIC,
        active_options=[OptionType.STATIC_IP],
    ),
    # Vec ima i static IP i premium support - koristi se za demo Pravila 1
    # (konflikt) u jednom prolazu, bez oslanjanja na stanje izmedu procesa
    # (nas in-memory "customer store" se resetira svaki put kad proces krene
    # iznova - vidi napomenu na vrhu filea i README).
    "6633110": CustomerRecord(
        customer_id="6633110",
        name="Petra N.",
        email="petra.n@example.com",
        package=OptionType.PACKAGE_STANDARD,
        active_options=[OptionType.STATIC_IP, OptionType.PREMIUM_SUPPORT],
    ),
}


def get_customer(customer_id: str) -> CustomerRecord:
    customer = _CUSTOMERS.get(customer_id)
    if customer is None:
        raise CustomerNotFoundError(f"Korisnik s ID-em '{customer_id}' ne postoji")
    return customer


def activate_option(customer_id: str, option: OptionType) -> CustomerRecord:
    customer = get_customer(customer_id)
    if option in customer.active_options:
        raise ToolExecutionError(f"Opcija '{option.value}' je vec aktivna za korisnika {customer_id}")
    customer.active_options.append(option)
    return customer


def deactivate_option(customer_id: str, option: OptionType) -> CustomerRecord:
    customer = get_customer(customer_id)
    if option not in customer.active_options:
        raise ToolExecutionError(f"Opcija '{option.value}' nije aktivna za korisnika {customer_id}")
    customer.active_options.remove(option)
    return customer


def change_package(customer_id: str, package: OptionType) -> CustomerRecord:
    customer = get_customer(customer_id)
    if customer.package == package:
        raise ToolExecutionError(f"Korisnik {customer_id} je vec na paketu '{package.value}'")
    customer.package = package
    return customer
