#!/usr/bin/env python3
"""
CLI - jedina "ulazna vrata" za covjeka u ovaj sustav.

Naredbe:
  python cli.py process emails/01_ivana_roaming.txt
  python cli.py list-pending
  python cli.py approve <request_id> --reviewer "ime@ht.hr"
  python cli.py reject  <request_id> --reviewer "ime@ht.hr" --reason "..."
  python cli.py show    <request_id>
"""

from __future__ import annotations

import argparse
import sys

from dotenv import load_dotenv

load_dotenv()  # ucitaj .env PRIJE ostalih importa - build_llm_client() ga cita

import pipeline
import storage
from models import RequestStatus


def cmd_process(args: argparse.Namespace) -> None:
    with open(args.file, encoding="utf-8") as f:
        raw_email = f.read()
    record = pipeline.process_email(raw_email)
    _print_summary(record)


def cmd_list_pending(args: argparse.Namespace) -> None:
    pending = storage.list_by_status(RequestStatus.NEEDS_APPROVAL, RequestStatus.NEEDS_CLARIFICATION)
    if not pending:
        print("Nema zahtjeva koji cekaju covjeka.")
        return

    for r in pending:
        customer_id = r.extracted.customer_id if r.extracted else "?"
        print(f"{r.request_id}  [{r.status.value}]  customer_id={customer_id}")
        if r.status == RequestStatus.NEEDS_APPROVAL:
            print(f"    razlog: {r.policy_decision.reason}")
        elif r.status == RequestStatus.NEEDS_CLARIFICATION:
            print(f"    pitanje za korisnika: {r.extracted.clarification_question}")


def cmd_approve(args: argparse.Namespace) -> None:
    record = pipeline.resume_after_approval(args.request_id, reviewer=args.reviewer)
    _print_summary(record)


def cmd_reject(args: argparse.Namespace) -> None:
    record = pipeline.reject(args.request_id, reviewer=args.reviewer, reason=args.reason)
    _print_summary(record)


def cmd_show(args: argparse.Namespace) -> None:
    record = storage.load(args.request_id)
    print(record.model_dump_json(indent=2))


def _print_summary(record) -> None:
    print(f"request_id: {record.request_id}")
    print(f"status:     {record.status.value}")

    if record.execution_result:
        if record.execution_result.error:
            print(f"greska:     {record.execution_result.error}")
        ce = record.execution_result.confirmation_email
        if ce:
            print(f"\n--- nacrt potvrdnog emaila ---\nTo: {ce.to}\nSubject: {ce.subject}\n\n{ce.body}")

    if record.status == RequestStatus.NEEDS_CLARIFICATION and record.extracted:
        print(f"pitanje za korisnika: {record.extracted.clarification_question}")
    if record.status == RequestStatus.NEEDS_APPROVAL and record.policy_decision:
        print(f"razlog za odobrenje:  {record.policy_decision.reason}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cli.py", description="Multiagentni sustav za obradu email zahtjeva")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("process", help="obradi novi email (.txt file) kroz pipeline")
    p.add_argument("file")
    p.set_defaults(func=cmd_process)

    p = sub.add_parser("list-pending", help="prikazi zahtjeve koji cekaju covjeka")
    p.set_defaults(func=cmd_list_pending)

    p = sub.add_parser("approve", help="odobri zahtjev u stanju NEEDS_APPROVAL")
    p.add_argument("request_id")
    p.add_argument("--reviewer", default="cli-user", help="tko odobrava (upisuje se u trag)")
    p.set_defaults(func=cmd_approve)

    p = sub.add_parser("reject", help="odbij zahtjev u stanju NEEDS_APPROVAL ili NEEDS_CLARIFICATION")
    p.add_argument("request_id")
    p.add_argument("--reviewer", default="cli-user")
    p.add_argument("--reason", default="")
    p.set_defaults(func=cmd_reject)

    p = sub.add_parser("show", help="prikazi cijeli zapis zahtjeva, ukljucujuci trace")
    p.add_argument("request_id")
    p.set_defaults(func=cmd_show)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    try:
        args.func(args)
    except (FileNotFoundError, ValueError) as exc:
        print(f"Greska: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
