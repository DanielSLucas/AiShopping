import asyncio

from scrapping_agent.agent import ScrappingAgent
from llms import LlmOpenAi

llm = LlmOpenAi("gpt-4o-mini")

agent = ScrappingAgent(llm)

asyncio.run(
  agent.run(
    "https://mercadolivre.com.br",
    "Site de compras",
    "Quero uma lampada inteligente",
    debug=True
  )
)