import os
import json
from asyncio import sleep
from typing import Dict, List, Any, Callable

from utils.logger import Logger
from utils.utils import extract_domain
from scrapping_agent.playwright_scrapper import PlaywrightScrapper
from scrapping_agent.repository import ScrapScript


class ScrapScriptRunner:
  def __init__(self, script: ScrapScript, input_values: Dict[str, str | int], debug: bool = False, logger: Logger = None):
    self.input_values = input_values
    self.script = script
    
    log_name = extract_domain(script.site)
    self.logger = Logger(file_name=f"scrap_{log_name}", show_debug_logs=debug) if not logger else logger
    self.debug = debug

    self.actions = ScrapScriptsStepActions(self.execute_step)
    self.errors = []

  async def run(self) -> str:
    self.validate_inputs()
    
    # Placeholder replacement on a dict representation to avoid mutating the model
    # but still allow the runner logic to work as expected.
    # We use model_dump(by_alias=True) to get keys like 'ignoreParent' as in JSON.
    script_data = self.script.model_dump(by_alias=True)
    running_script = self.replace_placeholders(script_data)

    scrapper = PlaywrightScrapper()
    extracted_data: List[str] = []

    self.logger.debug(f"Accessing '{running_script['site']}'")
    await scrapper.initialize(running_script["site"], self.debug)

    for step in running_script['steps']:
      result = await self.execute_step(scrapper, step)
      if result is False:
        break
      if (isinstance(result, dict)):
        extracted_data.append(result)
    self.logger.debug("Steps finished")

    await scrapper.close()

    if self.errors:
      return json.dumps({"errors": self.errors}, ensure_ascii=False)

    return json.dumps(extracted_data, ensure_ascii=False)


  def validate_inputs(self) -> None:
    if self.script.input_schema:
      missing_inputs = []
      for input_name in self.script.input_schema:
        if input_name not in self.input_values:
          missing_inputs.append(input_name)

      if missing_inputs:
        required_inputs = '\n- '.join([f"{k}: {v}" for k, v in self.script.input_schema.items()])
        self.logger.info(f"Error: Missing required input variables: {', '.join(missing_inputs)}")
        self.logger.info(f"Required inputs: \n- {required_inputs}")
        raise ValueError(f"Missing required input variables: {', '.join(missing_inputs)}")

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
        if placeholder == obj:
          return var_value
        if placeholder in obj:
          obj = obj.replace(placeholder, str(var_value))
    return obj
  
  async def execute_step(self, scrapper: PlaywrightScrapper, step: Dict[str, Any]) -> Dict | bool:
    action_name = step["action"]
    action = self.actions.get_action(action_name)
    stop_on_error = step.get("stopOnError", True)

    self.logger.info(f"Running {action_name}")
    self.logger.debug(f"Step {step}")

    try:
      await sleep(step.get('sleep', 0)/1000)
      result = await action(scrapper, step)
      self.logger.debug(f"Success running '{action_name}'!")

      return result if result is not None else True
    except Exception as e:
      error_msg = f"Error running '{action_name}'. {type(e).__name__}: {str(e)}"
      self.logger.debug(error_msg)
      
      if stop_on_error:
        self.errors.append(error_msg)
        return False
        
      return True
  

class ScrapScriptsStepActions:
  def __init__(self, execute_step_cb: Callable[[PlaywrightScrapper, Dict[str, Any]], bool | dict]):
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
    count = 0

    while True:
      count += 1
      if count > step.get("limit", 100) or len(steps) == 0:
        break
      
      rst = {}

      for inner_step in steps:
        enriched_step = inner_step.copy()
        
        if (not inner_step.get("ignoreParent", False)):
          enriched_step["parentSelector"] = step["selector"]
          enriched_step["parentIndex"] = count-1

        inner_step_result = await self.execute_step(scrapper, enriched_step)

        if not inner_step_result:
          count = step.get("limit", 100) +1
          break

        if isinstance(inner_step_result, dict):
          rst.update(inner_step_result)
      
      result[step_label].append(rst)

    return result