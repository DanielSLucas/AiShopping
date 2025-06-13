import asyncio

from langchain_openai import ChatOpenAI

from scrapping_agent.agent import ScrappingAgent
from shopping_agent.agent import ShoppingAgent
import time

async def main():
  start_time = time.time()
  llm = ChatOpenAI(model="gpt-4.1-mini")
  agent = ShoppingAgent(llm, debug=True)

  user_input = input("O que deseja comprar? ")

  res = await agent.run(user_input, recursion_limit=100)

  if res.startswith("ASK_HUMAN:"):
    question = res.removeprefix("ASK_HUMAN:")
    print(question)
    answer = input("User: ")
    start_time = time.time()
    res = await agent.continue_from_input(answer)

  end_time = time.time()
  print(f"Tempo de execução: {end_time - start_time:.2f} segundos")

async def main2():
  """Main function to execute the web navigation agent."""
  llm = ChatOpenAI(model="o4-mini")

  agent = ScrappingAgent(llm, debug=True)
  await agent.initialize("https://www.mercadolivre.com.br", headless=False)
  # await agent.initialize("https://www.amazon.com.br", headless=False)
  # await agent.initialize("https://books.toscrape.com", headless=False)
      
  result = await agent.run("Quero comprar: Teclado gamer, sem fio ", all_results=False)
  # result = await agent.run("Quero comprar: todos os livros de ficção cientifica", all_results=True)

  await agent.close()
  print(result)


if __name__ == "__main__":
  asyncio.run(main())