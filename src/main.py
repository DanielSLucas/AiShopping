import asyncio
import time
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


  def sanitize(s: str) -> str:
    if not s:
      return ""
    # Normaliza quebras e remove duplas / múltiplas quebras
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    while "\n\n" in s:
      s = s.replace("\n\n", "\\\\")
    
    return s.strip()

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
          yield "data: [CANCELLED]\n\n"
          return
        
        try:
          if not logger.LOGS_QUEUE.empty():
            msg = logger.LOGS_QUEUE.get_nowait()
            try:
              parsed_msg = json.loads(msg)
              if parsed_msg.get("type") != "DEBUG":
                yield f"data: {sanitize(msg)}\n\n"
                if "[ASK_HUMAN] " in msg or "[RESPONSE] " in msg:
                  break
              continue
            except json.JSONDecodeError:
              yield f"data: {sanitize(msg)}\n\n"
            
            if "[ASK_HUMAN] " in msg or "[RESPONSE] " in msg:
              break
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
          yield f"data: {sanitize(f'Execution time: {end_time - start_time:.2f}s')}\n\n"
          yield f"data: {sanitize(result)}\n\n"
        except asyncio.CancelledError:
          yield "data: [CANCELLED]\n\n"
        except Exception as e:
          yield f"data: {sanitize('Error: ' + str(e))}\n\n"
      
      yield "data: [DONE]\n\n"
      
    except asyncio.CancelledError:
      agent_task.cancel()
      yield "data: [CANCELLED]\n\n"
    except Exception as e:
      agent_task.cancel()
      yield f"data: {sanitize('Error: ' + str(e))}\n\n"

  return StreamingResponse(
    event_stream(), 
    media_type="text/event-stream",
    headers={
      "Cache-Control": "no-cache",
      "Connection": "keep-alive",
      "Access-Control-Allow-Origin": "*"
    }
  )

# @app.post("/chats/{chat_id}")
# async def chat(chat_id: str, request: ChatRequest, http_request: Request):
#   if chat_id not in chats:
#     raise HTTPException(status_code=404, detail="Chat não encontrado")
  
#   chats[chat_id] = request.query

#   async def event_stream():

#     # Caminho do arquivo de log mock
#     file_path = (Path(__file__).resolve().parent.parent / "logs" / "_2025-08-28_20-35-09.json")
    
#     if not file_path.exists():
#       yield f"data: Error: log file not found: {file_path}\n\n"
#       yield "data: [DONE]\n\n"
#       return

#     try:
#       # Leitura linha a linha e envio como SSE
#       with file_path.open("r", encoding="utf-8") as f:
#         for line in f:
#           if await http_request.is_disconnected():
#             yield "data: [CANCELLED]\n\n"
#             return
#           line = line.rstrip("\n")
#             # Ignora linhas vazias
#           if not line.strip():
#             continue
#           yield f"data: {line}\n\n"
#           await asyncio.sleep(0.05)  # pequeno delay para simular streaming
      
#       yield "data: [DONE]\n\n"
#     except Exception as e:
#       yield f"data: Error: {str(e)}\n\n"
#       yield "data: [DONE]\n\n"

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

  if res.startswith("[ASK_HUMAN] "):
    question = res.removeprefix("[ASK_HUMAN] ")
    logger.info(question)
    answer = input("User: ")
    start_time = time.time()
    res = await agent.run(user_input, specifications=answer, recursion_limit=100)

  end_time = time.time()
  logger.info(f"{end_time - start_time:.2f}s")

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
  import uvicorn
  import json
  
  uvicorn.run(app, host="0.0.0.0", port=3000)