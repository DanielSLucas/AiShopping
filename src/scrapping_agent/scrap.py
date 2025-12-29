import os
import json
from asyncio import sleep

from typing import Dict, List, Any, Callable

from utils.logger import Logger
from utils.utils import extract_domain

from scrapping_agent.playwright_scrapper import PlaywrightScrapper

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

class ScrapScriptRunner:
  def __init__(self, scrap_script: Dict[str, Any], input_values: Dict[str, str | int], debug: bool = False):
    self.input_values = input_values
    self.extracted_data: List[str] = []
    self.scrap_script: Dict[str, Any] = scrap_script
    
    log_name = extract_domain(scrap_script["site"])
    self.logger = Logger(file_name=f"scrap_{log_name}", show_debug_logs=debug)
    self.debug = debug

    self.actions = ScrapScriptsStepActions(self.execute_step)

  async def run(self) -> str:
    self.validate_inputs()
    self.scrap_script = self.replace_placeholders(self.scrap_script)

    scrapper = PlaywrightScrapper()

    self.logger.debug(f"Accessing '{self.scrap_script['site']}'")
    await scrapper.initialize(self.scrap_script["site"], self.debug)

    for step in self.scrap_script['steps']:
      result = await self.execute_step(scrapper, step)
      if (isinstance(result, dict)):
        self.extracted_data.append(result)
    self.logger.debug("Steps finished")

    await scrapper.close()

    return json.dumps(self.extracted_data, ensure_ascii=False)


  def validate_inputs(self) -> None:
    if "input" in self.scrap_script:
      missing_inputs = []
      for input_name in self.scrap_script["input"]:
        if input_name not in self.input_values:
          missing_inputs.append(input_name)

      if missing_inputs:
        required_inputs = '\n- '.join([f"{k}: {v}" for k, v in self.scrap_script['input'].items()])
        self.logger.info(f"Error: Missing required input variables: {', '.join(missing_inputs)}")
        self.logger.info(f"Required inputs: \n- {required_inputs}")
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
  
  async def execute_step(self, scrapper: PlaywrightScrapper, step: Dict[str, Any]) -> Dict | bool:
    action_name = step["action"]
    action = self.actions.get_action(action_name)

    self.logger.info(f"Running {action_name}")
    self.logger.debug(f"Step {step}")

    try:
      await sleep(step.get('sleep', 0)/1000)
      result = await action(scrapper, step)
      self.logger.debug(f"Success running '{action_name}'!")

      return result if result is not None else True
    except Exception as e:
      self.logger.debug(f"Error running '{action_name}'. {type(e).__name__}: {str(e)}")
      return not step.get("stopOnError", True)
  

class ScrapScriptsStepActions:
  def __init__(self, execute_step_cb: Callable[[PlaywrightScrapper,dict], bool | dict]):
    self.execute_step = execute_step_cb
    self.__actions = {
      "navigate": self.navigate,
      "go_back": self.go_back,
      "fill": self.fill,
      "click": self.click,
      "extract": self.extract,
      "for_each": self.for_each,
      "wait_selector": self.wait_selector
    }

  def get_actions(self):
    return self.__actions
  
  def get_action(self, name: str):
    if name not in self.__actions:
      raise NameError(f"No action named `{name}`")
    return self.__actions[name]

  async def navigate(self, scrapper: PlaywrightScrapper, step: Dict[str, str]) -> None:
    await scrapper.navigate(step["url"])

  async def go_back(self, scrapper: PlaywrightScrapper, step: Dict[str, str]) -> None:
    await scrapper.go_back()

  async def fill(self, scrapper: PlaywrightScrapper, step: Dict[str, str]) -> None:
    await scrapper.fill(step["selector"], step["text"], { "parent_selector": step.get("parentSelector"), "parent_index": step.get("parentIndex") })

  async def click(self, scrapper: PlaywrightScrapper, step: Dict[str, str]) -> None:
    await scrapper.click(step["selector"], step.get("isDownload", False), { "parent_selector": step.get("parentSelector"), "parent_index": step.get("parentIndex") })

  async def wait_selector(self, scrapper: PlaywrightScrapper, step: Dict[str, str]) -> None:
    await scrapper.wait_selector(step["selector"], timeout=step.get("timeout", 0))

  async def extract(self, scrapper: PlaywrightScrapper, step: Dict[str, str]) -> Dict[str, str]:
    return await scrapper.extract(step["selector"], step["properties"], { "parent_selector": step.get("parentSelector"), "parent_index": step.get("parentIndex") })

  async def for_each(self, scrapper: PlaywrightScrapper, step: Dict[str, str]) -> Dict:
    step_label = step["label"]
    result = { step_label: [] }

    steps = step.get("steps", [])
    count = 0;

    while True:
      count += 1
      if count > step.get("limit", 100) or len(steps) == 0:
        break
      
      rst = {}

      for inner_step in steps:
        enriched_step = inner_step.copy()
        
        if (not inner_step.get("ignoreParent", False)):
          enriched_step["parentSelector"] = step["selector"]
          enriched_step["parentIndex"] = count

        inner_step_result = await self.execute_step(scrapper, enriched_step)

        if not inner_step_result:
          count = step.get("limit", 100) +1
          break

        if isinstance(inner_step_result, dict):
          rst.update(inner_step_result)
      
      result[step_label].append(rst)

    return result