from chem_utils import *
from doc_utils import *
import threading

from langchain.tools import tool

from tavily import TavilyClient


import yaml
with open("config.yaml", "r", encoding="utf-8") as f:
    config = yaml.safe_load(f)


@tool
def smiles_expand(smiles: str):
    """Return the IUPAC name and key chemical properties for a compound given its SMILES string."""

    return attribute_smi(smiles)

@tool
def iupac_expand(iupac_name: str):
    """Return the SMILES representation and key chemical properties for a compound given its IUPAC name."""

    return attribute_iupac(iupac_name)


tavily_client = TavilyClient()

@tool
def web_search_tool(query: str):
    """Search the web to retrieve LC–MS related content for the given query."""

    search_result = tavily_client.search(
        query = query,
        max_results = 5,
        search_depth = "advanced"
    )['results']
    
    #print(query, search_result)
    return search_result


google_search_api = GoogleSearchAPIWrapper()
google_search_api_lock = threading.Lock()

def google_search(query: str, k = 5) -> list:
    time.sleep(random.uniform(0, 1))
    return google_search_api.results(query, num_results = k)

@tool
def scholarly_search_tool(query: str):
    """Search scholarly articles containing LC–MS related content for the given query."""

    with google_search_api_lock:
        search_result = google_search(query)
        
    for item in search_result:
        if "link" in item:
            item["url"] = item.pop("link")
    
    #print(query, search_result)
    return search_result

@tool
def extraction_tool(url: str, query: str):
    """Extract LC–MS-related context associated with the given query from the provided URL."""

    # Google CSE
    ## link.springer.com/article/*
    ## nature.com/articles/*
    ## *.onlinelibrary.wiley.com/doi/*
    ## sciencedirect.com/science/article/* 
    if config['api_use']['wiley_api'] and "onlinelibrary.wiley.com/" in url:
        part = url.split('/')
        doi = normalize_doi(f"{part[-2]}/{part[-1]}")
        doi, text = wiley_extract_from_doi(doi)
    elif config['api_use']['elsevier_api'] and "sciencedirect.com/" in url:
        pii = normalize_doi(url.split('/')[-1])
        doi, text = elsevier_extract_from_pii(pii)
    elif config['api_use']['springernature_api'] and "nature.com/articles/" in url:
        doi = normalize_doi("10.1038/" + url.split('/')[-1])
        doi, text = sn_extract_from_doi(doi)
    elif config['api_use']['springernature_api'] and "link.springer.com/article/" in url:
        part = url.split('/')
        doi = normalize_doi(f"{part[-2]}/{part[-1]}")
        doi, text = sn_extract_from_doi(doi)
    else:
        doi, text = None, None

    # If Scholary APIs failed to extract, use Tavily Extraction API
    if not doi or not text:
        doi = 'tavily'
        text = tavily_client.extract(
            urls = [url],
            chunks_per_source = 3,
            extract_depth = "advanced"
        )['results'][0]['raw_content']

    if not doi or not text:
        return {}

    #print('EXTRACT:', doi, url, text[:100])
    
    chunks = get_chunk(text, query)
    if not chunks:
        return {"url": url, "content": "failed to extract"}
    else:
        print(f"@@@ Extraction Tool Usage: extracted chunks from [{doi}]:[{url}] for query [{query}]")
        return {"url": url, "content": chunks}  #f"https://doi.org/{doi}"