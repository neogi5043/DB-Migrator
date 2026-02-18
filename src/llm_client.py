"""
LLM client — Azure OpenAI via LangChain with JSON-mode prompting (GPT-4.1).

Generates per-table migration mappings as structured JSON.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from langchain_openai import AzureChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

from src.connectors.base import CANONICAL_TO_TARGET

log = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


def _build_canonical_table(target_engine: str) -> str:
    """Build the canonical → target type table for prompt injection."""
    lines = [f"{'Canonical':<16} {target_engine}"]
    lines.append("-" * 40)
    for canon, targets in CANONICAL_TO_TARGET.items():
        native = targets.get(target_engine, "—")
        lines.append(f"{canon:<16} {native}")
    return "\n".join(lines)


def _load_advisory(source_engine: str) -> str:
    """Load engine-specific advisory text."""
    path = PROMPTS_DIR / "source_advisories" / f"{source_engine}.txt"
    if path.exists():
        return path.read_text(encoding="utf-8")
    return f"No specific advisory for {source_engine}."


def build_llm(config: dict) -> AzureChatOpenAI:
    """Create the Azure OpenAI LLM instance via LangChain."""
    llm_cfg = config["llm"]
    return AzureChatOpenAI(
        azure_deployment=llm_cfg["azure_deployment"],
        azure_endpoint=llm_cfg["azure_endpoint"],
        api_key=llm_cfg["azure_api_key"],
        api_version=llm_cfg["azure_api_version"],
        temperature=llm_cfg.get("temperature", 0),
        max_retries=llm_cfg.get("max_retries", 4),
        model_kwargs={"response_format": {"type": "json_object"}},
    )


def generate_mapping(
    llm: AzureChatOpenAI,
    source_engine: str,
    target_engine: str,
    target_schema: str,
    table_spec: dict,
) -> dict:
    """Call the LLM to produce a JSON mapping for one table.

    Returns the parsed mapping dict.
    """
    system_template = (PROMPTS_DIR / "system_v1.txt").read_text(encoding="utf-8")
    user_template = (PROMPTS_DIR / "user_table.txt").read_text(encoding="utf-8")

    system_text = system_template.format(
        source_engine=source_engine,
        target_engine=target_engine,
        canonical_to_target_table=_build_canonical_table(target_engine),
        source_advisory=_load_advisory(source_engine),
    )

    user_text = user_template.format(
        source_engine=source_engine,
        target_engine=target_engine,
        target_schema=target_schema,
        table_json=json.dumps(table_spec, indent=2, default=str),
    )

    messages = [
        SystemMessage(content=system_text),
        HumanMessage(content=user_text),
    ]

    log.info("Sending LLM request for table %s.%s",
             table_spec.get("schema", ""), table_spec.get("name", ""))

    response = llm.invoke(messages)
    raw = response.content.strip()

    try:
        mapping = json.loads(raw)
    except json.JSONDecodeError as e:
        log.error("LLM returned invalid JSON: %s\nRaw: %s", e, raw[:500])
        raise ValueError(f"LLM JSON parse error: {e}") from e

    log.info("Received mapping for %s → %s.%s (%d columns)",
             mapping.get("source_table"), target_schema,
             mapping.get("target_table"), len(mapping.get("columns", [])))
    return mapping
