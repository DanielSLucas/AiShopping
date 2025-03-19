from time import time
import asyncio
import re

from playwright.async_api import async_playwright

class Scrapper:
  def __init__(self):
    self.page = None
    self.broser = None
    self.playwright = None
    self.commands = {
      "extract_elements": self._handle_extract_elements,
      "interact_with_element": self._handle_interact_with_element,
      "print": self._handle_print,
      "end": self._handle_end
    }
  
  async def initialize(self, url: str, headless: bool = True) -> None:
    self.playwright = await async_playwright().start()
    self.browser = await self.playwright.chromium.launch(headless=headless)
    self.page = await self.browser.new_page()
    await self.page.goto(url)
    await self.page.wait_for_load_state()
  
  async def close(self) -> None:
    if self.browser:
      await self.browser.close()
    if self.playwright:
      await self.playwright.stop()

  def run(self, command: str) -> str:
    loop = asyncio.get_event_loop()
    return loop.run_until_complete(self._async_run(command))

  async def _async_run(self, command: str) -> str:
    try:
      cmd, args = self._extract_command_and_args(command)

      command_handler = self.commands.get(cmd, self._handle_command_not_found)

      return await command_handler(args)
    except Exception as e:
      return f"Error running command '{command}'. Erro: {str(e)}"
  
  def _extract_command_and_args(self, command: str):
    pattern = r"([a-z_]+)\(('.*',?)*\)"
    match = re.search(pattern, command.strip())

    if match is None:
      raise Exception("No function match")

    name = match.group(1).strip()
    args = [arg.strip() for arg in match.group(2).strip().replace("'", "").split(",")] if match.group(2) else []

    return name, args
  
  async def _handle_command_not_found(self, _: list[str]):
    return "Command not found"

  async def _handle_extract_elements(self, args: list[str]):
    selector = args[0]
    trunc = False if args[1] == 'False' else True
    limit = int(args[2]) if len(args) == 3 else 10
    return await self._extract_elements(selector, trunc, limit)

  async def _extract_elements(self, el_selector: str, trunc:bool, limit: int):
    elements = await self.page.query_selector_all(el_selector)
    formatted_elements = []
    
    for el in elements:
      tag_name = (await el.evaluate('el => el.tagName')).lower()
      element = f"Element: {tag_name}"
      class_name = (await el.evaluate('el => el.className')).strip()
      text = re.sub(r'\s+', ' ', (await el.text_content()).strip())

      if class_name:
        element += f" Classes: {class_name}"

      if text:
        formatted_text = text if not trunc else text[:50] + "..." if len(text) > 50 else text
        element += f" Text: {formatted_text}"

      if tag_name == "a":
        element += f" Href: {await el.get_attribute('href')}"

      if tag_name == "input":
        placeholder = await el.get_attribute("placeholder") or "no placeholder"
        element += f" Name: {await el.get_attribute('name')} Placeholder: {placeholder}"
        
      formatted_elements.append(element)

      if len(formatted_elements) >= limit:
        break
    
    if len(formatted_elements) == 0:
      formatted_elements.append("No elements found")

    return "Extracted elements:\n" + "\n- ".join(formatted_elements)

  async def _handle_interact_with_element(self, args: list[str]):
    selector = args[0] 
    interaction = args[1]
    text = args[2] if len(args) == 3 else ""
    return await self._interact_with_element(selector, interaction, text)
  
  async def _interact_with_element(self, el_selector: str, interaction: str, text: str):
    element = await self.page.query_selector(el_selector)
    
    if element is None:
      return f"Element with selector '{el_selector}' not found."

    if interaction == "click":
      await element.click()
      return f"Element '{el_selector}' clicked."

    if interaction == "fill":
      await element.type(text)
      return f"Text '{text}' typed in element '{el_selector}'."
    
    return "Unsupported interaction."

  async def _handle_end(self, args: list[str]):
    return "END"
  
  async def _handle_print(self, args: list[str]):
    return await self._print()
  
  async def _print(self):
    timestamp = str(round(time()))
    fileName= f"./temp/print_{timestamp}.png"
    await self.page.screenshot(path=fileName, full_page=True)
    return f"PRINT: {fileName}"