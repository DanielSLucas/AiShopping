import base64

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage

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