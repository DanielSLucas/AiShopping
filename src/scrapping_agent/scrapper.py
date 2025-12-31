import os
from urllib.parse import urlparse
from time import time
import re

from playwright.async_api import async_playwright, Page
from langchain_core.tools import tool

class Scrapper:
  def __init__(self):
    self.__page = None
    self.__browser = None
    self.__playwright = None
    self.__url = None
    self.__initialized = False
  
  async def initialize(self, url: str, headless: bool = True) -> None:
    self.__playwright = await async_playwright().start()
    self.__browser = await self.__playwright.chromium.launch(headless=headless)
    self.__page = await self.__browser.new_page()
    self.__url = url

    self.__page.on("popup", self.__handle_popup())
    self.__page.on("load", lambda p: p.wait_for_load_state())

    await self.navigate(url)
    self.__initialized = True

  def __handle_popup(self):
    async def handle(page: Page):
      await self.__navigate(page.url)
      await page.close()
    return handle

  def __get_page(self) -> Page:
    if not self.has_been_initialized():
      raise RuntimeError("You need to call initialize() before doing any action")
    return self.__page

  async def __navigate(self, url: str):
    await self.__get_page().goto(url)
    await self.__get_page().wait_for_load_state()
  
  def has_been_initialized(self) -> bool:
    return self.__initialized
  
  def get_url(self):
    return self.__get_page().url

  async def getSiteData(self):
    iconUrl = "https://www.google.com/s2/favicons?domain=" + urlparse(self.__url).netloc

    title = await self.__get_page().title()

    return {
      "site": self.__get_page().url,
      "icon": iconUrl,
      "title": title
    }
  
  async def close(self) -> None:
    if self.__browser:
      await self.__browser.close()
    if self.__playwright:
      await self.__playwright.stop()

  async def go_back(self):
    try:
      await self.__get_page().go_back()
      await self.__get_page().wait_for_load_state()
      return "Navigated back to the previous page"
    except Exception as e:
      return f"Error running 'go_back'. Error: {str(e)}"

  async def extract_elements(self, el_selector: str, trunc: bool = True, limit: int = 50, compact: bool = False):
    """
      Extracts elements from the page based on the provided selector.
      Args:
        el_selector (str): The selector to find elements.
        trunc (bool): Whether to truncate the text content. Default is True.
        limit (int): The maximum number of elements to extract. Default is 50.
        compact (bool): Whether to compact identical elements with a count. Default is False.
      Returns:
        str: A formatted string with the extracted elements.
    """
    try:
      elements = await self.__get_page().query_selector_all(el_selector)
      formatted_elements = []
      last_element = {'el': None, 'count': 0}
      
      for el in elements:
        element = await self.__serialize_element(el, trunc)
        
        if compact and self.__isDuplicated(last_element, element):
          updated__last_element = last_element['el'].copy()
          updated__last_element['Count'] = last_element['count']
          formatted_elements[-1] = self.__stringfy_element(updated__last_element)
        else:
          formatted_elements.append(self.__stringfy_element(element))

        if len(formatted_elements) >= limit:
          break
      
      if len(formatted_elements) == 0:
        formatted_elements.append("No elements found")

      return "Extracted elements:\n-" + "\n- ".join(formatted_elements)
    except Exception as e:
      return f"Error running 'extract_elements'. Error: {str(e)}"

  async def __serialize_element(self, el, trunc):
    tag_name = (await el.evaluate('el => el.tagName')).lower()
    
    element = { "Element": tag_name }

    class_name = (await el.evaluate('el => el.className')).strip()
    if class_name:
      element['Classes'] = class_name
    
    text = re.sub(r'\s+', ' ', (await el.text_content()).strip())
    if text:
      formatted_text = text if not trunc else text[:50] + "..." if len(text) > 50 else text
      element['Text'] = formatted_text

    if tag_name == "a":
      element['Href'] = await el.get_attribute("href")

    if tag_name == "input":
      element['Placeholder'] = await el.get_attribute("placeholder") or "no placeholder"
      element['Name'] = await el.get_attribute("name") or "no name"
    
    return element
  
  def __stringfy_element(self, el):
    if isinstance(el, dict):
      return " ".join([f"{key}: {value}" for key, value in el.items()])
    return str(el)
  
  def __isDuplicated(self, last_element, element):
    if last_element['el'] is None:
      last_element['el'] = element
      last_element['count'] = 1
      return False

    if last_element['el']['Element'] == element['Element'] \
      and last_element['el'].get('Classes') == element.get('Classes'):
      last_element['count'] += 1
      return True
        
    last_element['el'] = element
    last_element['count'] = 1
    return False

  async def interact_with_element(self, el_selector: str, interaction: str, text: str, is_download=False):
    """
      Interacts with an element on the page based on the provided selector.
      Args:
        el_selector (str): The selector to find the element.
        interaction (str): The type of interaction to perform (click, fill).
        text (str): The text to fill in the element if applicable.
      Returns:
        str: A message indicating the result of the interaction.
    """
    try:
      element = await self.__get_page().query_selector(el_selector)
      
      if element is None:
        return f"Element with selector '{el_selector}' not found."
      
      if not await element.is_visible():
        return f"Element '{el_selector}' is not visible."

      if interaction == "click":
        download_event = self.__get_page().wait_for_event("download") if is_download else None
        await element.click(timeout=10000)
        if is_download:
          download = await download_event
          path = os.path.join("temp", download.suggested_filename)
          await download.save_as(path)
        return f"Element '{el_selector}' clicked."

      if interaction == "fill":
        await element.type(text, timeout=10000)
        return f"Text '{text}' typed in element '{el_selector}'."
      
      return "Unsupported interaction."
    except Exception as e:
      return f"Error running 'extract_elements'. Error: {str(e)}"
  
  async def print_page(self):
    """
      Takes a screenshot of the current page and saves it to a file.
      Returns:
        str: The file path of the saved screenshot.
    """
    try:
      timestamp = str(round(time()))
      fileName= f"./temp/print_{timestamp}.png"
      await self.__get_page().screenshot(path=fileName, full_page=True)
      return fileName
    except Exception as e:
      return f"Error running 'print_page'. Error: {str(e)}"
  
  async def page_summary(self):
    """
      Summarizes the current page by extracting the URL, title, description, text elements
      and interaction elements.
      Returns:
        str: A formatted string with the page summary.
    """
    try:
      url = self.__get_page().url
      title = await self.__get_page().title()
      description = await self.__get_page().evaluate("() => document.querySelector('meta[name=\"description\"]')?.getAttribute('content') || 'No description available'")
      
      text_elements_tags = "h1, h2, h3, h4, p, li, td, th, label"
      interaction_elements_tags = "a, button, input"

      text_elements = await self.extract_elements(text_elements_tags, True, 1000, True)
      interaction_elements = await self.extract_elements(interaction_elements_tags, True, 1000, True)

      return f"URL: {url}\n" \
        + f"Title: {title}\n" \
        + f"Description: {description}\n" \
        + f"Text elements: \n{text_elements}\n" \
        + f"Interaction elements: \n{interaction_elements}"
    except Exception as e:
      return f"Error running 'page_summary'. Error: {str(e)}"
    
  async def navigate(self, url: str):
    """
      Navigates to a new URL.
      Args:
        url (str): The URL to navigate to.
      Returns:
        str: A message indicating the result of the navigation.
    """
    try:
      await self.__navigate(url)
      return f"Navigated to {url}"
    except Exception as e:
      return f"Error running 'navigate'. Error: {str(e)}"