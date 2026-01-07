import asyncio
import os
import json
import time
from uuid import uuid4
from typing import Annotated, Literal, TypedDict, List
from enum import StrEnum

from scrapping_agent.scrap import ScrapScriptsManager
from scrapping_agent.scrapper import Scrapper
from scrapping_agent.tools import make_scrapper_tools, Tools
from utils.logger import Logger
from utils.utils import extract_domain, get_prompt, node, get_text_content

from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import StateGraph, END, START
from langgraph.graph.message import add_messages
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage, BaseMessage
from langgraph.types import Command
from langgraph.prebuilt import ToolNode
from langchain_core.tools import BaseTool

class State(TypedDict):
  query: str
  all_results: bool
  messages: Annotated[List[BaseMessage], add_messages]
  actions_history: List[str]
  tokens: int
  input_tokens: int
  output_tokens: int
  scrap_script: dict
  script_executed: bool
  retry_count: int

class Nodes(StrEnum):
  SCRIPT_EXECUTOR = "script_executor"
  SCRIPT_EXECUTOR_TOOLS = "script_executor_tools"
  SCRAPPER = "scrapper"
  SCRAPPER_TOOLS = "scrapper_tools"
  SCRIPT_WRITTER = "script_writter"
  SCRIPT_WRITTER_TOOLS = "script_writter_tools"
  RESPONSE = "response"
  END = END


class ScrappingAgent:
  def __init__(
    self,
    llm: BaseChatModel,
    debug: bool = True,
    vision_model = ChatOpenAI(model="gpt-4o"),
    logger: Logger = None,
    max_retries: int = 2
  ):
    self.debug = debug
    self.logger = logger
    self.max_retries = max_retries

    self.scrapper = Scrapper()
    self.llm = llm
    self.vision_model = vision_model

    self.graph = None
    self.scrapping_tools = None
    self.current_node = None

  async def initialize(self, url:str, headless: bool = True):
    self.url = url
    
    if not self.logger:
      self.logger = Logger(
        file_name=f"{extract_domain(url)}_scrap",
        show_debug_logs=self.debug
      )
    
    self.scrapping_tools = make_scrapper_tools(
      self.scrapper,
      vision_model=self.vision_model,
      headless=headless,
      logger=self.logger
    )

  async def close(self):
    if self.scrapper:
      await self.scrapper.close()

  async def run(self, query: str, all_results: bool = True, recursion_limit: int = 100):
    start_time = time.time()

    scraping_context = {
      "type": "SITE",
      "content": {
        "url": self.url,
        "id": str(uuid4()),
        "start_time": start_time,
        "end_time": None
      }
    }
    self.logger.info(scraping_context)

    if not self.graph:
      self.graph = self._build_graph()

    ssm = ScrapScriptsManager()

    scrap_script_exists = ssm.exists(extract_domain(self.url))
    scrap_script = ssm.get(extract_domain(self.url)) if scrap_script_exists else "None"

    initial_message = f"Busque: {query}\nNo Site: {self.url}"
      
    initial_state = State(
      query=query,
      all_results=all_results,
      messages=[HumanMessage(initial_message)],
      actions_history=[],
      tokens=0,
      input_tokens=0,
      output_tokens=0,
      scrap_script=scrap_script,
      script_executed=False,
      retry_count=0
    )

    config = {"configurable": {"thread_id": "1"}, "recursion_limit": recursion_limit}

    self.logger.debug(initial_message)

    result = await self.graph.ainvoke(initial_state, config)

    self.logger.debug(f"Input tokens: {result.get('input_tokens', 0)}")
    self.logger.debug(f"Output tokens: {result.get('output_tokens', 0)}")
    self.logger.info(f"Total tokens: {result.get('tokens', 0)}")

    scraping_context["content"]["end_time"] = time.time()
    self.logger.info(scraping_context)

    response = { "type": "RESPONSE", "content": get_text_content(result["messages"][-1]) }
    self.logger.info(response)

    return response


  def _build_graph(self) -> StateGraph:
    graph_builder = StateGraph(State)

    executor_tools = [t for t in self.scrapping_tools.values() if t.get_name() in [Tools.EXECUTE_SCRAP_SCRIPT, Tools.GET_SCRAP_SCRIPT]]
    writter_tools = [self.scrapping_tools[Tools.SAVE_SCRAP_SCRIPT]]
    scrapper_tools = [t for t in self.scrapping_tools.values() if t not in executor_tools + writter_tools]

    graph_builder.add_node(Nodes.SCRIPT_EXECUTOR, self._make_script_executor_node(executor_tools))
    graph_builder.add_node(Nodes.SCRIPT_EXECUTOR_TOOLS, ToolNode(executor_tools))
    graph_builder.add_node(Nodes.SCRAPPER, self._make_scrapper_node(scrapper_tools))
    graph_builder.add_node(Nodes.SCRAPPER_TOOLS, ToolNode(scrapper_tools))
    graph_builder.add_node(Nodes.SCRIPT_WRITTER, self._make_script_writter_node(writter_tools))
    graph_builder.add_node(Nodes.SCRIPT_WRITTER_TOOLS, ToolNode(writter_tools))
    graph_builder.add_node(Nodes.RESPONSE, self._make_response_node())

    graph_builder.add_edge(START, Nodes.SCRIPT_EXECUTOR)
    graph_builder.add_edge(Nodes.SCRIPT_EXECUTOR_TOOLS, Nodes.SCRIPT_EXECUTOR)
    graph_builder.add_edge(Nodes.SCRAPPER_TOOLS, Nodes.SCRAPPER)
    graph_builder.add_edge(Nodes.SCRIPT_WRITTER_TOOLS, Nodes.SCRIPT_WRITTER)
    graph_builder.add_edge(Nodes.RESPONSE, END)

    return graph_builder.compile(checkpointer=MemorySaver())

  @node(Nodes.SCRIPT_EXECUTOR)
  def _make_script_executor_node(self, tools: List[BaseTool] = []) -> Command:
    async def executor_node(state: State) -> Command:
      prompt = self.__get_prompt_template(Nodes.SCRIPT_EXECUTOR)
      model = self.llm.bind_tools(tools)
      
      script_executed = state.get("script_executed", False)
      last_message = state["messages"][-1]
      
      if isinstance(last_message, ToolMessage) and last_message.name == Tools.EXECUTE_SCRAP_SCRIPT:        
        script_executed = self._validate_script_execution(last_message.content)
      
      trimmed_state = state.copy()
      trimmed_state["messages"] = self._trim_history(state["messages"])
      
      s_script = state.get("scrap_script", "None")
      trimmed_state["scrap_script"] = json.dumps(s_script, indent=2) if isinstance(s_script, dict) else str(s_script)
      trimmed_state["query"] = state["query"]

      response = await (prompt | model).ainvoke(trimmed_state)
      
      if response.tool_calls:
        return Command(update={"messages": [response]}, goto=Nodes.SCRIPT_EXECUTOR_TOOLS)
      
      if not script_executed or state["scrap_script"] == "None":
        retry_count = state.get("retry_count", 0)
        if retry_count < self.max_retries:
          if state["scrap_script"] == "None":
            self.logger.info("No script found. Moving to SCRAPPER.")
            msg = HumanMessage(content="SYSTEM ALERT: No script found for this domain. Please explore the page and find the elements.")
          else:
            self.logger.info(f"Script execution failed. Retrying ({retry_count + 1}/{self.max_retries})...")
            msg = HumanMessage(content="SYSTEM ALERT: Execution failed. Please analyze the 'extract' steps and fix the selectors.")
          
          return Command(
            update={"messages": [response, msg], "retry_count": retry_count + 1, "script_executed": False},
            goto=Nodes.SCRAPPER
          )
        else:
          self.logger.info("Max retries reached. Moving to RESPONSE.")
      
      return Command(update={"messages": [response], "script_executed": script_executed}, goto=Nodes.RESPONSE)
    return executor_node
  
  @node(Nodes.SCRAPPER)
  def _make_scrapper_node(self, tools: List[BaseTool] = []) -> Command:
    async def scrapper_node(state: State) -> Command:
      prompt = self.__get_prompt_template(Nodes.SCRAPPER)
      model = self.llm.bind_tools(tools)
      
      trimmed_state = state.copy()
      trimmed_state["messages"] = self._trim_history(state["messages"])
      
      trimmed_state["query"] = state["query"]
      trimmed_state["all_results"] = str(state["all_results"])
      trimmed_state["retry_mode"] = "True" if state.get("retry_count", 0) > 0 else "False"

      response = await (prompt | model).ainvoke(trimmed_state)

      if response.tool_calls:  
        tool_calls = self._get_formatted_tool_calls(response)
        return Command(
          update={"messages": [response], "actions_history": state["actions_history"] + tool_calls}, 
          goto=Nodes.SCRAPPER_TOOLS
        )
      
      return Command(update={"messages": [response]}, goto=Nodes.SCRIPT_WRITTER)
    return scrapper_node

  @node(Nodes.SCRIPT_WRITTER)
  def _make_script_writter_node(self, tools: List[BaseTool] = []) -> Command:
    async def script_writter_node(state: State) -> Command:
      prompt = self.__get_prompt_template(Nodes.SCRIPT_WRITTER)
      model = self.llm.bind_tools(tools)
      
      trimmed_state = state.copy()
      trimmed_state["messages"] = self._trim_history(state["messages"])
      
      history = state.get("actions_history", [])
      trimmed_state["actions_history"] = "\n".join(history) if isinstance(history, list) else str(history)
      trimmed_state["query"] = state["query"]

      response = await (prompt | model).ainvoke(trimmed_state)

      if response.tool_calls:
        self.logger.debug("Saving scrap script")
        scrap_script = response.tool_calls[0]["args"].get("scrap_script")
        return Command(update={"messages": [response], "scrap_script": scrap_script}, goto=Nodes.SCRIPT_WRITTER_TOOLS)
      
      self.logger.debug("Moving to: SCRIPT_EXECUTOR")
      return Command(update={"messages": [response]}, goto=Nodes.SCRIPT_EXECUTOR)
    return script_writter_node

  @node(Nodes.RESPONSE)
  def _make_response_node(self):
    async def response_node(state: State) -> Command:
      prompt = self.__get_prompt_template(Nodes.RESPONSE)
      response = await (prompt | self.llm).ainvoke(state)
      return Command(update={"messages": [response]})
    return response_node

  def __get_prompt_template(self, role) -> ChatPromptTemplate:
    prompt_path = os.path.join(os.path.dirname(__file__), "prompts", f"{role}.md")
    return ChatPromptTemplate.from_messages([
      ("system", get_prompt(prompt_path)),
      MessagesPlaceholder("messages")
    ])

  def _validate_script_execution(self, execution_result: str):
    if "Error" in execution_result:
      return False
    
    try:
      data = json.loads(execution_result)
      def count_nones(obj):
        total = 0
        nones = 0
        if isinstance(obj, dict):
          for v in obj.values():
            t, n = count_nones(v)
            total += t
            nones += n
        elif isinstance(obj, list):
          for v in obj:
            t, n = count_nones(v)
            total += t
            nones += n
        elif isinstance(obj, str):
          total = 1
          if obj == "None": nones = 1
        return total, nones

      total, nones = count_nones(data)
        
      if isinstance(data, list) and len(data) == 0:
        return False 
      elif total > 0 and (nones / total) > 0.25:
        self.logger.info(f"Execution flagged as failure due to high None rate: {nones}/{total} (>{25}%)")
        return False 
      else:
        self.logger.debug(f"Script executed with success")
        return True
    except Exception as e:
      self.logger.debug(f"JSON parse error or validation error: {e}")
      return True
  
  def _get_formatted_tool_calls(self, msg: BaseMessage):
    return [
      f"{tc['name']}(" + ", ".join(f"{k}={v!r}" for k, v in tc['args'].items()) + ")"
      for tc in msg.tool_calls
    ]

  def _trim_history(self, messages: List[BaseMessage]) -> List[BaseMessage]:
    """
    Trims tool responses that are too large or from old get_dom_tree calls to save tokens.
    """
    trimmed = []
    for i, msg in enumerate(messages):
      if isinstance(msg, ToolMessage):
        is_recent = i >= len(messages) - 3
        
        if len(str(msg.content)) > 2000:
          if is_recent:
             trimmed.append(msg)
          else:
            trimmed.append(ToolMessage(
              content=str(msg.content)[:300] + "... [TRUNCATED TO SAVE TOKENS]",
              tool_call_id=msg.tool_call_id,
              name=msg.name
            ))
          continue
      
      trimmed.append(msg)
    return trimmed

