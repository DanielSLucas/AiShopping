import json
import re
import sys
import time
from typing import Dict
from uuid import uuid4

from langchain_openai import ChatOpenAI

from scrapping_agent.agent import ScrappingAgent
from shopping_agent.agent import ShoppingAgent
from utils.logger import Logger

from scrapping_agent.scrap import ScrapScriptsManager, ScrapScriptRunner

def log_listener(msg: str):
  print(msg)

async def run_shopping_agent_cli():
  start_time = time.time()
  llm = ChatOpenAI(model="gpt-4.1-mini")
  logger = Logger(show_debug_logs=True, logger_id=str(uuid4()))
  logger.LOGS_QUEUE.put = log_listener
  agent = ShoppingAgent(llm, logger)

  user_input = input("O que deseja comprar? ")

  res = await agent.run(user_input, recursion_limit=100)

  if res["type"] == "ASK_HUMAN":
    question = res["content"]
    logger.info(res)
    answer = input(f"{question}\n\nUser: ")
    start_time = time.time()
    res = await agent.run(user_input, specifications=answer, recursion_limit=100)

  logger.info(res)
  end_time = time.time()
  logger.info({"type": "END_TIME", "content": f"{end_time - start_time:.2f}s"})

async def run_scrapping_agent():
  """Main function to execute the web navigation agent."""
  llm = ChatOpenAI(model="o4-mini")
  logger = Logger(file_name="cli",show_debug_logs=True)
  logger.LOGS_QUEUE.put = log_listener

  agent = ScrappingAgent(llm, debug=True, logger=logger)
  # await agent.initialize("https://books.toscrape.com", headless=False)
  # await agent.initialize("https://amazon.com.br", headless=False)
  await agent.initialize("https://jurisdf.tjdft.jus.br/resultado?sinonimos=true&espelho=true&inteiroTeor=false", headless=False)
  # await agent.initialize("https://www2.tjal.jus.br/cjsg/resultadoCompleta.do", headless=False)
      
  result = await agent.run("Trazer link do pdf de 3 processos sobre IPTU", all_results=False)

  await agent.close()
  print(result)

async def run_scrap_script():
  json_file, input_values = parse_args()
  ssm = ScrapScriptsManager()
  scrap_script = ssm.get(json_file.replace('.json', ""))
  scraper = ScrapScriptRunner(scrap_script, input_values, debug=True)
  scraper.logger.LOGS_QUEUE.put = log_listener
  await scraper.run()
  save_results(scraper.extracted_data, "extracted_data.txt")

def save_results(extracted_data: str, output_file: str = 'extracted_data.txt') -> None:
  with open(output_file, 'w') as file:
    file.write(json.dumps(extracted_data, ensure_ascii=False))

def parse_args() -> tuple[str, Dict[str, str]]:
  if len(sys.argv) < 3:
    print("Error: Missing JSON file path")
    print("Usage: python src/main.py --sscript <json_file> [var_name=\"var value\" ...]")
    sys.exit(1)
  
  json_file = sys.argv[2]
  input_values = {}

  for arg in sys.argv[3:]:
    match = re.match(r'^([^=]+)=(.+)$', arg.strip())
    if not match:
      print(f"Error: Invalid input format: '{arg}'")
      print("Expected format: var_name=\"var value\"")
      sys.exit(1)

    var_name, var_value = match.groups()
    input_values[var_name] = int(var_value) if var_value.isdigit() else var_value

  return json_file, input_values
