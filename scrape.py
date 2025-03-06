from scrapegraphai.graphs import SmartScraperGraph

# Create the SmartScraperGraph instance
smart_scraper_graph = SmartScraperGraph(
    prompt="Search for 'mouses sem fio' and than extract the first page of products",
    source="https://lista.mercadolivre.com.br/moues-sem-fio#D[A:moues%20sem%20fio]",
    config={
        "llm": {
            "model": "ollama/qwen2.5",
            "model_tokens": 8192
        },
        "verbose": True,
        "headless": False,
    }
)

# Run the pipeline
result = smart_scraper_graph.run()

import json
print(json.dumps(result, indent=4))