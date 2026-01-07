import base64
from uuid import uuid4
import json

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage, AIMessage, ToolMessage, HumanMessage
from langgraph.types import Command
import tldextract

def get_prompt(prompt_file_path: str):
  with open(prompt_file_path, "r") as f:
    return f.read()

def encode_image(image_path: str) -> str:
  """Encode image to base64 string"""
  with open(image_path, "rb") as image_file:
    return base64.b64encode(image_file.read()).decode("utf-8")  
  
def describe_web_page_print(vision_llm: BaseChatModel, fileName: str) -> str:
  try:
    encoded_print = encode_image(fileName)

    message = HumanMessage(
      content=[
        {
          "type": "text", 
          "text": "Provide a comprehensive and detailed description of this webpage screenshot.\n\nProvide a structured response with sections and bullet points about the page title and purpose, main navigation elments, primary content, interactive elements, current state, possible actions, page structure, unique identifiers.\n\nScreenshot analysis:\n"
        },
        {
          "type": "image_url",
          "image_url": {
            "url": f"data:image/jpeg;base64,{encoded_print}"
          }
        }
      ]
    )
    description = vision_llm.invoke([message]).content

    return description
  except Exception as e:
    return f"Error tryning to describe the page print. Error: {str(e)}"
  
def make_log_event(type, content=""):
  return { "id": str(uuid4()), "type": type, "content": content }

def make_sse_data(data):
  if isinstance(data, dict):
    data = json.dumps(data, ensure_ascii=False)
  return f"data: {data}\n\n"

def extract_domain(url: str) -> str:
  ext = tldextract.extract(url)
  return f"{ext.domain}.{ext.suffix}"

def node(node_name: str):
  def decorator(func):
    def wrapper(self, *args, **kwargs):
      # Call the original factory method to get the inner node function
      inner_node_func = func(self, *args, **kwargs)
      
      async def node_execution_wrapper(state: dict) -> Command:
        # Execute the inner node function
        result = await inner_node_func(state)
        
        # Logging logic (now has access to 'self' from wrapper closure)
        if isinstance(result, Command) and "messages" in result.update:
          messages = state["messages"] + result.update["messages"]
          if len(messages) >= 2:
            previous_msg = messages[-2]
            if isinstance(previous_msg, ToolMessage):
              self.logger.debug(f"Tools 🛠️: {previous_msg}")

          new_messages = result.update.get("messages", [])
          last_ai_msg = next((m for m in reversed(new_messages) if isinstance(m, AIMessage)), None)

          if last_ai_msg:
            token_updates = save_tokens(state, last_ai_msg)
            result.update.update(token_updates)
            
            last_ai_content = get_text_content(last_ai_msg)
            content_empty = not last_ai_content or last_ai_content.strip() == ""
            no_tool_calls = not (hasattr(last_ai_msg, "tool_calls") and last_ai_msg.tool_calls)
            
            if content_empty and no_tool_calls:
              self.logger.debug(f"{node_name.upper()} 🤖: ⚠️  Empty AI response. Overriding to retry. ⚠️")
              
              retry_alert = "SYSTEM ALERT: The last response was empty. Please provide a clear action or use a tool."
              new_messages = list(new_messages) + [HumanMessage(content=retry_alert)]
              
              result = Command(
                update={**result.update, **token_updates, "messages": new_messages}, 
                goto=node_name
              )

          last_msg = new_messages[-1]
          last_msg_content = get_text_content(last_msg)

          if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
            node_msg = [
              f"{tc['name']}(" + ", ".join(f"{k}={v!r}" for k, v in tc['args'].items()) + ")"
              for tc in last_msg.tool_calls
            ]
          else:
            node_msg = last_msg_content

          self.logger.debug(f"{node_name.upper()} 🤖: {node_msg}")

        return result
      return node_execution_wrapper
    return wrapper
  return decorator

def get_text_content(message: BaseMessage) -> str:
  """
  Extracts text content from a message, handling both string and list content (blocks).
  """
  content = message.content
  if isinstance(content, str):
    return content
  
  if isinstance(content, list):
    text_parts = []
    for part in content:
      if isinstance(part, str):
        text_parts.append(part)
      elif isinstance(part, dict) and part.get("type") == "text":
        text_parts.append(part.get("text", ""))
    return "".join(text_parts)
  
  if isinstance(content, dict) and content.get("type") == "text":
    return content.get("text", "")
  
  return str(content)

def save_tokens(state: dict, response: AIMessage) -> dict:
  usage = getattr(response, "usage_metadata", None)
  if not usage:
    return {}

  input_tokens = usage.get("input_tokens", 0)
  output_tokens = usage.get("output_tokens", 0)
  total_tokens = usage.get("total_tokens", 0)
  
  return {
    "tokens": state.get("tokens", 0) + total_tokens,
    "input_tokens": state.get("input_tokens", 0) + input_tokens,
    "output_tokens": state.get("output_tokens", 0) + output_tokens
  }