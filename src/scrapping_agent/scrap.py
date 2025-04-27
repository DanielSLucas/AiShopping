import os
import json
import sys
import re

from playwright.sync_api import sync_playwright

def fill(page, step):
  page.fill(step["selector"], step["text"])

def click(page, step):
  page.click(step["selector"])
  page.wait_for_load_state()

def extract(parent, step):
  result = []
  el = parent.query_selector(step["selector"])
  if el is None:
    return "Element not found"
  for prop, label in step["properties"].items():
    prop_value = el.evaluate(f"el => el.{prop}").replace(r"\s+", " ").strip()
    result.append(f"{label.upper()}: {prop_value}")
  return "\n".join(result)

def extract_all(page, step):
  step_label = step["label"].upper()
  limit = step["limit"]
  result = []
  page.wait_for_selector(step["selector"])
  for i, el in enumerate(page.query_selector_all(step["selector"])):
    if i >= limit: break
    result.append("\n".join([f"{step_label} #{i+1}"] + [extract(el, in_step) for in_step in step["forEach"]]))
  return "\n".join(result)

actions = {
  "fill": fill,
  "click": click,
  "extract": extract,
  "extract_all": extract_all
}

def replace_placeholders(obj, input_values):
  if isinstance(obj, dict):
    for key, value in obj.items():
      obj[key] = replace_placeholders(value, input_values)
  elif isinstance(obj, list):
    for i, item in enumerate(obj):
      obj[i] = replace_placeholders(item, input_values)
  elif isinstance(obj, str):
    for var_name, var_value in input_values.items():
      placeholder = f"{{{{{var_name}}}}}"
      if placeholder in obj:
        obj = obj.replace(placeholder, var_value)
  return obj

def parse_args():
  if len(sys.argv) < 2:
    print("Error: Missing JSON file path")
    print("Usage: python scrap.py <json_file> [var_name=\"var value\" ...]")
    sys.exit(1)

  json_file = sys.argv[1]
  input_values = {}

  for arg in sys.argv[2:]:
    match = re.match(r'^([^=]+)=(.+)$', arg.strip())
    if not match:
      print(f"Error: Invalid input format: '{arg}'")
      print("Expected format: var_name=\"var value\"")
      sys.exit(1)

    var_name, var_value = match.groups()
    input_values[var_name] = var_value

  return json_file, input_values

def main(json_file, args):
  extracted_data = []

  try:
    script_path = os.path.join(os.path.dirname(__file__), 'scrap_scripts', json_file)
    with open(script_path, 'r') as file:
      scrap_script = json.load(file)

      validate_inputs(args, scrap_script)

      scrap_script = replace_placeholders(scrap_script, args)

      with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()

        print(f"Accessing '{scrap_script['site']}'")

        page.goto(scrap_script["site"])
        page.wait_for_load_state()

        for step in scrap_script["steps"]:
          action = actions[step["action"]]

          print(f"Running '{step['action']}'")

          try:
            result = action(page, step)
            if isinstance(result, str):
              extracted_data.append(result)
          except Exception as e:
            print(f"Error running '{step['action']}'. Error: {str(e)}")
            break

        print("Steps finished")

        browser.close()

    print("Saving extracted data")
    with open('extracted_data.txt', 'w') as file:
      file.write("\n\n".join(extracted_data))

  except FileNotFoundError:
    print(f"Error: JSON file not found: {json_file}")
    sys.exit(1)
  except json.JSONDecodeError:
    print(f"Error: Invalid JSON format in file: {json_file}")
    sys.exit(1)

def validate_inputs(args, scrap_script):
  if "input" in scrap_script:
    missing_inputs = []
    for input_name in scrap_script["input"]:
      if input_name not in args:
        missing_inputs.append(input_name)

    if missing_inputs:
      required_inputs = '\n- '.join([f"{k}: {v}" for k, v in scrap_script['input'].items()])
      print(f"Error: Missing required input variables: {', '.join(missing_inputs)}")
      print(f"Required inputs: \n- {required_inputs}")
      sys.exit(1)

if __name__ == "__main__":
  json_file, input_values = parse_args()
  main(json_file, input_values)
