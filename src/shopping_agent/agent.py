import os
from typing import Annotated, Literal
from typing_extensions import TypedDict

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, ToolMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.types import interrupt, Command

from shopping_agent.tools import make_researcher_tools
from utils.logger import Logger
from utils.utils import get_prompt
import asyncio

class State(TypedDict):
  messages: Annotated[list, add_messages]
  product: str
  specifications: str
  research: list[(str, str)]

class ShoppingAgent:
  def __init__(
    self,
    llm: BaseChatModel,
    logger: Logger
  ):
    self.llm = llm
    self.logger = logger
    
    self.graph = None
    self.graph_config = None
    self.current_node = None

    self.researcher_tools = make_researcher_tools(self.logger)
    self.tools_by_name = {tool.name: tool for tool in self.researcher_tools}

  async def run(self, run_input, recursion_limit: int = 100):
    if not self.graph:
      self.graph = self._build_graph()
    
    state = None
    if isinstance(run_input, str):
      state = State(
        messages=[HumanMessage(content=run_input)],
        product=run_input,
        specifications="",
        research=[],
      )
    else: 
      state = run_input
    
    if not self.graph_config:
      self.graph_config = {"configurable": {"thread_id": "1"}, "recursion_limit": recursion_limit}
    
    events = self.graph.astream(
      state,
      self.graph_config,
      stream_mode="values"
    )

    last_message = ""
    async for event in events:
      if "messages" in event:
        last_message = event["messages"][-1]

    if self.current_node == "ASK_HUMAN":
      question = last_message.content
      return f"ASK_HUMAN:{question}"
    
    return last_message.content

  async def continue_from_input(self, user_input: str):
    command = Command(resume=user_input)
    await self.run(command)

  def _build_graph(self) -> StateGraph:
    graph_builder = StateGraph(State)
    
    receptionist_node = self.make_default_node("receptionist")
    ask_human_node = self.make_ask_human_node()
    researcher_node = self.make_default_node("researcher", tools=self.researcher_tools)
    tools_node = self.make_tools_node()
    analyst_node = self.make_analyst_node()

    graph_builder.add_node("receptionist", receptionist_node)
    graph_builder.add_node("ask_human", ask_human_node)
    graph_builder.add_node("researcher", researcher_node)
    graph_builder.add_node("tools", tools_node)
    graph_builder.add_node("analyst", analyst_node)

    tools_condition = self.make_tools_condition()

    graph_builder.add_edge(START, "receptionist")
    graph_builder.add_edge("receptionist", "ask_human")
    graph_builder.add_edge("ask_human", "researcher")
    graph_builder.add_conditional_edges("researcher", tools_condition)
    graph_builder.add_edge("tools", "researcher")
    graph_builder.add_edge("analyst",  END)
    
    memory = MemorySaver()
    return graph_builder.compile(checkpointer=memory)

  def make_default_node(self, name: str, tools: list = []):
    async def node(state: State):
      self.current_node = name.upper()
      prompt = self._get_prompt_template(name)
      llm = self.llm.model_copy()
      llm = llm if len(tools) == 0 else llm.bind_tools(tools)
      message = await (prompt | llm).ainvoke(state["messages"])
      self.logger.debug(f"\n{name.upper()} 🤖 -> {message.content}")
      return {"messages": [message]}
    
    return node
  
  def _get_prompt_template(self, role) -> ChatPromptTemplate:
    """Return the prompt template for the receptionist role."""
    prompt_path = os.path.join(os.path.dirname(__file__), "prompts", f"{role}.md")
    return ChatPromptTemplate.from_messages([
      ("system", get_prompt(prompt_path)),
      MessagesPlaceholder("messages")
    ])
  
  def make_ask_human_node(self):
    async def ask_human_node(state: State):
      self.current_node = "ASK_HUMAN"
      human_response = interrupt("ASK_HUMAN")
      self.logger.debug(f"ASK_HUMAN 👤-> {human_response}")
      return {
        "messages": [HumanMessage(human_response)],
        "specifications": human_response
      }
    
    return ask_human_node
  
  def make_analyst_node(self):
    async def node(state: State):
      self.current_node = "ANALYST"
      prompt = self._get_prompt_template("analyst")
      llm = self.llm.model_copy()

      product = state["product"]
      specifications = state["specifications"]
      research = "\n\n".join([f"## {key}:\n{value}" for key, value in state["research"]])

      analyst_input = f"# Produto\n{product}\n# Especificações:\n{specifications}\n# Pequisa:\n{research}"
      self.logger.debug(f"\nANALYST_INPUT -> {analyst_input}")

      message = await (prompt | llm).ainvoke({"messages":[HumanMessage(analyst_input)]})
      self.logger.debug(f"\nANALYST 🤖 -> {message.content}")
      return {"messages": [message]}
    
    return node

  def make_tools_node(self):
    async def tools_node(state: State):
      self.current_node = "TOOLS"
      tool_msgs = await asyncio.gather(*[
        self.handle_tool_call(tool_call, state) 
        for tool_call in state["messages"][-1].tool_calls
      ])
      self.logger.debug(f"\nTOOLS 🛠️ -> {tool_msgs}")  
      return {"messages": tool_msgs}
    
    return tools_node
  
  async def handle_tool_call(self, tool_call, state: State):
    tool_call_id, tool_name, tool_args = tool_call["id"], tool_call["name"], tool_call["args"]
    
    tool = self.tools_by_name[tool_name]
    result = await tool.ainvoke(tool_args)
    
    if tool_name == "save_relevant_data":
      self.logger.debug(f"\nSaving to memory: {tool_args['key']} -> {tool_args['value']}")  
      state["research"].append((tool_args["key"], tool_args["value"]))

    return ToolMessage(content=result, tool_call_id=tool_call_id)
  
  def make_tools_condition(self):
    def tools_condition(state: State) -> Literal["tools", "analyst"]:
      result = "analyst"
      last_message = state["messages"][-1]

      if hasattr(last_message, "tool_calls") and len(last_message.tool_calls) > 0:
        result = "tools"
      self.logger.debug(f"TOOLS_CONDITION -> {result}")

      return result
    
    return tools_condition
