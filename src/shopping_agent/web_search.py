from os import getenv
from datetime import datetime

from langchain_openai import ChatOpenAI
from googleapiclient.discovery import build

from scrapping_agent.agent import ScrappingAgent

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
      dateRestrict=f"y[{current_year}]",
      excludeTerms="youtube tiktok"
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

async def extract_data(google_result, query):
  try:
    llm = ChatOpenAI(model="o4-mini")

    agent = ScrappingAgent(llm, debug=False)
    await agent.initialize(google_result['link'], headless=True)
      
    result = await agent.run(query, all_results=True)

    await agent.close()
    return result 
  except:
    return f"Falha ao extrair dados do link {google_result['link']}"
