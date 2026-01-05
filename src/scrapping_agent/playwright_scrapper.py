import os
import re
from urllib.parse import urlparse
from asyncio import sleep
from typing import Dict, List, NotRequired, TypedDict

from playwright.async_api import async_playwright, ElementHandle, Page

class PlaywrightScrapperActionOptions(TypedDict):
  parent_selector: NotRequired[str]
  parent_index: NotRequired[int]

class PlaywrightScrapper:
  def __init__(self):
    self.page = None
    self.broser = None
    self.playwright = None
    self.url = None
  
  async def initialize(self, url: str, debug: bool = True, timeout = 10000) -> None:
    self.playwright = await async_playwright().start()
    self.browser = await self.playwright.chromium.launch(headless=not debug,)
    self.page = await self.browser.new_page()
    self.page.set_default_timeout(timeout)
    
    self.timeout = timeout
    self.url = url
    self.debug = debug
    
    self.page.on("popup", self.__handle_popup())
    self.page.on("load", lambda p: p.wait_for_load_state())

    await self.navigate(url)

  def __handle_popup(self):
    async def handle(page: Page):
      await self.navigate(page.url)
      await page.close()
    return handle

  async def close(self) -> None:
    if self.browser:
      await self.browser.close()
    if self.playwright:
      await self.playwright.stop()

  async def navigate(self, url: str) -> None:
    await self.page.goto(url)
    await self.page.wait_for_load_state()

  async def go_back(self) -> None:
    await self.page.go_back()
    await self.page.wait_for_load_state()

  async def getSiteData(self):
    iconUrl = "https://www.google.com/s2/favicons?domain=" + urlparse(self.url).netloc

    title = await self.page.title()

    return {
      "site": self.url,
      "icon": iconUrl,
      "title": title
    }

  async def fill(self, selector: str, input_text: str = "", options: PlaywrightScrapperActionOptions = {}) -> None:
    el: ElementHandle = await self.__get_element(selector, options=options)
    await el.fill(input_text)
  
  async def click(self, selector: str, is_download=False, options: PlaywrightScrapperActionOptions = {}) -> None:
    el = await self.__get_element(selector, options=options)
    download_event = self.page.wait_for_event("download") if is_download else None

    await el.click(force=True)

    if is_download:
      download = await download_event
      path = os.path.join("temp", download.suggested_filename)
      await download.save_as(path)

  async def wait_selector(self, selector: str, timeout = None) -> None:
    await self.page.wait_for_selector(selector, timeout=(timeout or self.timeout))

  async def extract(self, selector: str, prop_label_dict: Dict[str, str], options: PlaywrightScrapperActionOptions = {}) -> Dict[str, str]:
    try:
      el = await self.__get_element(selector, options=options)
      result = {}
      for prop, label in prop_label_dict.items():
        prop_value = await el.evaluate(f"el => el.{prop}")
        prop_value = re.sub(r"[\s\t\n]+", " ", prop_value).strip() if prop_value else "None"
        result[label] = prop_value
      return result
    except Exception as e:
      self.logger.debug(f"Element not found for extraction: {selector}. Returning None labels.")
      return {label: "None" for label in prop_label_dict.values()}

  async def __get_element(self, selector: str, all=False, options: PlaywrightScrapperActionOptions = {}) -> ElementHandle | List[ElementHandle]:
    elements = await self.page.query_selector_all(options.get("parent_selector") if options.get("parent_selector") else selector)

    if len(elements) != 0 and options.get("parent_selector"):
      elements = await elements[options.get("parent_index", 0)].query_selector_all(selector)

    if len(elements) == 0:
      raise Exception(f"No elements with selector '{selector}' were found")

    if (self.debug):
      await self.__highlight(elements, 1000)

    el = elements if all else elements[0]

    return el

  async def __highlight(self, elements:List[ElementHandle], duration_ms=500):
    for el in elements:
      await el.hover()
      await el.evaluate("""el => {
        el._originalBorder = el.style.border; 
        el.style.border = '3px solid red';
      }""")
    
    await sleep(duration_ms / 1000)
    
    for el in elements:
      await el.evaluate("el => el.style.border = el._originalBorder")


  