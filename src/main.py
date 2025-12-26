import asyncio
import sys

import uvicorn
from dotenv import load_dotenv
load_dotenv()

from cli import run_shopping_agent_cli, run_scrapping_agent, run_scrap_script
from server import app

if __name__ == "__main__":
  if "--shopping" in sys.argv:
    asyncio.run(run_shopping_agent_cli())
    sys.exit(0)

  if "--scrapping" in sys.argv:
    asyncio.run(run_scrapping_agent())
    sys.exit(0)

  if "--sscript" in sys.argv:
    asyncio.run(run_scrap_script())
    sys.exit(0)

  uvicorn.run(app, host="0.0.0.0", port=3000)