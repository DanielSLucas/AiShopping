import json
import sys
import re
from typing import Dict, List, Any

from playwright.sync_api import sync_playwright, Page, ElementHandle
from utils.logger import Logger

class ScrapScriptRunner:
  def __init__(self, json_file: str, input_values: Dict[str, str], debug: bool = False):
    self.json_file = json_file
    self.input_values = input_values
    self.extracted_data: List[str] = []
    self.scrap_script: Dict[str, Any] = {}
    # Extract the base filename without extension for the logger
    log_name = json_file.split("/")[-1].split(".")[0] if "/" in json_file else json_file.split(".")[0]
    self.logger = Logger(file_name=f"scrap_{log_name}", show_debug_logs=debug)

    self.actions = {
      "fill": self.fill,
      "click": self.click,
      "extract": self.extract,
      "extract_all": self.extract_all
    }

  def fill(self, page: Page, step: Dict[str, str]) -> None:
    page.fill(step["selector"], step["text"])

  def click(self, page: Page, step: Dict[str, str]) -> None:
    page.click(step["selector"])
    page.wait_for_load_state()

  def extract(self, parent: Page | ElementHandle, step: Dict[str, Any]) -> str:
    result = []
    el = parent.query_selector(step["selector"])
    if el is None:
        return "Element not found"
    for prop, label in step["properties"].items():
        prop_value = el.evaluate(f"el => el.{prop}").replace(r"\s+", " ").strip()
        result.append(f"{label.upper()}: {prop_value}")
    return "\n".join(result)

  def extract_all(self, page: Page, step: Dict[str, Any]) -> str:
    step_label = step["label"].upper()
    limit = step["limit"]
    result = []
    page.wait_for_selector(step["selector"])
    for i, el in enumerate(page.query_selector_all(step["selector"])):
        if i >= limit: break
        result.append("\n".join([f"{step_label} #{i+1}"] + [self.extract(el, in_step) for in_step in step["forEach"]]))
    return "\n".join(result)

  def run(self) -> str:
    self.load_script()
    self.validate_inputs()
    self.scrap_script = self.replace_placeholders(self.scrap_script)

    with sync_playwright() as p:
      browser = p.chromium.launch(headless=False)
      page = browser.new_page()

      self.logger.debug(f"Accessing '{self.scrap_script['site']}'")

      page.goto(self.scrap_script["site"])
      page.wait_for_load_state()

      for step in self.scrap_script["steps"]:
        action = self.actions[step["action"]]

        self.logger.debug(f"Running '{step['action']}'")

        try:
          result = action(page, step)
          if isinstance(result, str):
            self.extracted_data.append(result)
        except Exception as e:
          self.logger.log(f"Error running '{step['action']}'. Error: {str(e)}")
          break

      self.logger.debug("Steps finished")
      browser.close()

    return "\n\n".join(self.extracted_data)

  def load_script(self) -> None:
    try:
      with open(self.json_file, 'r') as file:
        self.scrap_script = json.load(file)
    except FileNotFoundError:
      self.logger.log(f"Error: JSON file not found: {self.json_file}")
      raise FileNotFoundError
    except json.JSONDecodeError:
      self.logger.log(f"Error: Invalid JSON format in file: {self.json_file}")
      raise json.JSONDecodeError

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

  def save_results(self, output_file: str = 'extracted_data.txt') -> None:
    self.logger.debug("Saving extracted data")
    with open(output_file, 'w') as file:
      file.write("\n\n".join(self.extracted_data))

# command line interface
def main():
  json_file, input_values = parse_args()
  scraper = ScrapScriptRunner(json_file, input_values, debug=True)
  scraper.run()
  scraper.save_results()

def parse_args() -> tuple[str, Dict[str, str]]:
  # We'll use a generic name for the CLI logger since we don't know the JSON filename yet
  logger = Logger(file_name="scrap_cli", show_debug_logs=True)

  if len(sys.argv) < 2:
    logger.log("Error: Missing JSON file path")
    logger.log("Usage: python scrap.py <json_file> [var_name=\"var value\" ...]")
    sys.exit(1)

  json_file = sys.argv[1]
  input_values = {}

  for arg in sys.argv[2:]:
    match = re.match(r'^([^=]+)=(.+)$', arg.strip())
    if not match:
      logger.log(f"Error: Invalid input format: '{arg}'")
      logger.log("Expected format: var_name=\"var value\"")
      sys.exit(1)

    var_name, var_value = match.groups()
    input_values[var_name] = var_value

  return json_file, input_values

if __name__ == "__main__":
  main()
