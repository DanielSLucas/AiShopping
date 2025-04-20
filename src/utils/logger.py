import os
from datetime import datetime

LOGS_DIR = "./logs"
os.makedirs(LOGS_DIR, exist_ok=True)

class Logger:
  def __init__(self, file_name: str = "", show_debug_logs: bool = False):
    self.file_name = file_name + f"_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.txt"
    self.show_debug_logs = show_debug_logs
  
  def log(self, *msgs: str):
    self.display(*msgs, kind="LOG")
    self.append_to_log_file(*msgs)
  
  def info(self, *msgs: str):
    self.display(*msgs, kind="INFO")
  
  def debug(self, *msgs: str):
    if self.show_debug_logs:
      self.display(*msgs, kind="DEBUG")
    self.append_to_log_file(*msgs)

  def get_log_file(self) -> str:
    return self.file_name
  
  def display(self, *msgs: str, kind: str):
    for msg in msgs:
      print(f"[{kind}] {msg}")

  def append_to_log_file(self, *msgs: str):
    with open(os.path.join(LOGS_DIR, self.file_name), "a") as log_file:
      log_file.write("\n".join(msgs) + "\n\n")