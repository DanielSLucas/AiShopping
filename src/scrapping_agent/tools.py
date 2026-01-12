import os
from typing import Any, Dict, List
from enum import StrEnum

from scrapping_agent.scrap import ScrapScriptRunner
from scrapping_agent.repository import ScrapScript, ScrapScriptsRepository
from scrapping_agent.disk_repository import DiskScrapScriptsRepository
from scrapping_agent.scrapper import Scrapper
from langchain_core.language_models import BaseChatModel
from langchain_core.tools import tool, BaseTool
from utils.utils import describe_web_page_print, extract_domain
from utils.logger import Logger 

class Tools(StrEnum):
  EXTRACT_ELEMENTS = "extract_elements"
  INTERACT_WITH_ELEMENT = "interact_with_element"
  GET_DOM_TREE = "get_dom_tree"
  GET_URL = "get_url"
  GO_BACK = "go_back"
  NAVIGATE = "navigate"
  PRINT_PAGE = "print_page"  
  EXECUTE_SCRAP_SCRIPT = "execute_scrap_script"
  GET_SCRAP_SCRIPT = "get_scrap_script"
  SAVE_SCRAP_SCRIPT = "save_scrap_script"
  LIST_DOMAIN_SCRIPTS = "list_domain_scripts"

def make_scrapper_tools(scrapper: Scrapper, vision_model: BaseChatModel = None, headless: bool = True, logger: Logger = None) -> dict[Tools, BaseTool]:
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
    Extracts elements matching a selector with detailed attributes.
    Args:
        el_selector: The CSS selector to find elements.
        trunc: Whether to truncate text content (max 100 chars).
        limit: Maximum number of elements to return.
        compact: If true, groups identical selectors and adds a count.
    Returns:
        A JSON array with detailed DOM trees including innerText, ariaLabel, href, src, children, etc.
    """
    return await scrapper.extract_elements(el_selector, trunc, limit, compact)

  @tool
  async def interact_with_element(el_selector: str, interaction: str, text: str = "", is_download: bool = False) -> str:
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

  # Repository instance (using disk storage)
  repo: ScrapScriptsRepository = DiskScrapScriptsRepository()

  @tool
  async def execute_scrap_script(script_id: str, input_values: dict = {}) -> str:
    """
      Executes a scrap script by its ID with the provided input values.
      Args:
        script_id: The unique ID of the script to execute.
        input_values: The input values for the scrap script.
      Returns:
        The extracted data from the scrap script.
    """
    try:
      script = repo.get_by_id(script_id)
      
      if script is None:
        return f"There is no script with ID '{script_id}'"
      
      runner = ScrapScriptRunner(script, input_values, debug=not headless, logger=logger)

      return await runner.run()
    except Exception as e:
      return f"Error running 'execute_scrap_script'. Error: {str(e)}"

  @tool
  async def get_scrap_script(script_id: str) -> dict:
    """
      Gets a scrap script by its ID.
      Args:
        script_id: The unique ID of the script to retrieve.
      Returns:
        The scrap script if it exists, or an error message.
    """
    try:
      script = repo.get_by_id(script_id)
      
      if script is None:
        return f"There is no script with ID '{script_id}'"
      
      return script.to_execution_dict()
    except Exception as e:
      return f"Error running 'get_scrap_script'. Error: {str(e)}"

  @tool
  async def list_domain_scripts(domain: str) -> List[Dict[str, Any]]:
    """
      Lists all available scripts for a domain with their summaries.
      Args:
        domain: The domain to list scripts for (e.g., "amazon.com.br").
      Returns:
        A list of script summaries with id, name, description, and inputs.
    """
    try:
      summaries = repo.get_domain_summaries(domain)
      if not summaries:
        return f"No scripts found for domain '{domain}'"
      return summaries
    except Exception as e:
      return f"Error running 'list_domain_scripts'. Error: {str(e)}"
    
  @tool
  async def save_scrap_script(scrap_script: Dict[str, Any], script_id: str = None) -> str:
    """
      Saves a scrap script. Requires 'name' and 'description' fields.
      If script_id is provided, the existing script will be overwritten.
      Args:
        scrap_script: The scrap script to save with name, description, site, input, and steps.
        script_id: (Optional) The unique ID of the script to overwrite.
      Returns:
        A message indicating the result of the save operation with the script ID.
    """
    try:
      domain = extract_domain(scrap_script.get("site", ""))
      
      if script_id:
        existing = repo.get_by_id(script_id)
        if existing:
          # Update existing script fields
          existing.name = scrap_script.get("name", existing.name)
          existing.description = scrap_script.get("description", existing.description)
          existing.site = scrap_script.get("site", existing.site)
          existing.input_schema = scrap_script.get("input", existing.input_schema)
          existing.steps = scrap_script.get("steps", existing.steps)
          existing.updated_at = datetime.now()
          saved = repo.save(existing)
          return f"Scrap script '{saved.name}' updated successfully (ID: {saved.id})"
        else:
          return f"Error: Script with ID '{script_id}' not found. Cannot overwrite."

      # Create new script
      script = ScrapScript(
        domain=domain,
        name=scrap_script.get("name", "default"),
        description=scrap_script.get("description", f"Script for {domain}"),
        site=scrap_script.get("site", ""),
        input_schema=scrap_script.get("input", {}),
        steps=scrap_script.get("steps", [])
      )
      
      saved = repo.save(script)
      return f"Scrap script '{saved.name}' saved with ID: {saved.id}"
    except Exception as e:
      return f"Error running 'save_scrap_script'. Error: {str(e)}"

  @tool
  async def get_dom_tree(selector: str = "body", limit: int = 50) -> str:
    """
    Returns a simplified DOM tree including page title and description.
    Args:
        selector: The CSS selector to start the tree from (default "body").
        limit: Maximum number of nodes to capture.
    Returns:
        A JSON string with 'title', 'description', and 'tree' keys.
    """
    return await scrapper.get_dom_tree(selector, limit)

  return {
    Tools.EXTRACT_ELEMENTS: extract_elements, 
    Tools.INTERACT_WITH_ELEMENT: interact_with_element,
    Tools.GET_DOM_TREE: get_dom_tree, 
    Tools.NAVIGATE: navigate,
    Tools.GET_URL: get_url,
    Tools.GO_BACK: go_back,
    Tools.PRINT_PAGE: print_page,
    Tools.EXECUTE_SCRAP_SCRIPT: execute_scrap_script,
    Tools.GET_SCRAP_SCRIPT: get_scrap_script,
    Tools.SAVE_SCRAP_SCRIPT: save_scrap_script,
    Tools.LIST_DOMAIN_SCRIPTS: list_domain_scripts
  }
  