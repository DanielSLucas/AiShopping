import os
import json
import sys
import re
import asyncio
from urllib.parse import urlparse
from typing import Dict, List, Any

from playwright.async_api import async_playwright, Page, ElementHandle
from utils.logger import Logger

class ScrapScriptRunner:
  def __init__(self, scrap_script: Dict[str, Any], input_values: Dict[str, str | int], debug: bool = False):
    self.input_values = input_values
    self.extracted_data: List[str] = []
    self.scrap_script: Dict[str, Any] = scrap_script
    
    log_name = urlparse(scrap_script["site"]).netloc
    self.logger = Logger(file_name=f"scrap_{log_name}", show_debug_logs=debug)

    self.actions = {
      "navigate": self.navigate,
      "fill": self.fill,
      "click": self.click,
      "extract": self.extract,
      "for_each": self.for_each
    }

  async def navigate(self, page: Page, step: Dict[str, str]) -> None:
    await page.goto(step["url"], timeout=10000)
    await page.wait_for_load_state()

  async def fill(self, page: Page, step: Dict[str, str]) -> None:
    await page.fill(step["selector"], step["text"], timeout=10000)

  async def click(self, page: Page, step: Dict[str, str]) -> None:
    await page.click(step["selector"], timeout=10000)
    await page.wait_for_load_state()

  async def extract(self, parent: Page | ElementHandle, step: Dict[str, Any]) -> str:
    result = []
    await parent.wait_for_selector(step["selector"], timeout=10000)
    el = await parent.query_selector(step["selector"])
    if el is None:
      return "Element not found"
    for prop, label in step["properties"].items():
      prop_value = await el.evaluate(f"el => el.{prop}")
      prop_value = prop_value.replace(r"\s+", " ").strip() if prop_value else "None"
      result.append(f"{label.upper()}: {prop_value}")
    return "\n".join(result)

  async def for_each(self, page: Page, step: Dict[str, Any]) -> str:
    step_label = step["label"].upper()
    limit = step["limit"]
    result = []
    await page.wait_for_selector(step["selector"], timeout=10000)
    for i, el in enumerate(await page.query_selector_all(step["selector"])):
      if i >= limit: break
      result.append("\n".join([f"{step_label} #{i+1}"] + [(await self.extract(el, in_step)) for in_step in step["forEach"]]))
    return "\n".join(result)

  async def run(self) -> str:
    self.validate_inputs()
    self.scrap_script = self.replace_placeholders(self.scrap_script)

    async with async_playwright() as p:
      browser = await p.chromium.launch(headless=False)
      page = await browser.new_page()

      self.logger.debug(f"Accessing '{self.scrap_script['site']}'")

      await page.goto(self.scrap_script["site"])
      await page.wait_for_load_state()

      for step in self.scrap_script["steps"]:
        action = self.actions[step["action"]]

        self.logger.debug(f"Running '{step['action']}'")

        try:
          result = await action(page, step)
          if isinstance(result, str):
            self.extracted_data.append(result)
        except Exception as e:
          self.logger.log(f"Error running '{step['action']}'. Error: {str(e)}")
          break

      self.logger.debug("Steps finished")
      await browser.close()

    return "\n\n".join(self.extracted_data)

  def validate_inputs(self) -> None:
    if "input" in self.scrap_script:
      missing_inputs = []
      for input_name in self.scrap_script["input"]:
        if input_name not in self.input_values:
          missing_inputs.append(input_name)

      if missing_inputs:
        required_inputs = '\n- '.join([f"{k}: {v}" for k, v in self.scrap_script['input'].items()])
        self.logger.log(f"Error: Missing required input variables: {', '.join(missing_inputs)}")
        self.logger.log(f"Required inputs: \n- {required_inputs}")
        raise ValueError

  def replace_placeholders(self, obj: Any) -> Any:
    if isinstance(obj, dict):
      for key, value in obj.items():
        obj[key] = self.replace_placeholders(value)
    elif isinstance(obj, list):
      for i, item in enumerate(obj):
        obj[i] = self.replace_placeholders(item)
    elif isinstance(obj, str):
      for var_name, var_value in self.input_values.items():
        placeholder = f"{{{{{var_name}}}}}"
        if placeholder in obj:
          obj = obj.replace(placeholder, var_value)
    return obj

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

# command line interface
def main():
  json_file, input_values = parse_args()
  ssm = ScrapScriptsManager()
  scrap_script = ssm.get(urlparse(json_file).netloc)
  scraper = ScrapScriptRunner(scrap_script, input_values, debug=True)
  asyncio.run(scraper.run())
  save_results(scraper.extracted_data, "extracted_data.txt")

def save_results(extracted_data: str, output_file: str = 'extracted_data.txt') -> None:
  with open(output_file, 'w') as file:
    file.write("\n\n".join(extracted_data))

def parse_args() -> tuple[str, Dict[str, str]]:
  if len(sys.argv) < 2:
    print("Error: Missing JSON file path")
    print("Usage: python scrap.py <json_file> [var_name=\"var value\" ...]")
    sys.exit(1)

  json_file = sys.argv[1]
  input_values = {}

  for arg in sys.argv[2:]:
    match = re.match(r'^([^=]+)=(.+)$', arg.strip())
    if not match:
      print(f"Error: Invalid input format: '{arg}'")
      print("Expected format: var_name=\"var value\"")
      sys.exit(1)

    var_name, var_value = match.groups()
    input_values[var_name] = int(var_value) if var_value.isdigit() else var_value

  return json_file, input_values

if __name__ == "__main__":
  main()
