import time
import re

import ollama
from playwright.sync_api import sync_playwright


def format_product(product: str):
  response = ollama.chat(
    model="deepseek-r1",
    messages=[
      { 
        "role":  "system",
        "content": """
          You will receive web scrapped text of a product and your goal is to 
          extract its data and format it this way: name,price,rating and number of ratings.
          - Answer just with text SEPARETED BY COMMAS
          - If the receive input does not look like a product just answer: NOT A PRODUCT
        """
      },
      {
        "role": "user",
        "content": product
      }
    ]
  )

  return response['message']['content'].strip()

def format_p(p: str):
  if "R$" not in p or not p: 
    return None
  
  # Obter o nome do produto
  name_pattern = r"(?:.*\n)?(.*?)(?:\nPor)"
  name_match = re.search(name_pattern, p)
  name = name_match.group(1).strip() if name_match else None
  
  # Obter a avaliação e número de avaliações
  rating_pattern = r"(\d+\.\d+)\n\((\d+)\)"
  rating_match = re.search(rating_pattern, p)
  rate = rating_match.group(1) if rating_match else None
  ratings_num = rating_match.group(2) if rating_match else None
  
  # Obter o preço
  price_pattern = r"R\$\n(\d+)\n,\n(\d+)"
  price_match = re.search(price_pattern, p)
  price = f"{price_match.group(1)}.{price_match.group(2)}" if price_match else None
  
  return f"{name},{price},{rate},{ratings_num}"
  

def main():
  start_time = time.time() 
  with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()

    page.goto("https://www.mercadolivre.com.br")

    page.wait_for_load_state()

    page.screenshot(path="test.png")

    # search_input = page.query_selector("input")
    # search_input.type("Mouses sem fio")

    # search_button = page.query_selector("button[type=submit]")
    # search_button.click()

    # page.wait_for_load_state()

    # products = page.query_selector_all("main section ol li")
    # formated_products = []

    # for i in range(len(products)):
    #   p = products[i]
    #   p_text = format_p(p.inner_text())
    #   p_link = p.evaluate(f"document.querySelector(\"main section ol li:nth-child({i+1}) a\").href")
    #   if p is not None: formated_products.append(f"#{i+1},{p_text},{p_link}")

    # f =open("output.txt", "w")
    # f.write("\n\n".join(formated_products))
    # f.close()

    browser.close()
    
  end_time = time.time()
  elapsed_time = end_time - start_time
  print(f"Elapsed time: {elapsed_time:.4f} seconds")


if __name__ == "__main__":
  main()
