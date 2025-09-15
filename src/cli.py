import time
from uuid import uuid4

from langchain_openai import ChatOpenAI

from scrapping_agent.agent import ScrappingAgent
from shopping_agent.agent import ShoppingAgent
from utils.logger import Logger

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
  logger = Logger(file_name="ml",show_debug_logs=True)
  logger.LOGS_QUEUE.put = log_listener

  agent = ScrappingAgent(llm, debug=True, logger=logger)
  await agent.initialize("https://books.toscrape.com", headless=False)
      
  result = await agent.run("Quero comprar: todos os livros de ficção cientifica", all_results=True)

  await agent.close()
  print(result)