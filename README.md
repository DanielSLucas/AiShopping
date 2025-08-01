# AiShopping

AiShopping is an intelligent shopping assistant and web scraping platform designed to automate product research, price comparison, and data collection from various e-commerce websites. Built with Python, it leverages agent-based architectures and modular tools to provide flexible and extensible shopping automation.

## Features
- Automated web scraping for multiple online stores
- Agent-based architecture for shopping and data collection tasks
- Modular design for easy extension and customization
- Logging and data storage for collected information
- Utilities for data processing and analysis

## Project Structure
- `src/` - Main source code
  - `scrapping_agent/` - Web scraping agents and tools
  - `shopping_agent/` - Shopping automation agents and tools
  - `utils/` - Utility functions and logging
- `logs/` - Collected logs and scraped data
- `requirements.txt` - Python dependencies

## Getting Started
1. **Clone the repository:**
   ```zsh
   git clone https://github.com/DanielSLucas/AiShopping.git
   cd AiShopping
   ```
2. **Install dependencies:**
   ```zsh
   pip install -r requirements.txt
   ```

3. **Set up environment variables:**
   Create a `.env` file in the project root with the following content:
   ```env
   # OpenAI API
   OPENAI_API_KEY=

   # Google Search API
   GOOGLE_API_KEY=
   GOOGLE_CSE_ID=
   ```

4. **Run the main application:**
   ```zsh
   python src/main.py
   ```

## Usage
Configure scraping scripts in `src/scrapping_agent/scrap_scripts/` and customize agent prompts as needed. Logs and results are stored in the `logs/` directory.
