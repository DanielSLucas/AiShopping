import os
from urllib.parse import urlparse
from typing import Any, Dict

from scrapping_agent.scrap import ScrapScriptRunner, ScrapScriptsManager
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

  @tool
  async def end_navigation() -> str:
    """
    Ends the navigation and closes the browser.
    Returns:
        A message indicating the end of the navigation.
    """
    return "Ending the navigation."
  
  @tool
  async def execute_scrap_script(scrap_script: Dict[str, Any], input_values: Dict[str, str | int]) -> str:
    """
      Executes a scrap script with the provided input values.
      Args:
        scrap_script: The scrap script to execute.
        input_values: The input values for the scrap script.
      Returns:
        The extracted data from the scrap script.
    """
    try:
      scraper = ScrapScriptRunner(scrap_script, input_values)
      return await scraper.run()
    except Exception as e:
      print(e)
      return f"Error running 'execute_scrap_script'. Error: {str(e)}"
    
  @tool
  async def save_scrap_script(scrap_script: Dict[str, Any], url: str) -> str:
    """
      Saves a scrap script with the provided name.
      Args:
        scrap_script: The scrap script to save.
        url: The url of the site.
      Returns:
        A message indicating the result of the save operation.
    """
    try:
      ssm = ScrapScriptsManager()
      script_name = urlparse(url).netloc
      ssm.save(script_name, scrap_script)
      return f"Scrap script '{script_name}' saved."
    except Exception as e:
      return f"Error running 'save_scrap_script'. Error: {str(e)}"

  return [
    extract_elements, 
    interact_with_element, 
    print_page, 
    page_summary, 
    navigate, 
    end_navigation,
    execute_scrap_script,
    save_scrap_script
  ]
  