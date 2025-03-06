# Sistema de Comparação de Produtos
# Autor: [Seu Nome]
# Data: 25/02/2025

import os
import json
import requests
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from dotenv import load_dotenv
from openai import OpenAI
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Carrega variáveis de ambiente
load_dotenv()

# Inicializa APIs
try:
    # Tenta criar o cliente sem argumentos adicionais
    openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
except TypeError:
    # Versão mais antiga da biblioteca OpenAI pode requerer outra abordagem
    openai_client = OpenAI(
        api_key=os.getenv("OPENAI_API_KEY"), 
        http_client=None  # Não especifica o cliente HTTP diretamente
    )
google_api_key = os.getenv("GOOGLE_API_KEY")
google_cse_id = os.getenv("GOOGLE_CSE_ID")  # ID do Custom Search Engine
firecrawl_api_key = os.getenv("FIRECRAWL_API_KEY")

# Inicializa o aplicativo Flask
app = Flask(__name__)
CORS(app)  # Habilita CORS para o frontend

# Configuração da API do Google Custom Search
def google_search(query, num=5):
    try:
        service = build("customsearch", "v1", developerKey=google_api_key)
        result = service.cse().list(q=query, cx=google_cse_id, num=num).execute()
        return result.get('items', [])
    except HttpError as e:
        print(f"Erro ao realizar a busca no Google: {e}")
        return []

# Configuração da API Firecrawl para extrair conteúdo de websites
def extract_website_content(url):
    try:
        headers = {
            "Authorization": f"Bearer {firecrawl_api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "url": url,
            "limit": 100,  # Pode ser customizado para extrair partes específicas
            "scrapeOptions": {
                "formats": ["markdown"]
            }
        }
        
        response = requests.post(
            "https://api.firecrawl.dev/v1/crawl",
            headers=headers,
            json=payload
        )
        
        if response.status_code == 200:
            result = response.json()
            print(result)
            return result
        else:
            print(f"Erro ao extrair conteúdo: {response.status_code}, {response.text}")
            return {"content": ""}
    except Exception as e:
        print(f"Erro ao acessar a API Firecrawl: {e}")
        return {"content": ""}

# Função para o agente de IA processar as informações
def process_with_ai_agent(user_query, extracted_contents=None, need_more_info=False):
    # Se precisamos de mais informações do usuário
    if need_more_info:
        system_prompt = """
        Você é um assistente de compras especializado. O usuário está procurando 
        um produto, mas preciso de mais detalhes para ajudá-lo melhor. 
        Solicite informações específicas sobre o produto como:
        1. Faixa de preço desejada
        2. Uso principal (pessoal, profissional, gaming, etc.)
        3. Preferências específicas (marca, características, etc.)
        4. Qualquer outra informação relevante para a busca
        """
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"O usuário está procurando: {user_query}. Preciso de mais detalhes para ajudá-lo melhor."}
        ]
        
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            temperature=0.7,
            max_tokens=300
        )
        
        return {
            "status": "need_more_info",
            "message": response.choices[0].message.content
        }
    
    # Processamento normal quando temos informações suficientes
    system_prompt = """
    Você é um especialista em análise e comparação de produtos. 
    Com base nas informações fornecidas sobre produtos encontrados na web,
    sua tarefa é:
    
    1. Identificar os produtos mais recomendados nas tier lists
    2. Analisar as informações técnicas de cada produto
    3. Comparar vantagens e desvantagens
    4. Criar uma comparação detalhada em formato JSON com os seguintes campos:
       - nome: nome do produto
       - preço: faixa de preço estimada (ou preço exato se disponível)
       - características: lista das principais características
       - prós: lista dos pontos positivos
       - contras: lista dos pontos negativos
       - avaliação: nota de 0 a 10
       - recomendado_para: tipo de uso recomendado
       - link: link para onde encontrar o produto
    
    Retorne apenas o JSON com a comparação dos 3-5 melhores produtos.
    """
    
    # Compilar todo o conteúdo extraído
    content_text = ""
    if extracted_contents and len(extracted_contents) > 0:
        for i, content in enumerate(extracted_contents):
            if content and 'content' in content:
                content_text += f"\n--- CONTEÚDO DA PÁGINA {i+1} ---\n{content['content'][:4000]}\n"
    
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Com base na busca por '{user_query}', analise os seguintes conteúdos extraídos de tier lists e reviews:\n{content_text}\n\nCrie uma comparação detalhada dos melhores produtos encontrados."}
    ]
    
    response = openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        temperature=0.5,
        max_tokens=2000
    )
    
    try:
        # Tentar extrair o JSON da resposta
        response_text = response.choices[0].message.content
        # Encontra o início e fim do JSON na resposta
        json_start = response_text.find('{')
        json_end = response_text.rfind('}') + 1
        
        if json_start >= 0 and json_end > json_start:
            json_str = response_text[json_start:json_end]
            comparison_data = json.loads(json_str)
            return {
                "status": "success",
                "data": comparison_data
            }
        else:
            # Se não conseguir extrair o JSON, retorna a resposta em texto
            return {
                "status": "success",
                "data": {"raw_response": response_text}
            }
    except json.JSONDecodeError:
        return {
            "status": "error",
            "message": "Erro ao processar a resposta do agente de IA",
            "raw_response": response.choices[0].message.content
        }

# Rota principal da API
@app.route('/api/search', methods=['POST'])
def search_product():
    data = request.json
    user_query = data.get('query', '')
    additional_info = data.get('additional_info', '')
    
    # Combina a consulta inicial com informações adicionais, se disponíveis
    full_query = user_query
    if additional_info:
        full_query = f"{user_query} {additional_info}"
    
    print("Chamando agente")
    # Primeiro, verificamos se temos informações suficientes
    ai_check = process_with_ai_agent(full_query, need_more_info=True)
    
    # Se precisarmos de mais informações e não temos informações adicionais
    if ai_check.get('status') == 'need_more_info' and not additional_info:
        return jsonify(ai_check)
    
    print("Buscando no google")
    # Se temos informações suficientes, continuamos com a busca
    # 1. Buscar tier lists relacionadas ao produto
    tier_list_results = google_search(f"{full_query} tier list best recommendations reviews", num=3)
    print("Google results")
    print(tier_list_results)

    # 2. Extrair conteúdos das tier lists
    extracted_contents = []
    for result in tier_list_results:
        print("Extraindo conteúdo com firecrawl")
        content = extract_website_content(result['link'])
        print("Conteúdo extraido")
        print(content)
        if content and 'content' in content:
            extracted_contents.append(content)
    
    # 3. Processar com o agente de IA
    comparison_result = process_with_ai_agent(full_query, extracted_contents)
    
    # 4. Buscar informações específicas para os produtos recomendados
    if comparison_result.get('status') == 'success' and isinstance(comparison_result.get('data'), dict):
        products_data = comparison_result.get('data')
        
        # Se products_data for uma lista, processa cada produto
        if 'produtos' in products_data and isinstance(products_data['produtos'], list):
            for product in products_data['produtos']:
                product_name = product.get('nome', '')
                if product_name:
                    # Buscar informações detalhadas do produto
                    product_results = google_search(f"{product_name} specifications review price", num=2)
                    
                    # Extrair conteúdo adicional para o produto
                    for result in product_results:
                        content = extract_website_content(result['link'])
                        if content and 'content' in content:
                            extracted_contents.append(content)
        
        # Processar novamente com todas as informações coletadas
        final_comparison = process_with_ai_agent(full_query, extracted_contents)
        return jsonify(final_comparison)
    
    return jsonify(comparison_result)

# Rota para a interface web
@app.route('/')
def home():
    return render_template('index.html')

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)