from firecrawl import FirecrawlApp
from openai import OpenAI
from dotenv import load_dotenv
import os
import json
import pandas as pd
from datetime import datetime

def scrape_date(url):
    load_dotenv()

    app =  FirecrawlApp(api_key=os.getenv('FIRECRAWL_API_KEY'))

    scrape_date = app.scrape_url(url)

    if 'markdown' in scrape_date:
          return scrape_date['markdown']
    else:
         raise KeyError("A chave 'markdown' naoi existe no scraped date.")
    
def save_raw_data(raw_data, timestamp, output_folder ='output'):
     
     os.makedirs(output_folder, exist_ok= True)

     raw_output_path = os.path.join(output_folder, f'rawData_{timestamp}.md')
     with open(raw_output_path, 'w', encoding='utf-8') as f:
            f.write(raw_data)
     print(f"Raw data saved to {raw_output_path}")        

def form_data(data, fields=None): 
    load_dotenv()
    client =OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
    if fields is None:
        fields = ["Endereco","agência imobiliária ", "Preco", "Quartos", "Banheiros", "Área (sqft)", "Tipo de imóvel","Tempo de anúncio","Foto da casa"]

    system_message = f"""
        "Você é um assistente inteligente de extração e conversão de texto. "
        "Sua tarefa é extrair informações estruturadas do texto sobre propriedades imobiliárias. "
        "Explicações ou enumerações não são necessárias. Você deve retornar os dados extraídos em formato JSON puro, "
        "sem nenhuma palavra antes ou depois. Se o texto não tiver alguns campos, faça o seu melhor para preenchê-los "
        "ou deixe-os em branco. Por favor, processe o texto a seguir e forneça a saída em formato JSON puro, "
        "sem palavras antes ou depois."""
    

    # Mensagem enviada como "user"
    user_message = f"Extraia as seguintes informações do conteúdo de texto:\nPage content:\n\n{data}\n\nInformacao extraida:{fields}"



    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_message}
        ],
        
    )

    if response and response.choices:
      formatted_data= response.choices[0].message.content.strip()
      print(f"Formatted data received from API: {formatted_data}")
      
      try:
           parsed_json = json.loads(formatted_data)
      except json.JSONDecodeError as e:
           print(f"JSON decoding error: {e}")  
           print(f"Formatted data tha caused the error: {formatted_data}")
           raise ValueError("The formatted data coud not be decoded into JSON.")
      return parsed_json
    else:
         raise ValueError("The openAI API response did not contai the expected choices data")

def save_formatted_data(formatted_data, timestamp, output_folder='output'):
    # Garante que a pasta de saída exista
    os.makedirs(output_folder, exist_ok=True)

    # Salva os dados formatados como JSON, com o timestamp no nome do arquivo
    output_path = os.path.join(output_folder, f'sorted_data_{timestamp}.json')
    with open(output_path, 'w', encoding='utf-8') as f:
      json.dump(formatted_data, f, indent=4)
    print(f"Formatted data saved to {output_path}")

    # Verifica se os dados são um dicionário e se há apenas uma chave
    if isinstance(formatted_data, dict) and len(formatted_data) == 1:
      key = next(iter(formatted_data))
        # Se houver apenas uma chave, obtém o conteúdo dessa chave
      formatted_data = formatted_data[key]

    # Converte os dados formatados em um DataFrame do pandas
    if isinstance(formatted_data, dict):
      # Se ainda for um dicionário, converte para lista com um item
      formatted_data = [formatted_data]

    df = pd.DataFrame(formatted_data)

    # Salva o DataFrame em um arquivo Excel
    excel_output_path = os.path.join(output_folder, f'sorted_data_{timestamp}.xlsx')
    df.to_excel(excel_output_path, index=False)
    print(f"Formatted data saved to {excel_output_path}")   


if __name__ == "__main__":
   # Exemplos de URLs (descomente a que deseja usar ou adicione a sua)
   url = 'http://www.zillow.com/salt-lake-city-ut/'
    # url = "http://www.culia.com/CA/san-francisco/"
    # url = "http://www.culia.com/amo-lyon-69/"
    # Exemplos de campos (descomente ou ajuste conforme a sua necessidade)
    # fields = ["Model", "Storage Capacity", "Camera Resolution", "Screen Size", "RAM", "Processor"]
   try:
        # Obtém os dados brutos (raw data) a partir da URL
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        raw_data = scrape_date(url)

        # Salva os dados brutos
        save_raw_data(raw_data, timestamp)

        # Formata os dados brutos
        formatted_data = form_data(raw_data)

        # Salva os dados formatados
        save_formatted_data(formatted_data, timestamp)
   except Exception as e:
       print(f"An error occurred: {e}")   