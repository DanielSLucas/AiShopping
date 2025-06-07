import os
import json

class ScrapScriptsManager:
  SCRAP_SCRIPTS_DIR = os.path.join(os.path.dirname(__file__), "scrap_scripts")

  def list_all(self):
    return [f.replace(".json", "") for f in os.listdir(self.SCRAP_SCRIPTS_DIR)]

  def exists(self, script_name: str) -> bool:
    return os.path.exists(os.path.join(self.SCRAP_SCRIPTS_DIR, f"{script_name}.json"))

  def get(self, script_name: str) -> dict:
    return json.load(open(os.path.join(self.SCRAP_SCRIPTS_DIR, f"{script_name}.json")))
  
  def save(self, script_name: str, script: dict) -> None:
    with open(os.path.join(self.SCRAP_SCRIPTS_DIR, f"{script_name}.json"), "w") as f:
      json.dump(script, f, indent=2)
