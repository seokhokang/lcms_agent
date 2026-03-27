import asyncio
import os, requests
import markdown
from langchain.messages import HumanMessage, AIMessage

from agents import *
from utils import *
from doc_utils import *
from chem_utils import *

import yaml
with open("config.yaml", "r", encoding="utf-8") as f:
    config = yaml.safe_load(f)


async def compound_level_analysis(reaction_attr, constraint, max_iter = 1):

    async def compound_refine(compound_attr, cond, key, max_iter):

        ref = cond['Ref']
        msg_reflect = [HumanMessage(
            content = f"Compound:\n{json_to_str(compound_attr)}" + "\n\n\n"
                    + f"Constraints:\n{constraint}" + "\n\n\n"
                    + f"LC-MS Condition:\n{json_to_str(cond)}"
        )]
                
        for i in range(max_iter): 
            reflection = await a_call_agent("reflect", msg_reflect, to_json = False)
            reflection = str(reflection)
            
            #print(i+1, len(reflection), reflection[:50])
            if len(reflection) < 10:
                print(f"::: (reflection iter {i+1}) No reflection needed for the condition {key} on {compound_attr['IUPAC_Name']}.")
                break
    
            msg_evolve = [HumanMessage(
                content = f"Compound:\n{json_to_str(compound_attr)}" + "\n\n\n"
                        + f"Constraints:\n{constraint}" + "\n\n\n"
                        + f"LC-MS Condition:\n{json_to_str(cond)}" + "\n\n\n"
                        + f"Reflection:\n{reflection}"
            )]
            cond = await a_call_agent("evolve", msg_evolve, to_json = True)
            cond['Ref'] = ref
            
            msg_reflect.extend([
                AIMessage(content = f"Reflection:\n{reflection}"),
                HumanMessage(content = f"Refined LC-MS Condition:\n{json_to_str(cond)}")
            ])

        print(f"::: reflect and evolve agents refined the condition {key} on {compound_attr['IUPAC_Name']}.")
        
        return cond

    async def compound_generate_refine(compound_attr, agent_name, max_iter):

        # Generation or Search Agent
        msg_init = [HumanMessage(
            content = f"Compound:\n{json_to_str(compound_attr)}" + "\n\n\n"
                    + f"Constraints:\n{constraint}"
        )]   
        cond_ = await a_call_agent(agent_name, msg_init, to_json = True)
        print(f"::: {agent_name} agent generated {len(cond_)} conditions for {compound_attr['IUPAC_Name']}.")

        # Reflection and Evolution Agents
        keys = cond_.keys()
        results = await asyncio.gather(
            *(compound_refine(compound_attr, cond_[k], k, max_iter) for k in keys)
        )
        
        for k, v in zip(keys, results):
            cond_[k] = v
        
        return cond_

    async def compound_main(compound_attr):

        if config['api_use']['wiley_api'] or config['api_use']['elsevier_api'] or config['api_use']['springernature_api']:
            cond_G, cond_S, cond_E = await asyncio.gather(
                compound_generate_refine(compound_attr, "generate", max_iter),
                compound_generate_refine(compound_attr, "web_search", max_iter),
                compound_generate_refine(compound_attr, "scholarly_search", max_iter)
            )
            
            return cond_G | cond_S | cond_E

        else:
            cond_G, cond_S = await asyncio.gather(
                compound_generate_refine(compound_attr, "generate", max_iter),
                compound_generate_refine(compound_attr, "web_search", max_iter)
            )
            #cond_G = await compound_generate_refine(compound_attr, "generate")
            
            return cond_G | cond_S

    print('\n--- Stage 1. Compound-Level Analysis')
    
    conds = await asyncio.gather(
        *[compound_main(attr) for attr in reaction_attr.values()]
    )
    
    compound_cond = dict(zip(reaction_attr.keys(), conds))
    
    for key in compound_cond.keys():
        compound_cond[key] = {f"{key[0]}{key.split(' ')[1]}_{k}": v for k, v in compound_cond[key].items()}

    return compound_cond

async def reaction_level_analysis(reaction_attr, compound_cond, constraint):
    
    def cond_to_block(cond):
        return "\n\n".join([f"{i+1}. Condition ID: {c_id}\n{json_to_str(c_cond)}" for i, (c_id, c_cond) in enumerate(cond.items())]) 
    
    print('\n--- Stage 2. Reaction-Level Analysis')

    # Integration Agent
    cond_blocks = [f"LC-MS Conditions for {key} [{key[0]}{key.split(' ')[1]}] ({reaction_attr[key]['IUPAC_Name']}):\n\n{cond_to_block(cond)}" for (key, cond) in compound_cond.items()]

    msg_integrate = [HumanMessage(
        content = f"Reaction:\n{json_to_str(reaction_attr)}" + "\n\n\n"
                + f"Constraints:\n{constraint}" + "\n\n\n"
                + "\n\n\n".join(cond_blocks)
    )]
    
    reaction_cond = call_agent("integrate", msg_integrate, to_json = True)
    print(f"::: integrate agent generated {len(reaction_cond)} conditions")
    
    # Reflection and Evolution Agents    
    reaction_cond = await reaction_level_update(reaction_attr, reaction_cond, constraint)
    
    return reaction_cond


async def reaction_level_update(reaction_attr, reaction_cond, constraint, max_iter = 2):
    
    async def reaction_refine(reaction_attr, cond, key, max_iter):

        ref = cond['Ref']
        msg_reflect = [HumanMessage(
            content = f"Reaction:\n{json_to_str(reaction_attr)}" + "\n\n\n"
                    + f"Constraints:\n{constraint}" + "\n\n\n"
                    + f"LC-MS Condition:\n{json_to_str(cond)}"
        )]
          
        for i in range(max_iter):
            reflection = await a_call_agent("reflect", msg_reflect, to_json = False)
            reflection = str(reflection)
            
            #print(i+1, len(reflection), reflection[:50])
            if len(reflection) < 10:
                print(f"::: (reflection iter {i+1}) No reflection needed for the condition {key}.")
                break
            
            msg_evolve = [HumanMessage(
                content = f"Reaction:\n{json_to_str(reaction_attr)}" + "\n\n\n"
                        + f"Constraints:\n{constraint}" + "\n\n\n"
                        + f"LC-MS Condition:\n{json_to_str(cond)}" + "\n\n\n"
                        + f"Reflection:\n{reflection}"
            )]
            cond = await a_call_agent("evolve", msg_evolve, to_json = True)
            cond['Ref'] = ref
            
            msg_reflect.extend([
                AIMessage(content = f"Reflection:\n{reflection}"),
                HumanMessage(content = f"Refined LC-MS Condition:\n{json_to_str(cond)}")
            ])
        
        print(f"::: reflect and evolve agents refined the condition {key}.")
        
        return cond

    print('\n--- Stage 2-1. Reaction-Level Update')

    # Reflection and Evolution Agents
    keys = reaction_cond.keys()
    results = await asyncio.gather(
        *(reaction_refine(reaction_attr, reaction_cond[k], k, max_iter) for k in keys)
    )
    
    for k, v in zip(keys, results):
        reaction_cond[k] = v
    
    # Meta-Review Agent
    msg_review = [HumanMessage(
        content = f"Reaction:\n{json_to_str(reaction_attr)}" + "\n\n\n"
                + f"Constraints:\n{constraint}" + "\n\n\n"
                + f"LC-MS Conditions:\n{json_to_str(reaction_cond)}"
    )]
    reaction_cond_score = call_agent("metareview", msg_review, to_json = True)
    print(f"::: Meta-Review & Ranking is done!")
    
    for key in reaction_cond_score.keys():
        reaction_cond[key]['Notes'] += " " + reaction_cond_score[key]['Notes']
        reaction_cond_score[key] = reaction_cond_score[key] | reaction_cond[key]
        
    reaction_cond = dict(
        sorted(list(reaction_cond_score.items()), key=lambda x: x[1]['Rank'])
    )
    
    return reaction_cond


def create_report(reaction_attr, compound_cond, reaction_cond, constraint, top_k = 3, css = "github-markdown.css"):

    def ref_to_link(ref):
        ref = ref.strip()
        if ref.startswith("http"):
            return f"[link]({ref})"
        else:
            return ref

    print('\n--- Stage 3. Report Generation')
    reaction_cond = dict(
        sorted(list(reaction_cond.items()), key=lambda x: x[1]['Rank'])[:top_k]
    )
    compound_cond_flatten = {k: v for d in compound_cond.values() for k, v in d.items()}

    # Reporting Agent
    msg_report = [HumanMessage(
        content = f"Reaction:\n{json_to_str(reaction_attr)}" + "\n\n\n"
                + f"Constraints:\n{constraint}" + "\n\n\n"
                + f"LC-MS Conditions:\n{json_to_str(reaction_cond)}"
    )]
    summary_text = call_agent("report", msg_report, to_json = False)
    print(f"::: Report is generated!")

    out = []
    out.append('LC-MS Condition Recommendation Report')
    out.append('=============\n')
    
    out.append('\n### Target Reaction\n')
    out.append("| | " + " | ".join(f"{k} [{k[0]}{k.split(' ')[1]}]" for k in reaction_attr.keys()) + " |")
    out.append("| --- | " + " | ".join("---" for _ in reaction_attr.keys()) + " |")
    for col in ['IUPAC_Name', 'SMILES', 'Exact_Mass']:
        out.append(f"| <b>{col.replace('_', ' ')}</b> | " + " | ".join(str(reaction_attr[k][col]).replace(';', ';<br>') for k in reaction_attr.keys()) + " |")
    out.append('\n### Constraints\n')
    out.append(('> - ' + constraint.strip().replace('\n','\n> - ')).replace('> - -', '> -'))
    out.append('\n---\n')
    
    out.append('\n## Recommended LC-MS Conditions\n')
    out.append("| | " + " | ".join(f"Condition {k} (Rank {str(reaction_cond[k]['Rank'])})" for k in reaction_cond.keys()) + " |")
    out.append("| --- | " + " | ".join("---" for _ in reaction_cond.keys()) + " |")
    for col in ['Retention_Time', 'Column', 'Mobile_Phase', 'Flow_Rate', 'Injection_Volume', 'Elution', 'Detector', 'MS_Parameters']:
        out.append(f"| <b>{col.replace('_', ' ')}</b> | " + " | ".join(str(reaction_cond[k][col]).replace(';', ';<br>') for k in reaction_cond.keys()) + " |")
    out.append("| <b>Ref</b> | " + " | ".join(";<br>".join([f"{idx.strip()} ({ref_to_link(compound_cond_flatten[idx.strip()]['Ref'])})" for idx in reaction_cond[k]["Ref"].split(",")]) for k in reaction_cond.keys()) + " |")
    out.append('\n---\n')
    
    out.append(summary_text)
    out.append('\n---\n')
    
    md_content = '\n'.join(out)
    
    with open(os.path.join(config['misc']['save_dir'], css), "r", encoding="utf-8") as f:
        css_text = f.read()
    
    md_html = f"""
    <html>
    <head>
    <style>
    {css_text}
    </style>
    </head>
    <body>
    <div class="markdown-body">
    {markdown.markdown(md_content, extensions=["tables", "fenced_code", "codehilite"])}
    </div>
    </body>
    </html>
    """.strip()

    md_html.replace('<a href', '<a target="_blank" href')# link open in new tab

    print(f"::: Report HTML is generated!")

    return summary_text, md_html