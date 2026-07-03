from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from string import Template
from typing import Any


@dataclass(frozen=True)
class PromptTemplate:
    name: str
    version: str
    system: str
    task: str
    rules: list[str]
    output_schema: dict[str, Any]

    def render_user_message(self, payload: dict[str, Any]) -> str:
        rendered_task = Template(self.task).safe_substitute(payload)
        return f"{rendered_task}\n\nInput JSON:\n{json.dumps(payload)}"


def load_prompt(name: str, version: str = "v1") -> PromptTemplate:
    path = Path(__file__).with_name(f"{name}.{version}.json")
    if not path.exists():
        raise FileNotFoundError(f"Prompt template not found: {path.name}")
    data = json.loads(path.read_text(encoding="utf-8"))
    return PromptTemplate(
        name=data["name"],
        version=data["version"],
        system=data["system"],
        task=data["task"],
        rules=list(data.get("rules", [])),
        output_schema=dict(data.get("output_schema", {})),
    )
