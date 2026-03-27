import logging
#logging.getLogger("httpx").setLevel(logging.WARNING)
logging.basicConfig(level=logging.WARNING)

from langchain.chat_models import init_chat_model
from langchain.agents import create_agent
import asyncio
import prompt
from tools import *
from utils import *

from dotenv import load_dotenv
load_dotenv()

import yaml
with open("config.yaml", "r", encoding="utf-8") as f:
    config = yaml.safe_load(f)


# LLM model to use
base_llm = init_chat_model(
    model = config['base_llm']['model'],
    temperature = config['base_llm']['temperature'],
    top_p = config['base_llm']['top_p'],
    thinking_level = config['base_llm']['thinking_level'],
    include_thoughts = False
)

# Agents
generation_agent = create_agent(
    model = base_llm,
    tools = [smiles_expand, iupac_expand],
    system_prompt = prompt.GENERATION_PROMPT,
    name = "Generation Agent"
)

web_search_agent = create_agent(
    model = base_llm,
    tools = [web_search_tool, extraction_tool, smiles_expand, iupac_expand],
    system_prompt = prompt.SEARCH_PROMPT,
    name = "Web Search Agent"
)

scholarly_search_agent = create_agent(
    model = base_llm,
    tools = [scholarly_search_tool, extraction_tool, smiles_expand, iupac_expand],
    system_prompt = prompt.SEARCH_PROMPT.replace("\"S_", "\"E_"),
    name = "Scholarly Search Agent"
)

reflection_agent = create_agent(
    model = base_llm,
    tools = [web_search_tool, smiles_expand, iupac_expand],
    system_prompt = prompt.REFLECTION_PROMPT,
    name = "Reflection Agent"
)

evolution_agent = create_agent(
    model = base_llm,
    tools = [smiles_expand, iupac_expand],
    system_prompt = prompt.EVOLUTION_PROMPT,
    name = "Evolution Agent"
)

integration_agent = create_agent(
    model = base_llm,
    tools = [smiles_expand, iupac_expand],
    system_prompt = prompt.INTEGRATION_PROMPT,
    name = "Integration Agent"
)

metareview_agent = create_agent(
    model = base_llm,
    tools = [smiles_expand, iupac_expand],
    system_prompt = prompt.METAREVIEW_PROMPT,
    name = "Meta-Review Agent"
)

report_agent = create_agent(
    model = base_llm,
    tools = [],
    system_prompt = prompt.REPORTING_PROMPT,
    name = "Reporting Agent"
)

supervisor_agent = create_agent(
    model = base_llm,
    tools = [],
    system_prompt = prompt.SUPERVISOR_PROMPT,
    name = "Supervisor Agent"
)

chat_agent = create_agent(
    model = base_llm,
    tools = [web_search_tool, smiles_expand, iupac_expand],
    system_prompt = prompt.CHAT_PROMPT,
    name = "Chat Agent"
)

agents = {
    "generate": generation_agent,
    "web_search": web_search_agent,
    "scholarly_search": scholarly_search_agent,
    "reflect": reflection_agent,
    "evolve": evolution_agent,
    "integrate": integration_agent,
    "metareview": metareview_agent,
    "report": report_agent,
    "supervisor": supervisor_agent,
    "chat": chat_agent
}

def call_agent(agent_name, messages, n_retry = 3, to_json = True):

    for attempt in range(1, n_retry + 1):
        content = ""
        try:
            response = agents.get(agent_name).invoke({"messages": messages})
            content = response['messages'][-1].content[0]['text']

            if to_json:
                if len(content.strip()) == 0:
                    content = {}
                else:
                    content = str_to_json(content)
                check_output(agent_name, content)
                return content
            return content

        except Exception as e:
            print(f"[{attempt}/{n_retry}] {agent_name} parsing error: {e}")
    
    return None


async def a_call_agent(agent_name, messages, n_retry = 3, to_json = True):
    
    return await asyncio.to_thread(call_agent, agent_name, messages, n_retry, to_json)


async def a_call_agent_stream(agent_name, messages):

    response = await agents.get(agent_name).ainvoke({"messages": messages})
    content = response['messages'][-1].content[0]['text']
   
    return content
