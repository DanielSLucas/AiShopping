import os
import json
from datetime import datetime
from typing import List, Optional, Dict, Any

from scrapping_agent.repository import ScrapScript, ScrapScriptsRepository


class DiskScrapScriptsRepository(ScrapScriptsRepository):
  """
  Filesystem-based implementation of ScrapScriptsRepository.
  """

  def __init__(self, base_dir: str = None):
    if base_dir is None:
      base_dir = os.path.join(os.path.dirname(__file__), "scrap_scripts")
    self.base_dir = base_dir
    os.makedirs(self.base_dir, exist_ok=True)

  def _get_domain_dir(self, domain: str) -> str:
    """Get path to domain directory."""
    return os.path.join(self.base_dir, domain)

  def _get_index_path(self, domain: str) -> str:
    """Get path to domain's _index.json."""
    return os.path.join(self._get_domain_dir(domain), "_index.json")

  def _get_script_path(self, domain: str, script_id: str) -> str:
    """Get path to a script file."""
    return os.path.join(self._get_domain_dir(domain), f"{script_id}.json")

  def _load_index(self, domain: str) -> Dict[str, Any]:
    """Load domain's _index.json or return empty structure."""
    index_path = self._get_index_path(domain)
    if os.path.exists(index_path):
      with open(index_path, "r", encoding="utf-8") as f:
        return json.load(f)
    return {"domain": domain, "scripts": []}

  def _save_index(self, domain: str, index: Dict[str, Any]) -> None:
    """Save domain's _index.json."""
    domain_dir = self._get_domain_dir(domain)
    os.makedirs(domain_dir, exist_ok=True)
    
    index_path = self._get_index_path(domain)
    with open(index_path, "w", encoding="utf-8") as f:
      json.dump(index, f, indent=2, ensure_ascii=False)

  def _find_script_domain(self, script_id: str) -> Optional[str]:
    """Find which domain a script ID belongs to."""
    if not os.path.exists(self.base_dir):
      return None
    
    for domain in os.listdir(self.base_dir):
      domain_dir = self._get_domain_dir(domain)
      if not os.path.isdir(domain_dir):
        continue
      
      script_path = self._get_script_path(domain, script_id)
      if os.path.exists(script_path):
        return domain
    
    return None

  def list_by_domain(self, domain: str) -> List[ScrapScript]:
    """List all scripts for a domain."""
    index = self._load_index(domain)
    scripts = []
    
    for entry in index.get("scripts", []):
      script_path = self._get_script_path(domain, entry["id"])
      if os.path.exists(script_path):
        with open(script_path, "r", encoding="utf-8") as f:
          data = json.load(f)
          scripts.append(ScrapScript.from_storage_dict(data))
    
    return scripts

  def get_by_id(self, script_id: str) -> Optional[ScrapScript]:
    """Get a script by its unique ID."""
    domain = self._find_script_domain(script_id)
    if domain is None:
      return None
    
    script_path = self._get_script_path(domain, script_id)
    if not os.path.exists(script_path):
      return None
    
    with open(script_path, "r", encoding="utf-8") as f:
      data = json.load(f)
      return ScrapScript.from_storage_dict(data)

  def save(self, script: ScrapScript) -> ScrapScript:
    """Create or update a script (upsert)."""
    script.updated_at = datetime.now()
    
    # Ensure domain directory exists
    domain_dir = self._get_domain_dir(script.domain)
    os.makedirs(domain_dir, exist_ok=True)
    
    # Save script file using Pydantic's serialization
    script_path = self._get_script_path(script.domain, script.id)
    with open(script_path, "w", encoding="utf-8") as f:
      json.dump(script.to_storage_dict(), f, indent=2, ensure_ascii=False)
    
    # Update index
    index = self._load_index(script.domain)
    
    # Check if script already in index
    existing_idx = next(
      (i for i, s in enumerate(index["scripts"]) if s["id"] == script.id),
      None
    )
    
    entry = {
      "id": script.id,
      "name": script.name,
      "description": script.description
    }
    
    if existing_idx is not None:
      index["scripts"][existing_idx] = entry
    else:
      index["scripts"].append(entry)
    
    self._save_index(script.domain, index)
    
    return script

  def delete(self, script_id: str) -> bool:
    """Delete a script by ID."""
    domain = self._find_script_domain(script_id)
    if domain is None:
      return False
    
    # Remove script file
    script_path = self._get_script_path(domain, script_id)
    if os.path.exists(script_path):
      os.remove(script_path)
    
    # Update index
    index = self._load_index(domain)
    index["scripts"] = [s for s in index["scripts"] if s["id"] != script_id]
    self._save_index(domain, index)
    
    return True

  def exists(self, script_id: str) -> bool:
    """Check if a script with the given ID exists."""
    domain = self._find_script_domain(script_id)
    return domain is not None
