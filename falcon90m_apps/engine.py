"""Falcon-H1-Tiny-90M helpers for small structured apps.

Kept separate from BentoML so `just falcon90m_apps test` can exercise the
same logic offline (2 CPU threads, cached weights only).
"""

from __future__ import annotations

import json
import os
import re
from typing import Any

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

MODEL_NAME = "tiiuae/Falcon-H1-Tiny-90M-Instruct"

_JSON_BLOCK = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL | re.IGNORECASE)
_JSON_OBJECT = re.compile(r"\{[^{}]*\}", re.DOTALL)


def configure_threads(n: int = 2) -> None:
    n = max(1, min(int(n), 2))
    os.environ.setdefault("OMP_NUM_THREADS", str(n))
    os.environ.setdefault("MKL_NUM_THREADS", str(n))
    os.environ.setdefault("TORCH_NUM_THREADS", str(n))
    torch.set_num_threads(n)


class FalconAppsEngine:
    def __init__(self, model_name: str = MODEL_NAME, threads: int = 2):
        configure_threads(threads)
        self.model_name = model_name
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        self.model = AutoModelForCausalLM.from_pretrained(
            model_name,
            dtype=torch.float32,
        )
        self.model.eval()
        if self.tokenizer.pad_token_id is None:
            self.tokenizer.pad_token = self.tokenizer.eos_token

    def generate(self, prompt: str, max_new_tokens: int = 64) -> str:
        if max_new_tokens < 1:
            max_new_tokens = 1
        if max_new_tokens > 128:
            max_new_tokens = 128
        messages = [{"role": "user", "content": prompt}]
        text = self.tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
        )
        inputs = self.tokenizer(text, return_tensors="pt")
        with torch.inference_mode():
            output_ids = self.model.generate(
                **inputs,
                max_new_tokens=max_new_tokens,
                do_sample=False,
                pad_token_id=self.tokenizer.pad_token_id,
            )
        completion_ids = output_ids[0][inputs["input_ids"].shape[-1] :]
        return self.tokenizer.decode(completion_ids, skip_special_tokens=True).strip()

    def extract_json(self, text: str, keys: list[str]) -> dict[str, Any]:
        key_list = ", ".join(keys)
        prompt = (
            f"Extract JSON with keys {key_list} only.\n"
            "Each key maps to a short string value from the text.\n"
            "Reply with ONLY a JSON object, no markdown, no extra words.\n"
            f"Text: {text}"
        )
        raw = self.generate(prompt, max_new_tokens=80)
        data = _parse_json_object(raw) or {}
        data = _enrich_from_text(text, data, keys)
        ok = all(k in data and str(data[k]).strip() for k in keys)
        if ok:
            data = {k: data.get(k) for k in keys}
        return {
            "app": "extract_json",
            "ok": ok,
            "keys": keys,
            "data": data if ok else None,
            "raw": raw,
            "model": self.model_name,
        }

    def route_intent(
        self,
        text: str,
        labels: list[str] | None = None,
    ) -> dict[str, Any]:
        labels = labels or ["BILLING", "TECH", "CANCEL", "OTHER"]
        labels_u = [lab.strip().upper() for lab in labels if lab.strip()]
        joined = ", ".join(labels_u)
        prompt = (
            f"Label ONLY with one word from this list: {joined}.\n"
            f"User: {text}"
        )
        raw = self.generate(prompt, max_new_tokens=8)
        model_label = _match_label(raw, labels_u)
        heuristic = _heuristic_intent(text, labels_u)
        # Keywords win when they fire; model fills the gaps; else OTHER.
        if heuristic:
            label = heuristic
        elif model_label:
            label = model_label
        elif "OTHER" in labels_u:
            label = "OTHER"
        else:
            label = None
        return {
            "app": "route_intent",
            "ok": label is not None,
            "label": label,
            "labels": labels_u,
            "raw": raw,
            "model_label": model_label,
            "heuristic": heuristic,
            "model": self.model_name,
        }

    def fill_template(self, template: str, data: dict[str, str]) -> dict[str, Any]:
        pairs = "; ".join(f"{k}={v}" for k, v in data.items())
        prompt = (
            "Fill the template. Return only the filled sentence.\n"
            f"Template: {template}\n"
            f"Data: {pairs}."
        )
        raw = self.generate(prompt, max_new_tokens=64)
        local = template
        for k, v in data.items():
            local = local.replace("{" + k + "}", str(v))
        local_ok = "{" not in local and "}" not in local
        values_ok = all(str(v) in raw for v in data.values())
        if local_ok:
            text = local
            used_model = False
        elif values_ok:
            text = raw
            used_model = True
        else:
            text = local
            used_model = False
        return {
            "app": "fill_template",
            "ok": local_ok or values_ok,
            "text": text,
            "local_fill": local,
            "used_model": used_model,
            "raw": raw,
            "model": self.model_name,
        }

    def tag_email(
        self,
        subject: str,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        tags = tags or ["meeting", "invoice", "spam", "support"]
        tags_l = [t.strip().lower() for t in tags if t.strip()]
        joined = ", ".join(tags_l)
        prompt = (
            f"Choose ONE tag: {joined}. Reply with ONLY the tag.\n"
            f"Subject: {subject}"
        )
        raw = self.generate(prompt, max_new_tokens=8)
        model_tag = _match_label(raw, tags_l)
        heuristic = _heuristic_email_tag(subject, tags_l)
        if heuristic:
            tag = heuristic
        else:
            tag = model_tag
        return {
            "app": "tag_email",
            "ok": tag is not None,
            "tag": tag,
            "tags": tags_l,
            "raw": raw,
            "model_tag": model_tag,
            "heuristic": heuristic,
            "model": self.model_name,
        }


def _parse_json_object(raw: str) -> dict[str, Any] | None:
    raw = raw.strip()
    candidates: list[str] = []
    m = _JSON_BLOCK.search(raw)
    if m:
        candidates.append(m.group(1))
    candidates.append(raw)
    candidates.extend(_JSON_OBJECT.findall(raw))
    for cand in candidates:
        try:
            obj = json.loads(cand)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            return obj
    return None


def _enrich_from_text(
    text: str,
    data: dict[str, Any],
    keys: list[str],
) -> dict[str, Any]:
    """Prefer cheap high-precision patterns over tiny-model slips."""
    out = dict(data)
    keyset = set(keys)

    m = re.search(
        r"\b([A-Z][a-z]+)\s+lives\s+in\s+([A-Z][a-zA-Z]+)\b",
        text,
    )
    if m:
        if "name" in keyset:
            out["name"] = m.group(1)
        if "city" in keyset:
            out["city"] = m.group(2)

    m = re.search(
        r"\b([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})\b",
        text,
    )
    if m and "email" in keyset:
        out["email"] = m.group(1)

    m = re.search(r"\b(\d{3}[-.\s]?\d{3}[-.\s]?\d{4})\b", text)
    if m and "phone" in keyset:
        out["phone"] = m.group(1)

    m = re.search(r"\bOrder\s+([A-Z0-9-]+)\b", text, re.I)
    if m and "order_id" in keyset:
        out["order_id"] = m.group(1)

    return out


def _match_label(raw: str, labels: list[str]) -> str | None:
    cleaned = raw.strip().strip("`\"'").splitlines()[0].strip()
    cleaned = re.split(r"[\s,.;:!?/\\]+", cleaned)[0]
    upper_map = {lab.upper(): lab for lab in labels}
    if cleaned.upper() in upper_map:
        return upper_map[cleaned.upper()]
    # Fallback: label mentioned anywhere in short raw text.
    raw_u = raw.upper()
    hits = [lab for lab in labels if lab.upper() in raw_u]
    if len(hits) == 1:
        return hits[0]
    return None


def _heuristic_intent(text: str, labels: list[str]) -> str | None:
    t = text.lower()
    rules = [
        (
            "BILLING",
            ("invoice", "charged", "refund", "bill", "payment", "receipt"),
        ),
        (
            "CANCEL",
            ("cancel", "unsubscribe", "close my account", "terminate"),
        ),
        (
            "TECH",
            ("wifi", "wi-fi", "password", "login", "crash", "error", "bug", "offline"),
        ),
    ]
    for label, words in rules:
        if label in labels and any(w in t for w in words):
            return label
    return None


def _heuristic_email_tag(subject: str, tags: list[str]) -> str | None:
    s = subject.lower()
    rules = [
        ("spam", ("free iphone", "!!!", "click now", "winner", "congrats")),
        ("invoice", ("invoice", "payment due", "receipt", "billing")),
        ("meeting", ("meeting", "sync", "kickoff", "calendar", "invite")),
        ("support", ("login", "password", "cannot", "help", "issue", "error")),
    ]
    for tag, words in rules:
        if tag in tags and any(w in s for w in words):
            return tag
    return None
