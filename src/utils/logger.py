import os
from datetime import datetime
from uuid import uuid4
import json
from queue import Queue

LOGS_DIR = "./logs"
os.makedirs(LOGS_DIR, exist_ok=True)

class Logger:
  def __init__(
    self, 
    file_name: str = "", 
    show_debug_logs: bool = False,
    format_logs: bool = True,
    logger_id: str = str(uuid4())
  ):
    self.LOGS_QUEUE = Queue()
    self.id = logger_id
    self.file_name = file_name + f"_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.json"
    self.show_debug_logs = show_debug_logs
    self.format_logs = format_logs
  
  def info(self, *msgs: str | dict):
    self.display(*msgs, kind="INFO")
    self.append_to_log_file(*msgs, kind="INFO")
  
  def debug(self, *msgs: str | dict):
    if self.show_debug_logs:
      self.display(*msgs, kind="DEBUG")
    self.append_to_log_file(*msgs, kind="DEBUG")

  def get_log_file(self) -> str | dict:
    return self.file_name
  
  def display(self, *msgs: str | dict, kind: str):
    for msg in msgs:
      ser_msg = self.serialize_message(msg, kind)
      
      self.LOGS_QUEUE.put(
        ser_msg if self.format_logs else f"[{kind}] {msg!r}"
      )

  def append_to_log_file(self, *msgs: str | dict, kind: str):
    with open(os.path.join(LOGS_DIR, self.file_name), "a") as log_file:
      serialized_msgs = [self.serialize_message(msg, kind) for msg in msgs]
      log_file.write("\n".join(serialized_msgs) + "\n")

  def serialize_message(self, msg: str | dict, kind: str) -> str:
    return json.dumps({
      "time": datetime.now().strftime('%Y-%m-%d_%H-%M-%S'),
      "id": self.id,
      "type": kind,
      "content": msg
    })