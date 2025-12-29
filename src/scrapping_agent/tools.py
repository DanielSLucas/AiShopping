import os
from typing import Any, Dict

from scrapping_agent.scrap import ScrapScriptsManager, ScrapScriptRunner
from scrapping_agent.scrapper import Scrapper
from langchain_core.language_models import BaseChatModel
from langchain_core.tools import tool

from utils.utils import describe_web_page_print, extract_domain

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
  async def execute_scrap_script(scrap_script_url: str, input_values: Dict[str, str | int]) -> str:
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
        print(f"There is no script for this url '{scrap_script_url}'")
        return f"There is no script for this url '{scrap_script_url}'"
      
      scrap_script = ssm.get(scrap_script_name)
      scraper = ScrapScriptRunner(scrap_script, input_values)

      result = await scraper.run()
      print(result)
      return result
    except Exception as e:
      print(e)
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

  return [
    extract_elements, 
    interact_with_element,
    page_summary, 
    navigate,
    execute_scrap_script,
    get_scrap_script,
    save_scrap_script,
    print_page
  ]
  