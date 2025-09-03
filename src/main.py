import uvicorn
import asyncio
import time
import json
import os
from uuid import uuid4
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from dotenv import load_dotenv
load_dotenv()

from langchain_openai import ChatOpenAI

from scrapping_agent.agent import ScrappingAgent
from shopping_agent.agent import ShoppingAgent
from utils.logger import Logger

app = FastAPI()

app.add_middleware(
  CORSMiddleware,
  allow_origins=["*"],
  allow_credentials=True,
  allow_methods=["*"],
  allow_headers=["*"],
)
chats = {}

class ChatRequest(BaseModel):
  query: str
  specifications: str = ""

@app.post("/chats")
async def create_chat():
  chat_id = str(uuid4())
  chats[chat_id] = ""
  return {"id": chat_id}

@app.get("/chats")
async def get_chats():
  return chats

@app.post("/chats/{chat_id}")
async def chat(chat_id: str, request: ChatRequest, http_request: Request):
  if chat_id not in chats:
    raise HTTPException(status_code=404, detail="Chat não encontrado")
  
  chats[chat_id] = request.query

  async def event_stream():
    start_time = time.time()
    
    llm = ChatOpenAI(model="gpt-4.1-mini")
    logger = Logger(show_debug_logs=True, logger_id=chat_id)
    agent = ShoppingAgent(llm, logger)
    
    agent_task = asyncio.create_task(
      agent.run(request.query, specifications=request.specifications, recursion_limit=100)
    )
    
    try:
      while not agent_task.done():
        if await http_request.is_disconnected():
          agent_task.cancel()
          yield f"data: " + json.dumps({"type": "CANCELLED", "content": ""}) + "\n\n"
          return
        
        try:
          if not logger.LOGS_QUEUE.empty():
            msg = logger.LOGS_QUEUE.get_nowait()
            try:
              parsed_msg = json.loads(msg)
              if parsed_msg.get("type") != "DEBUG":
                yield f"data: {msg}\n\n"
            except json.JSONDecodeError:
              yield f"data: {msg}\n\n"
          else:
            await asyncio.sleep(0.1)
        except Exception:
            if await http_request.is_disconnected():
              agent_task.cancel()
              return
            await asyncio.sleep(0.1)

      if not agent_task.cancelled():
        try:
          result = await agent_task
          end_time = time.time()
          yield "data: " + json.dumps(result) + "\n\n"
          yield "data: " + json.dumps({"type": "END_TIME", "content": end_time - start_time}) + "\n\n"
        except asyncio.CancelledError:
          yield f"data: " + json.dumps({"type": "CANCELLED", "content": ""}) + "\n\n"
        except Exception as e:
          yield f"data: " + json.dumps({"type": "ERROR", "content": str(e)}) + "\n\n"
      
      yield f"data: " + json.dumps({"type": "END", "content": ""}) + "\n\n"
      
    except asyncio.CancelledError:
      agent_task.cancel()
      yield f"data: " + json.dumps({"type": "CANCELLED", "content": ""}) + "\n\n"
    except Exception as e:
      agent_task.cancel()
      yield f"data: " + json.dumps({"type": "ERROR", "content": str(e)}) + "\n\n"

  return StreamingResponse(
    event_stream(), 
    media_type="text/event-stream",
    headers={
      "Cache-Control": "no-cache",
      "Connection": "keep-alive",
      "Access-Control-Allow-Origin": "*"
    }
  )

# @app.post("/chats/mock")
# async def chat_mock(request: ChatRequest, http_request: Request):
#   """Simula o chat usando arquivos de log pré-gravados"""
  
#   # Seleciona o arquivo de log baseado nas specifications
#   if request.specifications:
#     log_file = "./logs/_2025-09-02_18-37-38.json"
#   else:
#     log_file = "./logs/_2025-09-02_18-37-38_2.json"
  
#   # Verifica se o arquivo existe
#   if not os.path.exists(log_file):
#     raise HTTPException(status_code=404, detail=f"Arquivo de log não encontrado: {log_file}")

#   async def event_stream():
#     try:
#       with open(log_file, 'r', encoding='utf-8') as f:
#         for line in f:
#           if await http_request.is_disconnected():
#             yield f"data: " + json.dumps({"type": "CANCELLED", "content": ""}) + "\n\n"
#             return
          
#           try:
#             # Parse da linha do log
#             log_entry = json.loads(line.strip())
            
#             # Filtra apenas logs que não são DEBUG (como na rota original)
#             if log_entry.get("type") != "DEBUG":
#               yield f"data: {json.dumps(log_entry)}\n\n"
            
#             # Adiciona um pequeno delay para simular o processamento real
#             await asyncio.sleep(0.5)
            
#           except json.JSONDecodeError:
#             # Se não conseguir fazer parse do JSON, pula a linha
#             continue
#           except Exception as e:
#             if await http_request.is_disconnected():
#               return
#             continue
      
#       # Sinaliza o fim do stream
#       yield f"data: " + json.dumps({"type": "END", "content": ""}) + "\n\n"
      
#     except asyncio.CancelledError:
#       yield f"data: " + json.dumps({"type": "CANCELLED", "content": ""}) + "\n\n"
#     except Exception as e:
#       yield f"data: " + json.dumps({"type": "ERROR", "content": str(e)}) + "\n\n"

#   return StreamingResponse(
#     event_stream(), 
#     media_type="text/event-stream",
#     headers={
#       "Cache-Control": "no-cache",
#       "Connection": "keep-alive",
#       "Access-Control-Allow-Origin": "*"
#     }
#   )


# ------

def log_listener(msg: str):
  print(msg)

async def run_shopping_agent_cli():
  start_time = time.time()
  llm = ChatOpenAI(model="gpt-4.1-mini")
  logger = Logger(show_debug_logs=True, logger_id=str(uuid4()))
  logger.LOGS_QUEUE.put = log_listener
  agent = ShoppingAgent(llm, logger)

  user_input = input("O que deseja comprar? ")

  res = await agent.run(user_input, recursion_limit=100)

  if res["type"] == "ASK_HUMAN":
    question = res["content"]
    logger.info(res)
    answer = input(f"{question}\n\nUser: ")
    start_time = time.time()
    res = await agent.run(user_input, specifications=answer, recursion_limit=100)

  logger.info(res)
  end_time = time.time()
  logger.info({"type": "END_TIME", "content": f"{end_time - start_time:.2f}s"})

async def run_scrapping_agent():
  """Main function to execute the web navigation agent."""
  llm = ChatOpenAI(model="o4-mini")
  logger = Logger(file_name="ml",show_debug_logs=True)
  logger.LOGS_QUEUE.put = log_listener

  agent = ScrappingAgent(llm, debug=True, logger=logger)
  # await agent.initialize("https://www.mercadolivre.com.br", headless=False)
  # await agent.initialize("https://www.amazon.com.br", headless=False)
  await agent.initialize("https://books.toscrape.com", headless=False)
      
  # result = await agent.run("Quero comprar: Teclado gamer, sem fio ", all_results=False)
  result = await agent.run("Quero comprar: todos os livros de ficção cientifica", all_results=True)

  await agent.close()
  print(result)


if __name__ == "__main__":
  # asyncio.run(run_shopping_agent_cli())
  uvicorn.run(app, host="0.0.0.0", port=3000)