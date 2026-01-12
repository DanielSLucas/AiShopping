from abc import ABC, abstractmethod
from datetime import datetime
from typing import List, Optional, Dict, Any, Union, Literal, Self
from uuid import uuid4

from pydantic import BaseModel, Field

class BaseStep(BaseModel):
  """Base class for all step types"""
  action: str
  sleep: int = 0
  ignore_parent: bool = Field(default=False, alias="ignoreParent")

  model_config = {
    "populate_by_name": True,
    "extra": "allow"
  }


class NavigateStep(BaseStep):
  """Navigate to a URL"""
  action: Literal["navigate"] = "navigate"
  url: str


class GoBackStep(BaseStep):
  """Navigate back"""
  action: Literal["go_back"] = "go_back"


class FillStep(BaseStep):
  """Fill an input element"""
  action: Literal["fill"] = "fill"
  selector: str
  text: str
  parent_selector: Optional[str] = Field(default=None, alias="parentSelector")
  parent_index: Optional[int] = Field(default=None, alias="parentIndex")


class ClickStep(BaseStep):
  """Click an element"""
  action: Literal["click"] = "click"
  selector: str
  is_download: bool = Field(default=False, alias="isDownload")
  parent_selector: Optional[str] = Field(default=None, alias="parentSelector")
  parent_index: Optional[int] = Field(default=None, alias="parentIndex")


class WaitSelectorStep(BaseStep):
  """Wait for a selector to appear"""
  action: Literal["wait_selector"] = "wait_selector"
  selector: str
  timeout: int = 0


class ExtractStep(BaseStep):
  """Extract data from elements"""
  action: Literal["extract"] = "extract"
  selector: str
  properties: Dict[str, str]
  parent_selector: Optional[str] = Field(default=None, alias="parentSelector")
  parent_index: Optional[int] = Field(default=None, alias="parentIndex")


class ForEachStep(BaseStep):
  """Loop over elements"""
  action: Literal["for_each"] = "for_each"
  selector: str
  label: str
  limit: Union[int, str] = 100
  steps: List["ScrapStep"] = Field(default_factory=list)


ScrapStep = Union[
  NavigateStep,
  GoBackStep,
  FillStep,
  ClickStep,
  WaitSelectorStep,
  ExtractStep,
  ForEachStep
]

# Update forward reference for ForEachStep
ForEachStep.model_rebuild()


class ScrapScript(BaseModel):
  """
  Represents a scraping script with metadata.
  """
  id: str = Field(default_factory=lambda: str(uuid4()))
  domain: str
  name: str
  description: str
  site: str
  input_schema: Dict[str, str] = Field(default_factory=dict, alias="input")
  steps: List[ScrapStep] = Field(default_factory=list)
  created_at: datetime = Field(default_factory=datetime.now)
  updated_at: datetime = Field(default_factory=datetime.now)

  model_config = {
    "populate_by_name": True,
    "ser_json_timedelta": "iso8601"
  }

  def to_storage_dict(self) -> Dict[str, Any]:
    """
    Convert to dict format for storage (JSON files, DB, etc.).
    Uses Pydantic's model_dump with alias serialization.
    """
    data = self.model_dump(by_alias=True)
    # Convert datetime to ISO format strings for JSON serialization
    data["created_at"] = self.created_at.isoformat()
    data["updated_at"] = self.updated_at.isoformat()
    return data

  @classmethod
  def from_storage_dict(cls, data: Dict[str, Any]) -> Self:
    """
    Create ScrapScript from storage dict.
    Handles datetime parsing from ISO strings.
    """
    # Parse datetime strings if present
    if "created_at" in data and isinstance(data["created_at"], str):
      data["created_at"] = datetime.fromisoformat(data["created_at"])
    if "updated_at" in data and isinstance(data["updated_at"], str):
      data["updated_at"] = datetime.fromisoformat(data["updated_at"])
    
    return cls.model_validate(data)

  def to_execution_dict(self) -> Dict[str, Any]:
    """
    Convert to dict format expected by ScrapScriptRunner.
    Excludes id, domain, created_at, updated_at.
    """
    return {
      "site": self.site,
      "description": self.description,
      "input": self.input_schema,
      "steps": self.steps
    }

  def to_summary(self) -> Dict[str, Any]:
    """
    Summary for agent prompt (id, name, description, inputs).
    Used by script_executor to choose which script to run.
    """
    def format_steps(steps_list: list[ScrapStep]) -> list[str]:
      lines = []
      for step in steps_list:
        action = getattr(step, "action")
        selector = getattr(step, "selector", None) or getattr(step, "url", "")
        lines.append(f"{action} -> {selector}")
        if hasattr(step, "steps"):
          inner_steps = format_steps(step.steps)
          lines.append(inner_steps)
      return lines

    steps = format_steps(self.steps)

    return {
      "id": self.id,
      "name": self.name,
      "description": self.description,
      "inputs": self.input_schema,
      "steps": steps
    }

class ScrapScriptsRepository(ABC):
  """
  Abstract base class for script storage.
  """

  @abstractmethod
  def list_by_domain(self, domain: str) -> List[ScrapScript]:
    """
    List all scripts for a domain.
    
    Args:
      domain: The domain to list scripts for (e.g., "amazon.com.br")
    
    Returns:
      List of ScrapScript objects for the domain
    """
    pass

  @abstractmethod
  def get_by_id(self, script_id: str) -> Optional[ScrapScript]:
    """
    Get a script by its unique ID.
    
    Args:
      script_id: UUID of the script
    
    Returns:
      ScrapScript if found, None otherwise
    """
    pass

  @abstractmethod
  def save(self, script: ScrapScript) -> ScrapScript:
    """
    Create or update a script (upsert).
    
    If script.id exists, updates. Otherwise creates new.
    Always updates `updated_at` timestamp.
    
    Args:
      script: The ScrapScript to save
    
    Returns:
      The saved ScrapScript (with updated timestamps)
    """
    pass

  @abstractmethod
  def delete(self, script_id: str) -> bool:
    """
    Delete a script by ID.
    
    Args:
      script_id: UUID of the script to delete
    
    Returns:
      True if deleted, False if not found
    """
    pass

  @abstractmethod
  def exists(self, script_id: str) -> bool:
    """
    Check if a script with the given ID exists.
    
    Args:
      script_id: UUID to check
    
    Returns:
      True if exists, False otherwise
    """
    pass

  def get_domain_summaries(self, domain: str) -> List[Dict[str, Any]]:
    """
    Get summaries of all scripts for a domain (for agent prompts).
    
    Args:
      domain: The domain to get summaries for
    
    Returns:
      List of summary dicts with id, name, description, inputs
    """
    scripts = self.list_by_domain(domain)
    return [s.to_summary() for s in scripts]
