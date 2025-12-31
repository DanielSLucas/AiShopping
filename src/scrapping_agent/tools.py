import os
from typing import Any, Dict
from enum import StrEnum

from scrapping_agent.scrap import ScrapScriptsManager, ScrapScriptRunner
from scrapping_agent.scrapper import Scrapper
from langchain_core.language_models import BaseChatModel
from langchain_core.tools import tool, BaseTool

from utils.utils import describe_web_page_print, extract_domain

class Tools(StrEnum):
  EXTRACT_ELEMENTS = "extract_elements"
  INTERACT_WITH_ELEMENT = "interact_with_element"
  PAGE_SUMMARY = "page_summary"
  GET_URL = "get_url"
  GO_BACK = "go_back"
  NAVIGATE = "navigate"
  PRINT_PAGE = "print_page"  
  EXECUTE_SCRAP_SCRIPT = "execute_scrap_script"
  GET_SCRAP_SCRIPT = "get_scrap_script"
  SAVE_SCRAP_SCRIPT = "save_scrap_script"

def make_scrapper_tools(scrapper: Scrapper, vision_model: BaseChatModel = None, headless: bool = True) -> dict[Tools, BaseTool]:
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
  async def interact_with_element(el_selector: str, interaction: str, text: str = "", is_download=False) -> str:
    """
    Interacts with an element on the page based on the provided selector.
    Args:
        el_selector: The selector to find the element.
        interaction: The type of interaction to perform (click, fill).
        text: The text to fill in the element if applicable.
        is_download: Wheather or not the click will start a download to be awaited
    Returns:
        A message indicating the result of the interaction.
    """
    return await scrapper.interact_with_element(el_selector, interaction, text, is_download)

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
  async def go_back() -> str:
    """
    Navigate back to the previous page
    Returns:
      A message confirming the navigation or not
    """
    return await scrapper.go_back()

  @tool
  async def get_url() -> str:
    """
    Get the current url 
    Returns:
      A message with the current url
    """
    return scrapper.get_url()

  @tool
  async def navigate(url: str) -> str:
    """
    Navigates to a new URL.
    Args:
        url: The URL to navigate to.
    Returns:
        A message indicating the result of the navigation.
    """
    if not scrapper.has_been_initialized():
      return await scrapper.initialize(url, headless)

    return await scrapper.navigate(url)

  @tool
  async def execute_scrap_script(scrap_script_url: str, input_values: dict = {}) -> str:
    """
      Executes a scrap script with the provided input values.
      Args:
        scrap_script_url: The URL to be scrapped.
        input_values: The input values for the scrap script.
      Returns:
        The extracted data from the scrap script.
    """
    try:
      ssm = ScrapScriptsManager()
      scrap_script_name = extract_domain(scrap_script_url)
      
      if not ssm.exists(scrap_script_name):
        return f"There is no script for this url '{scrap_script_url}'"
      
      scrap_script = ssm.get(scrap_script_name)
      scraper = ScrapScriptRunner(scrap_script, input_values)

      return await scraper.run()
    except Exception as e:
      return f"Error running 'execute_scrap_script'. Error: {str(e)}"

  @tool
  async def get_scrap_script(scrap_script_url: str) -> dict:
    """
      Gets a scrap script for the given URL and runs it with the provided input values.
      Args:
        scrap_script_url: The URL of the scrap script to run.
      Returns:
        The scrap script if it exists, or an error message.
    """
    try:
      ssm = ScrapScriptsManager()
      scrap_script_name = extract_domain(scrap_script_url)
      
      if not ssm.exists(scrap_script_name):
        return f"There is no script for this url '{scrap_script_url}'"
      
      scrap_script = ssm.get(scrap_script_name)

      return scrap_script
    except Exception as e:
      return f"Error running 'execute_scrap_script'. Error: {str(e)}"
    
  @tool
  async def save_scrap_script(scrap_script: Dict[str, Any]) -> str:
    """
      Saves a scrap script.
      Args:
        scrap_script: The scrap script to save.
      Returns:
        A message indicating the result of the save operation.
    """
    try:
      ssm = ScrapScriptsManager()
      script_name = extract_domain(scrap_script["site"])
      ssm.save(script_name, scrap_script)
      return f"Scrap script '{script_name}' saved."
    except Exception as e:
      return f"Error running 'save_scrap_script'. Error: {str(e)}"

  return {
    Tools.EXTRACT_ELEMENTS: extract_elements, 
    Tools.INTERACT_WITH_ELEMENT: interact_with_element,
    Tools.PAGE_SUMMARY: page_summary, 
    Tools.NAVIGATE: navigate,
    Tools.GET_URL: get_url,
    Tools.GO_BACK: go_back,
    Tools.PRINT_PAGE: print_page,
    Tools.EXECUTE_SCRAP_SCRIPT: execute_scrap_script,
    Tools.GET_SCRAP_SCRIPT: get_scrap_script,
    Tools.SAVE_SCRAP_SCRIPT: save_scrap_script
  }
  