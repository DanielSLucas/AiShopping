import os
import json

from llms import LlmBase
from utils.logger import Logger
from scrapping_agent.scrapper import Scrapper

class ScrappingAgent:
  def __init__(self, llm: LlmBase):
    self.scrapper = Scrapper()
    self.llm = llm
    self.logger = None

  async def run(self, url: str, site_info: str, query: str, debug: bool = False):
    self.logger = Logger(show_debug_logs=debug)
    try:
      await self.scrapper.initialize(url, headless=not debug)

      init_msg = self.get_initial_message(url, site_info, query)
      self.logger.debug(f"[👤] {init_msg}")

      self.llm.set_system_prompt(self.get_prompt("agent.md"))
      self.llm.add_conversation_sample(*self.get_conversation_sample())

      raw_response = self.llm.get_response(init_msg)
      self.logger.debug(f"[🤖] {raw_response}")

      while True:
        action = raw_response.split("-####-")[1]

        action_result = await self.scrapper._async_run(action)
        self.logger.debug(f"[🔍] {action_result}")

        if action_result == "END":
          return action.replace("end()\n", "")

        raw_response = self.llm.get_response(action_result)
        self.logger.debug(f"[🤖] {raw_response}")
    finally:
      await self.scrapper.close()

  def get_initial_message(self, url: str, site_info: str, query: str):
    return self \
      .get_prompt("init.md") \
      .replace("{url}", url) \
      .replace("{site_info}", site_info) \
      .replace("{query}", query)

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
    
  def get_llm_raw_response(self, chat: list):
    response = self.llm.invoke(chat)
    return response.content.strip()
