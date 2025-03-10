import asyncio
from langchain_openai import ChatOpenAI

from scrapping_agent.agent import ScrappingAgent

llm = ChatOpenAI(
  model="gpt-4o-mini",
  temperature=0.5,
  max_tokens=2000
)

agent = ScrappingAgent(llm)

asyncio.run(
  agent.run(
    "https://mercadolivre.com.br",
    "Site de compras",
    "Quero uma lampada inteligente",
    debug=True
  )
)