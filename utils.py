import requests, time, random, os, re
import json


def str_to_json(s):

    idx_l = s.find("{")
    idx_r = s.rfind("}")

    return json.loads(
        s[idx_l:idx_r+1]
    )  
    
def json_to_str(x):
    return json.dumps(
        x,
        indent=2,
        ensure_ascii=False
    )

# output schema for each agent
SCHEMA = {
    "generate": [
        "Ref","Column","Mobile_Phase","Flow_Rate","Injection_Volume",
        "Elution", "Detector", "MS_Parameters", "Retention_Time", "Notes"
    ],
    "web_search": [
        "Ref","Column","Mobile_Phase","Flow_Rate","Injection_Volume",
        "Elution", "Detector", "MS_Parameters", "Retention_Time", "Notes"
    ],
    "scholarly_search": [
        "Ref","Column","Mobile_Phase","Flow_Rate","Injection_Volume",
        "Elution", "Detector", "MS_Parameters", "Retention_Time", "Notes"
    ],
    "integrate": [
        "Ref","Column","Mobile_Phase","Flow_Rate","Injection_Volume",
        "Elution", "Detector", "MS_Parameters", "Retention_Time", "Notes"
    ],
    "evolve": [
        "Ref","Column","Mobile_Phase","Flow_Rate","Injection_Volume",
        "Elution", "Detector", "MS_Parameters", "Retention_Time", "Notes"
    ],

    "metareview": ["Rank", "Notes"],
}

def check_output(agent_name, obj):
    required = SCHEMA.get(agent_name)
    if required is None:
        return True 

    if not isinstance(obj, dict) or len(obj) == 0:
        raise ValueError("empty or invalid output")

    # dict[id -> dict]
    if all(isinstance(v, dict) for v in obj.values()):
        for v in obj.values():
            for key in required:
                if key not in v:
                    raise ValueError("Schema Error")
        return True

    # single dict
    for key in required:
        if key not in obj:
            raise ValueError("Schema Error")

    return True
