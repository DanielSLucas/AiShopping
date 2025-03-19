import os
import json
from urllib.parse import urlparse

from llms import LlmBase
from utils.logger import Logger
from scrapping_agent.scrapper import Scrapper

class ScrappingAgent:
  def __init__(self, llm: LlmBase, vision_llm: LlmBase):
    self.scrapper = Scrapper()
    self.llm = llm
    self.vision_llm = vision_llm
    self.logger = None

  async def run(self, url: str, site_info: str, query: str, debug: bool = False, all_results: bool = False):
    host = urlparse(url).netloc
    self.logger = Logger(file_name=f"{host}_scrap",show_debug_logs=debug)
    try:
      self.logger.debug(f"[💻] Carregando página")
      await self.scrapper.initialize(url, headless=not debug)

      self.logger.debug(f"[🤖] Analisando página")
      page_print = await self.scrapper._print()
      print_description = self.add_print_description(page_print)

      init_msg = self.get_initial_message(url, site_info, query, all_results, print_description)
      self.logger.debug(f"[👤] {init_msg}")

      self.llm.set_system_prompt(self.get_prompt("agent.md"))
      # self.llm.add_conversation_sample(*self.get_conversation_sample())

      raw_response = self.llm.get_response(init_msg)
      self.logger.debug(f"[🤖] {raw_response}")

      while True:
        if "-####-" not in raw_response:
          self.logger.debug("[⚠️] Missing delimiter '-####-' in response.")
          raw_response = self.llm.get_response(f"⚠️ Your response is missing the delimiter '-####-'. Please correct it.\n{raw_response}")
          self.logger.debug(f"[🤖] Corrected response: {raw_response}")

        action = raw_response.split("-####-")[1].strip()
        is_more_than_one_action = len(action.splitlines()) > 1

        if is_more_than_one_action:
          self.logger.debug("[⚠️] Trying to execute more than 1 action at once")
          action = action.splitlines()[0]

        action_result = await self.scrapper._async_run(action)

        if action_result.startswith("PRINT:"):
          action_result = self.add_print_description(action_result)
        
        self.logger.debug(f"[🔍] {action_result}")

        if action_result == "END":
          final_response = action.replace("end()\n", "").strip()
          if not final_response:
            self.logger.debug("[⚠️] Missing final response after 'end()' function.")
            action_result = f"⚠️ Your response is missing final response after 'end()' function. Please correct it."
          else:
            return final_response

        if is_more_than_one_action:
          action_result = f"⚠️ You tried to execute more than 1 action at once. Only action {action} was executed. \nResult:\n{action_result}"

        raw_response = self.llm.get_response(action_result)
        self.logger.debug(f"[🤖] {raw_response}")
    finally:
      await self.scrapper.close()

  def add_print_description(self, action_result):
    print_path = action_result.splitlines()[0].split(":")[1].strip()
    print_description = self.get_print_description(print_path)
    os.remove(print_path)
    action_result = f"{action_result}\nDescription: {print_description}"
    return action_result

  def get_initial_message(self, url: str, site_info: str, query: str, all_results: bool, print_description: str):    
    return self \
      .get_prompt("init.md") \
      .replace("{url}", url) \
      .replace("{site_info}", site_info) \
      .replace("{query}", query) \
      .replace("{all}", str(all_results)) \
      .replace("{print_description}", str(print_description))

  def get_prompt(self, prompt_file: str):
    base_path = os.path.dirname(__file__)
    prompt_path = os.path.join(base_path, "prompts", prompt_file)
    with open(prompt_path, "r") as f:
      return f.read()
    
  def get_conversation_sample(self):
    base_path = os.path.dirname(__file__)
    prompt_path = os.path.join(base_path, "prompts", "extract_products_msgs_sample.json")
    with open(prompt_path) as f:
      return json.load(f)
  
  def get_print_description(self, print_path: str) -> str:
    self.vision_llm.set_system_prompt(self.get_prompt("vision.md"))
    return self.vision_llm.get_image_response(
      f"Print: {print_path}\nDescription: ",
      print_path
    )
