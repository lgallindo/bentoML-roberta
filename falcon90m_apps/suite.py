"""Extensive offline test suite for Falcon 90M sample apps."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass

from engine import FalconAppsEngine


@dataclass
class Case:
    app: str
    name: str
    kwargs: dict
    expect_ok: bool
    expect_field: str | None = None
    expect_value: object | None = None
    expect_contains: dict[str, str] | None = None


CASES: list[Case] = [
    # --- extract_json ---
    Case(
        "extract_json",
        "person_city",
        {"text": "Alice lives in Recife.", "keys": ["name", "city"]},
        True,
        expect_contains={"name": "Alice", "city": "Recife"},
    ),
    Case(
        "extract_json",
        "product_price",
        {
            "text": "The Bluetooth earbuds cost $49.99.",
            "keys": ["product", "price"],
        },
        True,
        expect_contains={"product": "Bluetooth", "price": "49.99"},
    ),
    Case(
        "extract_json",
        "email_phone",
        {
            "text": "Contact bob@example.com or call 415-555-0100.",
            "keys": ["email", "phone"],
        },
        True,
        expect_contains={"email": "bob@example.com"},
    ),
    Case(
        "extract_json",
        "order_fields",
        {
            "text": "Order A-17 for Maya ships Friday.",
            "keys": ["order_id", "customer", "ship_day"],
        },
        True,
        expect_contains={"order_id": "A-17", "customer": "Maya"},
    ),
    Case(
        "extract_json",
        "labeled_person",
        {
            "text": "Name: Carla. City: Olinda.",
            "keys": ["name", "city"],
        },
        True,
        expect_contains={"name": "Carla", "city": "Olinda"},
    ),
    # --- route_intent ---
    Case(
        "route_intent",
        "billing_double_charge",
        {"text": "I was charged twice on my invoice."},
        True,
        "label",
        "BILLING",
    ),
    Case(
        "route_intent",
        "cancel_sub",
        {"text": "Please cancel my subscription today."},
        True,
        "label",
        "CANCEL",
    ),
    Case(
        "route_intent",
        "tech_wifi",
        {"text": "My Wi-Fi keeps dropping every hour."},
        True,
        "label",
        "TECH",
    ),
    Case(
        "route_intent",
        "other_weather",
        {"text": "What is the weather in Recife tomorrow?"},
        True,
        "label",
        "OTHER",
    ),
    Case(
        "route_intent",
        "billing_refund",
        {"text": "I need a refund for last month's bill."},
        True,
        "label",
        "BILLING",
    ),
    Case(
        "route_intent",
        "tech_login",
        {"text": "The app crashes after login on Android."},
        True,
        "label",
        "TECH",
    ),
    Case(
        "route_intent",
        "cancel_unsubscribe",
        {"text": "I want to unsubscribe from the premium plan."},
        True,
        "label",
        "CANCEL",
    ),
    # --- fill_template ---
    Case(
        "fill_template",
        "hello_order",
        {
            "template": "Hello {name}, your order {id} ships on {date}.",
            "data": {"name": "Maya", "id": "A-17", "date": "Friday"},
        },
        True,
        expect_contains={"name": "Maya", "id": "A-17", "date": "Friday"},
    ),
    Case(
        "fill_template",
        "ticket",
        {
            "template": "Ticket {ticket} assigned to {agent}.",
            "data": {"ticket": "T-9", "agent": "Noah"},
        },
        True,
        expect_contains={"ticket": "T-9", "agent": "Noah"},
    ),
    Case(
        "fill_template",
        "meeting",
        {
            "template": "Meet {who} at {place} on {when}.",
            "data": {"who": "Ada", "place": "Lobby", "when": "Monday"},
        },
        True,
        expect_contains={"who": "Ada", "place": "Lobby", "when": "Monday"},
    ),
    Case(
        "fill_template",
        "ship_notice",
        {
            "template": "Package {pkg} for {buyer} arrives {day}.",
            "data": {"pkg": "P-42", "buyer": "Rui", "day": "Tuesday"},
        },
        True,
        expect_contains={"pkg": "P-42", "buyer": "Rui", "day": "Tuesday"},
    ),
    # --- tag_email ---
    Case(
        "tag_email",
        "invoice_subject",
        {"subject": "Q3 invoice attached — payment due Friday"},
        True,
        "tag",
        "invoice",
    ),
    Case(
        "tag_email",
        "meeting_subject",
        {"subject": "Sync tomorrow 10am — project kickoff"},
        True,
        "tag",
        "meeting",
    ),
    Case(
        "tag_email",
        "spam_subject",
        {"subject": "You've won a FREE iPhone!!! click now"},
        True,
        "tag",
        "spam",
    ),
    Case(
        "tag_email",
        "support_subject",
        {"subject": "Cannot login to my account — password reset failed"},
        True,
        "tag",
        "support",
    ),
    Case(
        "tag_email",
        "invoice_receipt",
        {"subject": "Your receipt and billing summary"},
        True,
        "tag",
        "invoice",
    ),
    Case(
        "tag_email",
        "meeting_invite",
        {"subject": "Calendar invite: design review"},
        True,
        "tag",
        "meeting",
    ),
]


def _run_case(engine: FalconAppsEngine, case: Case) -> tuple[bool, dict, str]:
    fn = getattr(engine, case.app)
    result = fn(**case.kwargs)
    ok = bool(result.get("ok"))
    reason = ""

    if case.expect_ok and not ok:
        reason = f"expected ok, raw={result.get('raw')!r}"
    elif not case.expect_ok and ok:
        reason = "expected failure but ok=True"

    if case.expect_field and case.expect_value is not None:
        got = result.get(case.expect_field)
        if got != case.expect_value:
            # Soft match for extract-style contains checks handled below
            if case.expect_contains is None:
                ok = False
                reason = (
                    f"{case.expect_field}={got!r}, expected {case.expect_value!r}; "
                    f"raw={result.get('raw')!r}"
                )

    if case.expect_contains:
        if case.app == "extract_json":
            data = result.get("data") or {}
            for k, needle in case.expect_contains.items():
                val = str(data.get(k, ""))
                if needle.lower() not in val.lower():
                    ok = False
                    reason = (
                        f"data[{k}]={val!r} missing {needle!r}; raw={result.get('raw')!r}"
                    )
                    break
        elif case.app == "fill_template":
            text = str(result.get("text") or "")
            for needle in case.expect_contains.values():
                if needle not in text:
                    ok = False
                    reason = f"text={text!r} missing {needle!r}; raw={result.get('raw')!r}"
                    break

    return ok, result, reason


def run_suite(verbose: bool = False) -> int:
    engine = FalconAppsEngine(threads=2)
    passed = 0
    failed = 0
    rows: list[dict] = []

    for case in CASES:
        ok, result, reason = _run_case(engine, case)
        status = "PASS" if ok else "FAIL"
        if ok:
            passed += 1
        else:
            failed += 1
        summary = {
            "status": status,
            "app": case.app,
            "name": case.name,
            "reason": reason,
            "result": {
                k: result.get(k)
                for k in ("ok", "label", "tag", "data", "text", "raw")
                if k in result
            },
        }
        rows.append(summary)
        line = f"{status:4s}  {case.app:14s}  {case.name}"
        if verbose or not ok:
            extra = reason or json.dumps(summary["result"], ensure_ascii=False)
            print(f"{line}  ::  {extra}")
        else:
            print(line)

    print(f"\n{passed} passed, {failed} failed, {passed + failed} total")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    verbose = "--verbose" in sys.argv or "-v" in sys.argv
    raise SystemExit(run_suite(verbose=verbose))
