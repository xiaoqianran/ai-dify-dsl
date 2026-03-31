"""Dify application-level models."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict


class Dependency(BaseModel):
    """A marketplace or package dependency."""

    model_config = ConfigDict(extra="allow")

    current_identifier: Optional[str] = None
    type: str = "marketplace"
    value: Dict[str, Any] = {}


class DifyApp(BaseModel):
    """Top-level app metadata in the DSL."""

    model_config = ConfigDict(extra="allow")

    name: str = ""
    description: str = ""
    icon: str = ""
    icon_background: str = ""
    mode: str = "workflow"  # workflow | chat | completion
    use_icon_as_answer_icon: bool = False
