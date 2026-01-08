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
  
  async def initialize(self, url: str, headless: bool = True) -> str:
    self.__playwright = await async_playwright().start()
    self.__browser = await self.__playwright.chromium.launch(headless=headless)
    self.__page = await self.__browser.new_page()
    self.__url = url

    self.__page.on("popup", self.__handle_popup())
    self.__page.on("load", lambda p: p.wait_for_load_state())

    self.__initialized = True
    return await self.navigate(url)

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
      Returns a JSON list with detailed DOM trees including attributes.
      Args:
        el_selector (str): The selector to find elements.
        trunc (bool): Whether to truncate text content (max 100 chars). Default is True.
        limit (int): The maximum number of elements to extract. Default is 50.
        compact (bool): If true, groups identical elements and adds a count.
      Returns:
        str: A JSON string with an array of detailed DOM trees.
    """
    try:
      js_script = """
      (args) => {
        const [selector, truncate, maxElements, compactMode] = args;
        const elements = document.querySelectorAll(selector);
        if (elements.length === 0) return JSON.stringify([]);

        function getAttributes(node) {
          const attrs = {};
          const tagName = node.tagName.toLowerCase();
          
          // innerText (direct text, not children's text)
          let directText = '';
          for (let child of node.childNodes) {
            if (child.nodeType === Node.TEXT_NODE) {
              directText += child.textContent;
            }
          }
          directText = directText.replace(/[\\s\\t\\n]+/g, ' ').trim();
          if (directText) {
            attrs.innerText = truncate && directText.length > 100 
              ? directText.substring(0, 100) + '...' 
              : directText;
          }
          
          // Common important attributes
          const ariaLabel = node.getAttribute('aria-label');
          if (ariaLabel) attrs.ariaLabel = ariaLabel;
          
          const title = node.getAttribute('title');
          if (title) attrs.title = title;
          
          const role = node.getAttribute('role');
          if (role) attrs.role = role;
          
          const dataTestId = node.getAttribute('data-testid') || node.getAttribute('data-test-id');
          if (dataTestId) attrs.dataTestId = dataTestId;
          
          // Tag-specific attributes
          if (tagName === 'a') {
            attrs.href = node.getAttribute('href') || '';
          }
          if (tagName === 'img') {
            attrs.src = node.getAttribute('src') || '';
            attrs.alt = node.getAttribute('alt') || '';
          }
          if (tagName === 'input' || tagName === 'textarea') {
            attrs.name = node.getAttribute('name') || '';
            attrs.placeholder = node.getAttribute('placeholder') || '';
            attrs.type = node.getAttribute('type') || '';
            attrs.value = node.value || '';
          }
          if (tagName === 'button' || tagName === 'input') {
            attrs.disabled = node.disabled || false;
          }
          
          return attrs;
        }

        function traverse(node, depth) {
          if (depth > 10) return { "...": {} };
          
          if (node.nodeType !== Node.ELEMENT_NODE) return null;
          
          const style = window.getComputedStyle(node);
          if (style.display === 'none' || style.visibility === 'hidden') return null;

          const tagName = node.tagName.toLowerCase();
          const id = node.id ? '#' + node.id : '';
          let className = node.classList.length > 0 ? '.' + [...node.classList].join('.') : '';
          let selectorStr = tagName + id + className;
          
          const attrs = getAttributes(node);
          
          // Collect children
          let children = [];
          for (let child of node.childNodes) {
            if (child.nodeType === Node.ELEMENT_NODE) {
              const res = traverse(child, depth + 1);
              if (res) children.push(res);
            }
          }
          
          if (children.length > 0) {
            attrs.children = children;
          }
          
          return { [selectorStr]: attrs };
        }

        const results = [];
        const seen = new Map(); // For compact mode deduplication
        
        for (let i = 0; i < Math.min(elements.length, maxElements); i++) {
          const tree = traverse(elements[i], 0);
          if (!tree) continue;
          
          if (compactMode) {
            const key = Object.keys(tree)[0]; // selector string
            if (seen.has(key)) {
              seen.get(key).count++;
            } else {
              tree[key].count = 1;
              seen.set(key, tree[key]);
              results.push(tree);
            }
          } else {
            results.push(tree);
          }
        }
        
        return JSON.stringify(results);
      }
      """
      return await self.__get_page().evaluate(js_script, [el_selector, trunc, limit, compact])
    except Exception as e:
      return f"Error running 'extract_elements'. Error: {str(e)}"

  # Removed __serialize_element, __stringfy_element, __isDuplicated (extract_elements now uses JS)

  async def interact_with_element(self, el_selector: str, interaction: str, text: str, is_download: bool = False):
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
  
  # page_summary method removed in favor of get_dom_tree
    
  async def get_dom_tree(self, selector: str = "body", limit: int = 50):
    """
      Returns a simplified DOM tree of the page, including title and description.
      Args:
        selector (str): The selector to start the tree from.
        limit (int): The maximum number of nodes to capture.
      Returns:
        str: A JSON string with 'title', 'description', and 'tree'.
    """
    try:
      js_script = """
      (args) => {
        const [rootSelector, limit] = args;
        const root = document.querySelector(rootSelector);
        if (!root) return JSON.stringify({ error: "Element not found" });

        const title = document.title || '';
        const descMeta = document.querySelector('meta[name="description"]');
        const description = descMeta ? descMeta.getAttribute('content') : '';

        const importantTags = new Set(['H1','H2','H3','H4','H5','H6','P','A','BUTTON','INPUT','UL','OL','LI','TABLE','THEAD','TBODY','TR','TH','TD','FORM','IMG','DIV','SPAN']);
        
        let counter = 0;
        
        function traverse(node, depth) {
          if (counter >= limit) return null;
          if (depth > 20) return "...";
          
          if (node.nodeType === Node.TEXT_NODE) {
            const text = node.textContent.replace(/[\\s\\t\\n]+/g, ' ').trim();
            if (text.length > 0) return text.length > 80 ? text.substring(0, 80) + '...' : text;
            return null;
          }
          
          if (node.nodeType !== Node.ELEMENT_NODE) return null;
          
          const style = window.getComputedStyle(node);
          if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return null;

          const tagName = node.tagName;
          const id = node.id ? '#' + node.id : '';
          let className = (node.classList && node.classList.length > 0) ? '.' + [...node.classList].join('.') : '';
          const fullSelector = (tagName + id + className).toLowerCase();
          
          let children = [];
          for (let child of node.childNodes) {
             const childResult = traverse(child, depth + 1);
             if (childResult) children.push(childResult);
          }
          
          if (!importantTags.has(tagName) && id === '' && className === '' && children.length <= 1) {
             return children.length === 1 ? children[0] : null;
          }

          if (children.length === 0 && !importantTags.has(tagName)) return null;
          
          if (children.length > 0 && children.every(c => typeof c === 'string')) {
             const joined = children.join(' ').trim();
             if (joined.length === 0) return null;
             if (!importantTags.has(tagName) && id === '' && className === '') return joined;
          }

          counter++;
          
          let output = fullSelector;
          if (tagName === 'A') output += ` [href="${node.getAttribute('href')}"]`;
          if (tagName === 'INPUT') output += ` [name="${node.getAttribute('name')}"][placeholder="${node.getAttribute('placeholder')}"]`;
          if (tagName === 'IMG') output += ` [alt="${node.getAttribute('alt')}"]`;
          
          if (children.length > 0) {
             return { [output]: children };
          } else {
             return output;
          }
        }

        const tree = traverse(root, 0);
        return JSON.stringify({ title, description, tree });
      }
      """
      return await self.__get_page().evaluate(js_script, [selector, limit])
    except Exception as e:
      return f"Error running 'get_dom_tree'. Error: {str(e)}"
    
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