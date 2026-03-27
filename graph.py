from procedure import *
from chem_utils import check_input
from doc_utils import *
from utils import *
import os, html
import pickle as pkl

from langchain.messages import HumanMessage, AIMessage
from typing import Literal, Dict, TypedDict


async def supervisor_node(state, config):
    
    if state['user_input'] is None:
        state['rsmi'] = state['rsmi'].strip()
        state['constraint'] = state['constraint'].strip()
        try:
            yield "[M]⏳ ... Query Expansion ..."
            reaction_attr, query_type = check_input(state['rsmi'])
            assert query_type == 'Reaction'
            state['reaction'] = reaction_attr
            state['message'] = [
                HumanMessage(
                    content = f"Reaction:\n{json_to_str(state['reaction'])}" + "\n\n"
                            + f"Constraints:\n{state['constraint']}"
                )
            ]
            state['supervision'] = 'init'
        except:
            state['supervision'] = 'invalid'

    else:
        state['message'].append(
            HumanMessage(
                content = state['user_input'].strip()
            )
        )
        next_node = call_agent("supervisor", state['message'], to_json = False)
        state['supervision'] = next_node.lower().strip()
    
    yield state


def supervisor_router(state, config) -> Literal["init", "invalid", "update_major", "update_minor", "chat"]:
    
    return state["supervision"]


async def init_node(state, config):
    
    yield "[M]⏳ ... Compound-Level Analysis ..."
    state['compound_cond'] = await compound_level_analysis(state['reaction'], state['constraint'])
    
    yield "[M]⏳ ... Reaction-Level Integration ..."
    state['reaction_cond'] = await reaction_level_analysis(state['reaction'], state['compound_cond'], state['constraint'])
    
    yield "[M]⏳ ... Report Generation ..."
    summary_text, md_html = create_report(state['reaction'], state['compound_cond'], state['reaction_cond'], state['constraint'])
    state['message'].extend([
        AIMessage(content = f"LC-MS Condition for Individual Components:\n{json_to_str(state['compound_cond'])}" + "\n\n\n"
                          + f"LC-MS Condition for Reaction:\n{json_to_str(state['reaction_cond'])}" + "\n\n\n"
                          + f"Summary Report:\n{summary_text}"
        )
    ])    
    state['html_content'] = html.escape(md_html)
    
    thread_id = config['configurable']['thread_id']
    os.makedirs(os.path.join(state['save_dir'], thread_id), exist_ok=True)
    with open(os.path.join(state['save_dir'], thread_id, "output_init.html"), "w", encoding="utf-8") as f:
        f.write(md_html)
    
    #with open(os.path.join(state['save_dir'], thread_id, "data.pkl"), "wb") as f:
    #    pkl.dump([state['compound_cond'], state['reaction_cond']], f)
    
    yield state


async def update_node(state, config):

    state['constraint'] = (state['constraint'] + f"\nUser added: {state['user_input']}").strip()
    if state['supervision'] == 'update_minor':
        yield "[M]⏳ ... Incorporating User Feedback (Minor Update) ..."
        state['reaction_cond'] = await reaction_level_update(state['reaction'], state['reaction_cond'], state['constraint'], max_iter = 1)
    elif state['supervision'] == 'update_major':
        yield "[M]⏳ ... Incorporating User Feedback (Major Update) ..."
        state['reaction_cond'] = await reaction_level_analysis(state['reaction'], state['compound_cond'], state['constraint'])
        
    yield "[M]⏳ ... Report Generation ..."    
    summary_text, md_html = create_report(state['reaction'], state['compound_cond'], state['reaction_cond'], state['constraint'])
    state['message'].extend([
        AIMessage(content = "Updated!\n\n" 
                          + f"LC-MS Condition for Reaction:\n{json_to_str(state['reaction_cond'])}" + "\n\n\n"
                          + f"Summary Report:\n{summary_text}"
        )
    ])
    state['html_content'] = html.escape(md_html)

    thread_id = config['configurable']['thread_id']
    with open(os.path.join(state['save_dir'], thread_id, "output_update.html"), "w", encoding="utf-8") as f:
        f.write(md_html)
    
    yield state


async def chat_node(state, config):
    
    response = await a_call_agent_stream("chat", state['message'])
    yield response
    
    state['message'].extend([
        AIMessage(content = response)
    ])
    
    yield state