import gradio as gr
from langgraph.graph import StateGraph, START, END 
from langgraph.checkpoint.memory import InMemorySaver
from langchain.messages import AIMessageChunk

from graph import *
import uuid, yaml
with open("config.yaml", "r", encoding="utf-8") as f:
    config = yaml.safe_load(f)

os.makedirs(config['misc']['save_dir'], exist_ok=True)


class GraphState(TypedDict):
    rsmi: str
    reaction: str
    constraint: str
    compound_cond: dict
    reaction_cond: dict
    message: list
    user_input: str
    supervision: str
    html_content: str
    save_dir: str


workflow = StateGraph(GraphState)

workflow.add_edge(START, 'supervisor')
workflow.add_node('supervisor', supervisor_node)
workflow.add_node('init', init_node)
workflow.add_node('update', update_node)
workflow.add_node('chat', chat_node)
workflow.add_conditional_edges(
    'supervisor',
    supervisor_router,
    {'init': 'init', 'invalid': END, 'update_major': 'update', 'update_minor': 'update', 'chat': 'chat'}
)
workflow.add_edge('init', END)
workflow.add_edge('update', END)
workflow.add_edge('chat', END)

memory = InMemorySaver()
app = workflow.compile(checkpointer = memory)


def load_html(html_content):
    
    return f"<iframe srcdoc='{html_content}' style='width:100%; height:85vh; border:1px solid #ccc;'></iframe>"


async def start_fn(rsmi, constraint, thread_id):
    
    print("thread_id:", thread_id)
    result = app.astream_events(
        {
            'save_dir': config['misc']['save_dir'],
            'rsmi': rsmi,
            'constraint': constraint,
            'user_input': None,
        },
        config={'configurable': {'thread_id': thread_id}}
    )
    
    status = None
    intermediate = ""
    async for event in result:
        if event['event'] == 'on_chain_stream' and "chunk" in event["data"]:
            if not isinstance(event['data']['chunk'], dict) and event['data']['chunk'].startswith("[M]"):
                print("MESSAGE:", event['data']['chunk'])
                intermediate += "\n" + event['data']['chunk'][3:]
                yield (
                    gr.update(),
                    [gr.ChatMessage(role="assistant", content=intermediate[1:])],
                    None
                )

            elif 'supervisor' in event['data']['chunk']:
                status = event['data']['chunk']['supervisor']['supervision']
    
    if status == 'invalid':
        raise gr.Error("Invalid Reaction SMILES!")
    
    elif status == 'init':
        yield (
            gr.update(interactive=True),
            [gr.ChatMessage(role="assistant", content="How can I help you?")],
            load_html(event['data']['output']['html_content'])
        )

  
def reset_fn():
    
    return (
        gr.update(value="", interactive=True),
        gr.update(value="", interactive=True),
        gr.update(value="", interactive=False),
        [],
        None
    )


async def chat_fn(message, chat_history, thread_id):

    yield (
        gr.update(value="", interactive=False),
        chat_history + [gr.ChatMessage(role="user", content=message)],
        gr.update()
    )

    result = app.astream_events(
        {
            'user_input': message,
        },
        config={'configurable': {'thread_id': thread_id}}
    )

    ## intermediate output
    status = None
    intermediate = ""
    generated = ""
    async for event in result:
        if event['event'] == 'on_chain_stream' and "chunk" in event["data"]:
            if not isinstance(event['data']['chunk'], dict) and event['data']['chunk'].startswith("[M]"):
                print("MESSAGE:", event['data']['chunk'])
                intermediate += "\n" + event['data']['chunk'][3:]
                yield (
                    gr.update(value="", interactive=False),
                    chat_history + [gr.ChatMessage(role="user", content=message), gr.ChatMessage(role="assistant", content=intermediate[1:])],
                    gr.update()
                )
            elif 'supervisor' in event['data']['chunk']:
                status = event['data']['chunk']['supervisor']['supervision']
                
        elif status == 'chat' and event["event"] == "on_chat_model_stream" and "chunk" in event["data"]:
            if isinstance(event["data"]["chunk"], AIMessageChunk) and event["data"]["chunk"].content:
                generated += event["data"]["chunk"].content[0]['text']
                yield (
                    gr.update(value="", interactive=False),
                    chat_history + [gr.ChatMessage(role="user", content=message), gr.ChatMessage(role="assistant", content=generated)],
                    gr.update()
                )

    ## final output
    if status.startswith('update'):
        yield (
            gr.update(value="", interactive=True),
            chat_history + [gr.ChatMessage(role="user", content=message), gr.ChatMessage(role="assistant", content="Updated the report!")],
            load_html(event['data']['output']['html_content'])
        )
        
    elif status == 'chat':
        #print('check', event['data']['output']['message'][-1].content)
        yield (
            gr.update(value="", interactive=True),
            chat_history + [gr.ChatMessage(role="user", content=message), gr.ChatMessage(role="assistant", content=generated)],
            gr.update()
        )
 
       
with gr.Blocks(fill_width=True, fill_height=True) as demo:
    thread_state = gr.State(lambda: str(uuid.uuid4()))

    with gr.Row():
        # LEFT SIDE
        with gr.Column(scale=1):
            input_rsmi = gr.Textbox(lines=1, max_lines=1, label="Reaction SMILES", interactive=True)
            input_const = gr.Textbox(lines=2, max_lines=2, label="Constraints", interactive=True)
            with gr.Row():
                start_btn = gr.Button("Start")
                clear_btn = gr.Button("Reset")

            chatbot = gr.Chatbot(scale=1, height='45vh')#buttons=[])
            chatbox = gr.Textbox(lines=1, max_lines=4, show_label=False, placeholder="Type a message...", interactive=False, submit_btn=True)

        # RIGHT SIDE
        with gr.Column(scale=2):
            html_view = gr.HTML(None)
        
        start_btn.click(
            fn=start_fn,
            inputs=[input_rsmi, input_const, thread_state],
            outputs=[chatbox, chatbot, html_view]#input_rsmi, input_const, 
        )
        
        clear_btn.click(
            fn=reset_fn,
            inputs=None,
            outputs=[input_rsmi, input_const, chatbox, chatbot, html_view]
        )

        chatbox.submit(
            fn=chat_fn,
            inputs=[chatbox, chatbot, thread_state],
            outputs=[chatbox, chatbot, html_view],
        )
        

demo.launch(server_name="115.145.162.40", share=True)