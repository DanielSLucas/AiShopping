import base64

def encode_image(self, image_path: str) -> str:
  """Encode image to base64 string"""
  with open(image_path, "rb") as image_file:
    return base64.b64encode(image_file.read()).decode("utf-8")  