from os import getenv,path
import time
from datetime import datetime
import json

import pandas as pd
import numpy as np
from playwright.sync_api import sync_playwright
from markdownify import markdownify as md
from bs4 import BeautifulSoup
from googleapiclient.discovery import build
from openai import OpenAI
from firecrawl import FirecrawlApp

google_api_key = getenv("GOOGLE_API_KEY")
google_cse_id = getenv("GOOGLE_CSE_ID")

openai_client = OpenAI(api_key=getenv("OPENAI_API_KEY"))
fc_app = FirecrawlApp(api_key="fc-YOUR_API_KEY")

now = datetime.now()

def log(message, display=False):
  # Transformar listas ou dicionários em strings
  if isinstance(message, (list, dict)):
    message = json.dumps(message, ensure_ascii=False)
  elif not isinstance(message, str):
    message = str(message)
      
  log_file = path.join("logs", f"log_{now}.txt")
  with open(log_file, "a", encoding="utf-8") as f:
    f.write(message + "\n")
  if display:
    print(message)

def google_search(query: str, num_results: int):
  service = build("customsearch", "v1", developerKey=google_api_key)

  search_results = (
    service.cse()
    .list(
      q=query, 
      cx=google_cse_id,
      num=num_results,
    )
    .execute()
  ).get('items', [])

  return [
    {
      "title": sr.get("title", ""), 
      "link": sr.get("link", ""),
      "snippet": sr.get("snippet", "")
    } 
    for sr in search_results
  ]
  
def gpt(msgs):  
  response = openai_client.chat.completions.create(
    model="gpt-4o-mini",
    messages=msgs,
    temperature=0.5,
    max_tokens=2000
  )

  return response.choices[0].message.content.strip()

def extract_data(url):
  with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    page = browser.new_page()

    page.goto(url)

    page.wait_for_load_state()

    page_content = page.content()

    if page_content is None: return None

    return page_content
  
def clean_html(html_content):
  soup = BeautifulSoup(html_content, 'html.parser')
        
  for script in soup(["script", "style", "svg", "path", "meta", "link"]):
    script.extract()
  
  return soup.decode()

def text_chunks(text:str, chunk_size: int = 500):
  return [text[i:i+chunk_size] for i in range(0, len(text), chunk_size)]

def get_embedding(text: str, model="text-embedding-3-small"):
  response = openai_client.embeddings.create(
    model=model,
    input=text
  )

  return response.data[0].embedding

def cosine_similarity(vec1, vec2):
  """Computes the cosine similarity between two vectors."""
  vec1 = np.array(vec1)
  vec2 = np.array(vec2)
  return np.dot(vec1, vec2) / (np.linalg.norm(vec1) * np.linalg.norm(vec2))

def main():
  start_time = time.time()
  year = datetime.now().year
  log("### START ###", True)

  # google_results = google_search("Pao de batata", 3)

  full_html = extract_data("https://lista.mercadolivre.com.br/mouse-sem-fio#D[A:mouse%20sem%20fio]")
  cleaned_html = clean_html(full_html)

  chunks = text_chunks(cleaned_html)

  df = pd.DataFrame({ "chunk": chunks })
  df["chunk_embedding"] = df['chunk'].apply(lambda x: get_embedding(x))
  
  query_embedding = get_embedding("<input/><button>search</button>")
  
  df['similarities'] = df["chunk_embedding"].apply(lambda x: cosine_similarity(x, query_embedding))

  res = df.sort_values("similarities", ascending=False).head(2)
  
  print(res)


  return 

  chat = [
    {"role": "developer", "content": f"""
      Você é um assitente de compras online.
     
      O usuário vai lhe enviar uma mensagem dizendo o que deseja comprar.
      '''
      Quero comprar: {{o quê o usuário quer comprar}}
      '''

      - Se o quê o usuário deseja comprar for muito amplo responda:
        '''
        ## SPECIFY ##
        {{Texto claro, conciso e amigável pedindo por informações mais específicas}}
        '''
      - Se o quê o usuário deseja comprar já estiver específico, ou ele já tenho dado informações adicionais responda:
        '''
        ## SEARCH ##
        Melhores {{produto}} para {{propósito}} em {year}
    """},
    {"role": "user", "content": "Quero comprar: Teclados"},
    {"role": "assistant", "content": """
      ## SPECIFY ##
      Que tipo de teclados você deseja? 
      - Sem fio ou com fio?
      - Para jogos, trabalho ou dia a dia?
      - Qual faixa de preço?
    """},
    {"role": "user", "content": "Teclado sem fio, para jogos e trabalho no melhor custo benfício"},
    {"role": "assistant", "content": f"""
      ## SEARCH ##
      Melhores teclados sem fio para jogos e trabalho em {year}
    """},
  ]

  # 1 - input
  log("#1 - Query")
  query = input("O que deseja comprar?")
  chat.append({"role": "user", "content": f"Quero comprar: {query}"})
  log(f"Query: '{query}'")

  # 2 - verificar se escopo está claro
  log("#2 - Enviando pedido para o GPT")
  gpt_response = gpt(chat)
  chat.append({ "role": "assistant", "content": gpt_response })
  log(f"Resposta GPT: '{gpt_response}'")

  # 2.1 - pedir mais informações
  if gpt_response.startswith("## SPECIFY ##"):
    specifications = input(gpt_response.removeprefix("## SPECIFY ##").strip()+"\n")
    chat.append({ "role": "user", "content": f"Especificações: {specifications}"})
  elif not gpt_response.startswith("## SEARCH ##"):
    raise Exception("Algo deu errado na resposta do GPT")
  
  gpt_response = gpt(chat)

  # 3 - Buscar tier lists relacionado ao produto
  log("#3 - Busca google")
  google_query = gpt_response.removeprefix("## SEARCH ##").strip()
  log(f"Google_query: {google_query}")
  google_results = google_search(google_query, 3)
  log(google_results)

  # 3.1 - buscar texto das urls
  log("#4 - Extraindo dados das URLs")
  results_data = "\n".join([
    f"FROM:{google_result['link']}\nDATA:{extract_data(google_result['link'])}"
    for google_result in google_results
  ])
  log(f"Resultados da busca:\n\n{results_data}")
  
  # 3.2 - guardar informações dos produtos mais relevantes
  # 4 - Buscar informações mais detalhadas
  # 5 - comparar produtos
  log("#5 - Montando comparativo")
  msgs = [
    {"role": "developer", "content": """
      Você é um assitente de compras online.
      - Você vai receber o conteúdo de vários rankings diferentes relacionados a determinado tipo de produto
      - Você vai escolher os que mais se repetem e que estejam de acordo com a busca do usuário
      - Você vai fazer um comparativo entre eles afim de ajudar o usuário com sua compra
      - Sua resposta deve estar num formato apropriado para ser exibido no terminal
    """},
    {"role": "user", "content": f"""
      PESQUISA: 
      ```{google_query}```
      RESULTADOS:
      ```
      {results_data}
      ```
    """}
  ]
  result = gpt(msgs)

  # 6 - retonar comparação
  log("### RESULTADO ###", True)
  log(result, True)
    
  end_time = time.time()
  elapsed_time = end_time - start_time
  log(f"Elapsed time: {elapsed_time:.4f} seconds")


if __name__ == "__main__":
  main()
