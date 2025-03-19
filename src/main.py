from os import getenv
from datetime import datetime
from time import time
import asyncio

from googleapiclient.discovery import build

from scrapping_agent.agent import ScrappingAgent
from llms import LlmOpenAi
from utils.logger import Logger

google_api_key = getenv("GOOGLE_API_KEY")
google_cse_id = getenv("GOOGLE_CSE_ID")

def google_search(query: str, num_results: int):
  service = build("customsearch", "v1", developerKey=google_api_key)

  current_year = datetime.now().year
  search_results = (
    service.cse()
    .list(
      q=query, 
      cx=google_cse_id,
      num=num_results,
      lr="lang_pt",
      dateRestrict=f"y[{current_year}]"
    )
    .execute()
  ).get('items', [])

  return [
    {
      "title": sr.get("title", ""), 
      "link": sr.get("link", ""),
      "snippet": sr.get("snippet", "")
    } 
    for sr in search_results
  ]

async def extract_data(logger, google_result, query):
  try:
    llm = LlmOpenAi("gpt-4o-mini")

    agent = ScrappingAgent(llm)

    return await agent.run(
      google_result['link'],
      google_result['title'] + "\n" + google_result['snippet'],
      query    
    )
  except:
    return f"Falha ao extrair dados do link {google_result['link']}"


entry_prompt = f"""
Você é um assistente de compras online especializado em encontrar os melhores produtos.

O usuário vai lhe enviar uma mensagem dizendo o que deseja comprar.  
Quero comprar: {{o quê o usuário quer comprar}}

Se a solicitação for muito ampla ou vaga, responda:  
## SPECIFY ##
{{Peça mais detalhes de forma clara, concisa e amigável. Pergunte sobre modelo, marca, faixa de preço ou características desejadas.}}

Se a solicitação já for específica, responda:  
## SEARCH ##
{{Gere uma query de busca no Google otimizada para encontrar os melhores resultados. A query deve:  
1. Incluir o nome do produto e características relevantes.  
2. Se houver uma faixa de preço, incluí-la de forma natural.  
3. Adicionar termos como "comprar", "preço", "promoção", "novo" para priorizar páginas de venda.  
4. Ser simples e direta, sem informações desnecessárias.  

**Exemplo:**  
Entrada do usuário: "Quero um teclado gamer mecânico com RGB de até 500 reais"  
Saída da query: `"teclado gamer mecânico RGB comprar preço promoção novo até R$500"`}}
"""

reviwer_prompt = f"""
Você é um assitente de compras online.
  - Você vai receber o conteúdo de vários rankings diferentes relacionados a determinado tipo de produto
  - Você vai escolher os que mais se repetem e que estejam de acordo com a busca do usuário
  - Você vai fazer um comparativo entre eles afim de ajudar o usuário com sua compra
  - Sua resposta deve estar num formato apropriado para ser exibido no terminal
"""

async def main2():
  start_time = time()
  logger = Logger(show_debug_logs=True)
  entry_llm = LlmOpenAi("gpt-4o-mini")

  entry_llm.set_system_prompt(entry_prompt)

  # 1 - input
  logger.debug("#1 - Query")
  query = input("O que deseja comprar? ")
  query = f"Quero comprar: {query}"
  specifications = ""
  logger.debug(f"Query: '{query}'")

  # 2 - verificar se escopo está claro
  logger.debug("#2 - Enviando pedido para o GPT")
  gpt_response = entry_llm.get_response(query)
  logger.debug(f"Resposta GPT: '{gpt_response}'")

  # 2.1 - pedir mais informações
  if gpt_response.startswith("## SPECIFY ##"):
    specifications = input(gpt_response.removeprefix("## SPECIFY ##").strip()+"\n")
    specifications = f"Especificações: {specifications}"
    gpt_response = entry_llm.get_response(specifications)
  elif not gpt_response.startswith("## SEARCH ##"):
    raise Exception("Algo deu errado na resposta do GPT")

  # 3 - Buscar tier lists relacionado ao produto
  logger.debug("#3 - Busca google")
  google_query = gpt_response.removeprefix("## SEARCH ##").strip().replace('"', "")
  logger.debug(f"Google_query: {google_query}")
  google_results = google_search(google_query, 3)
  logger.debug(str(google_results))


  # 3.1 - buscar conteudo das urls
  logger.debug("#4 - Extraindo dados das URLs")
  results_data = []
  for google_result in google_results:
    logger.debug(f"Extraindo dados de {google_result['link']}")
    results_data.append(
      {
        "link": google_result['link'],
        "data": await extract_data(logger, google_result, f"{query}\n{specifications}")
      }
    )
  results_data = "\n\n".join([f"FROM: {result['link']}\nDATA: {result['data']}" for result in results_data])
  logger.debug(f"Resultados da busca:\n\n{results_data}")
  
  reviwer_llm = LlmOpenAi("gpt-4o-mini")
  reviwer_llm.set_system_prompt(reviwer_prompt)

  logger.debug("#5 - Montando comparativo")
  result = reviwer_llm.get_response(results_data)

  # 6 - retonar comparação
  logger.debug("### RESULTADO ###")
  logger.debug(result)
    
  end_time = time()
  elapsed_time = end_time - start_time
  logger.debug(f"Elapsed time: {elapsed_time:.4f} seconds")

async def main():
  llm = LlmOpenAi("gpt-4o-mini")
  vision_llm = LlmOpenAi("gpt-4o")

  agent = ScrappingAgent(llm, vision_llm)

  # await agent.run(
  #   "https://books.toscrape.com",
  #   "All products | Books to Scrape - Sandbox\nBooks · Travel · Mystery · Historical Fiction · Sequential Art · Classics · Philosophy · Romance · Womens Fiction · Fiction · Childrens · Religion ...",
  #   "Quero comprar: livros de qualquer gênero",
  #   all_results=True,
  #   debug=True
  # )

  await agent.run(
    "https://www.mercadolivre.com.br",
    "Headset Sem Fio No mercadolivre.com.br\nFone de Ouvido Headset Gamer Havit Fuxi-H3 Black, Quad-Mode Com Fio e Sem Fio, Wireless 2,4GHz, Bluetooth, Cabo USB-C, Cabo 3,5mm. Surround, Baixa Latência.",
    "Quero comprar: Headset gamer, sem fio de até 500 reais",
    all_results=True,
    debug=True
  )

if __name__ == "__main__":
  asyncio.run(main())