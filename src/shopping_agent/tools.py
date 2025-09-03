import asyncio

from langchain_core.tools import tool

from shopping_agent.web_search import extract_data, google_search
from utils.logger import Logger

def make_receptionist_tools(logger: Logger) -> list:
  @tool
  async def ask_more_details(question: str) -> str:
    """
    Ask the human for more details.
    Args:
      question: The question to ask.
    Returns:
      A string containing the answer.
    """
    return f"Please provide more details about your request: {question}"

  return [ask_more_details]

def make_researcher_tools(logger: Logger) -> list:
  @tool
  async def web_search(query: str) -> str:
    """
    Search for information on the web.
    Args:
      query: The search query.
    Returns:
      A string containing the search results.
    """
    
    search_results = google_search(query, 3)

    logger.info({"type": "SEARCH", "content": { "query": query, "sites": [search_result['link'] for search_result in search_results] }})
    
    extraction_tasks = [extract_data(search_result, query, logger) for search_result in search_results]
    results = await asyncio.gather(*extraction_tasks)

    link_n_data =[
      f"FROM: {google_result['link']}\nDATA: {result}"
      for google_result, result in zip(search_results, results)
    ]

    return "---\n".join(link_n_data)
  
  @tool
  async def save_relevant_data(data: dict) -> str:
    """
    Save relevant information from your research for the analyst use later.
    Args:
      data: A dict containing the information to save.
    Returns:
      A string "Saved!"
    """
    return "Saved!"
  
  return [web_search, save_relevant_data]
