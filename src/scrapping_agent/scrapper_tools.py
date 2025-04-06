import os
from scrapping_agent.scrapper import Scrapper
from langchain_core.language_models import BaseChatModel
from langchain_core.tools import tool

from utils.utils import describe_web_page_print

def make_scrapper_tools(scrapper: Scrapper, vision_model: BaseChatModel = None) -> list:
  """
  Create and return the scrapping tools.
  Args:
      scrapper: The Scrapper instance to use for web scraping.
      vision_model: The vision model to use for image processing.
  Returns:
      A list of tools for web scraping and interaction.
  """
    
  @tool
  async def extract_elements(el_selector: str, trunc: bool = True, limit: int = 50, compact: bool = False) -> str:
    """
    Extracts elements from the page based on the provided selector.
    Args:
        el_selector: The selector to find elements.
        trunc: Whether to truncate the text content.
        limit: The maximum number of elements to extract.
        compact: Whether to compact identical elements with a count.
    Returns:
        A formatted string with the extracted elements.
    """
    return await scrapper.extract_elements(el_selector, trunc, limit, compact)

  @tool
  async def interact_with_element(el_selector: str, interaction: str, text: str = "") -> str:
    """
    Interacts with an element on the page based on the provided selector.
    Args:
        el_selector: The selector to find the element.
        interaction: The type of interaction to perform (click, fill).
        text: The text to fill in the element if applicable.
    Returns:
        A message indicating the result of the interaction.
    """
    return await scrapper.interact_with_element(el_selector, interaction, text)

  @tool
  async def print_page() -> str:
    """
    Takes a screenshot of the current page and returns a description of the page.
    Returns:
        A description of the page.
    """
    if vision_model is None:
      return "You need to define a vision model before using this tool."
    
    filename = await scrapper.print_page()
    page_description = describe_web_page_print(vision_model, filename)
    os.remove(filename)
    
    return page_description

  @tool
  async def page_summary() -> str:
    """
    Summarizes the current page by extracting the URL, title, description, text elements
    and interaction elements.
    Returns:
        A formatted string with the page summary.
    """
    return await scrapper.page_summary()

  @tool
  async def navigate(url: str) -> str:
    """
    Navigates to a new URL.
    Args:
        url: The URL to navigate to.
    Returns:
        A message indicating the result of the navigation.
    """
    return await scrapper.navigate(url)

  return [extract_elements, interact_with_element, print_page, page_summary, navigate]