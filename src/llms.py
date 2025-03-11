import os
from openai import OpenAI

class LlmBase:
  def __init__(self):
    self.messages = []

  def set_system_prompt(self, prompt:str):
    self.__add_message(prompt, "system")

  def add_conversation_sample(self, *messages):
    self.messages.extend(messages)

  def __add_message(self, message: str, role: str):
    self.messages.append({ "role": role, "content": message })

  def _add_user_message(self, message: str):
    self.__add_message(message, "user")

  def _add_assistant_message(self, message: str):
    self.__add_message(message, "assistant")

  def get_response(self, message: str):
    raise NotImplementedError("get_response not implemented")
  
class LlmOpenAi(LlmBase):
  def __init__(self, model: str, api_key:str =os.getenv("OPENAI_API_KEY")):
    super().__init__()
    self.model = model
    self.client = OpenAI(api_key=api_key)

  def get_response(self, message):
    self._add_user_message(message)

    raw_response = self.client.chat.completions.create(
      model=self.model,
      messages=self.messages,
    )
    response = raw_response.choices[0].message.content.strip()
    self._add_assistant_message(response)

    return response