import asyncio
import time
import json
import os
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from langchain_openai import ChatOpenAI

from shopping_agent.agent import ShoppingAgent
from utils.logger import Logger
from utils.utils import make_log_event, make_sse_data
from fastapi.staticfiles import StaticFiles

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

@app.post("/api/chats")
async def create_chat():
  chat_id = str(uuid4())
  chats[chat_id] = ""
  return {"id": chat_id}

@app.get("/api/chats")
async def get_chats():
  return chats

@app.get("/api/chats/{chat_id}")
async def get_chat(chat_id: str):
  """Busca um chat por ID no arquivo de log correspondente"""
  log_file_path = f"./logs/{chat_id}.json"
  
  if not os.path.exists(log_file_path):
    raise HTTPException(status_code=404, detail="Chat não encontrado")
  
  messages = []
  chat_name = chats.get(chat_id, "")
  
  try:
    with open(log_file_path, 'r', encoding='utf-8') as f:
      for line in f:
        try:
          log_entry = json.loads(line.strip())
          if log_entry.get("type") != "DEBUG":
            messages.append(log_entry.get("content", {}))
        except json.JSONDecodeError:
          continue
    
    return {
      "id": chat_id,
      "name": chat_name,
      "messages": messages
    }
    
  except Exception as e:
    raise HTTPException(status_code=500, detail=f"Erro ao ler arquivo de log: {str(e)}")

@app.post("/api/chats/{chat_id}")
async def chat(chat_id: str, request: ChatRequest, http_request: Request):
  if chat_id not in chats:
    raise HTTPException(status_code=404, detail="Chat não encontrado")
  
  chats[chat_id] = request.query

  async def event_stream():
    start_time = time.time()
    
    llm = ChatOpenAI(model="gpt-4.1-mini")
    logger = Logger(show_debug_logs=True, logger_id=chat_id)
    agent = ShoppingAgent(llm, logger)
    
    if request.specifications:
      logger.info(make_log_event(type="USER", content=request.specifications))
    else:
      logger.info(make_log_event(type="USER", content=request.query))

    agent_task = asyncio.create_task(
      agent.run(request.query, specifications=request.specifications, recursion_limit=100)
    )
    
    try:
      while not agent_task.done():
        if await http_request.is_disconnected():
          agent_task.cancel()
          yield make_sse_data(make_log_event(type="CANCELLED"))
          return
        
        try:
          if not logger.LOGS_QUEUE.empty():
            msg = logger.LOGS_QUEUE.get_nowait()
            try:
              parsed_msg = json.loads(msg)
              if parsed_msg.get("type") != "DEBUG":
                parsed_msg["content"]["id"] = str(uuid4())
                yield make_sse_data(parsed_msg["content"])
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
          result["id"] = str(uuid4())
          logger.info(result)
          end_time = time.time()
          yield make_sse_data(result)
          yield make_sse_data(make_log_event(type="END_TIME", content=end_time - start_time))
        except asyncio.CancelledError:
          yield make_sse_data(make_log_event(type="CANCELLED"))
        except Exception as e:
          yield make_sse_data(make_log_event(type="ERROR", content=str(e)))
      
      yield make_sse_data(make_log_event(type="END"))
      
    except asyncio.CancelledError:
      agent_task.cancel()
      yield make_sse_data(make_log_event(type="CANCELLED"))
    except Exception as e:
      agent_task.cancel()
      yield make_sse_data(make_log_event(type="ERROR", content=str(e)))

  return StreamingResponse(
    event_stream(), 
    media_type="text/event-stream",
    headers={
      "Cache-Control": "no-cache",
      "Connection": "keep-alive",
      "Access-Control-Allow-Origin": "*"
    }
  )

app.mount("/", StaticFiles(directory="public"), name="public")