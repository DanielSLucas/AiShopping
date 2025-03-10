import os
import json

from langchain_core.language_models import BaseLanguageModel

from utils.logger import Logger
from scrapping_agent.scrapper import Scrapper

class ScrappingAgent:
  def __init__(self, llm: BaseLanguageModel):
    self.scrapper = Scrapper()
    self.llm = llm
    self.logger = None

  async def run(self, url: str, site_info: str, query: str, debug: bool = False):
    self.logger = Logger(show_debug_logs=debug)
    try:
      await self.scrapper.initialize(url, headless=not debug)

      init_msg = self.get_initial_message(url, site_info, query)
      self.logger.debug(f"[👤] {init_msg}")

      chat = [
        { "role": "developer", "content": self.get_prompt("agent.md") },
        *self.get_conversation_sample(),
        { "role": "user", "content": init_msg },
      ]

      result = ""
      end = False
      while not end:
        raw_response = self.get_llm_raw_response(chat)
        chat.append({ "role": "assistant", "content": raw_response })
        self.logger.debug(f"[🤖] {raw_response}")

        action = raw_response.split("-####-")[1]

        action_result = await self.scrapper._async_run(action)
        chat.append({ "role": "user", "content": action_result })
        self.logger.debug(f"[🔍] {action_result}")

        if action_result == "END":
          result = action.replace("end()\n", "")
          break

      return result
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
