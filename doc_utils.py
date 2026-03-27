import requests, time, random, os, re
import json
import numpy as np

from rapidfuzz import fuzz
from itertools import zip_longest

from bs4 import BeautifulSoup

import pymupdf.layout
import pymupdf4llm
import yaml

from langchain.tools import BaseTool
from pydantic import BaseModel, ConfigDict, model_validator
from typing import Any, Dict, List, Optional

from elsapy.elsclient import ElsClient
from elsapy.elsdoc import FullDoc
from wiley_tdm import TDMClient
import springernature_api_client.tdm as tdm

from dotenv import load_dotenv
load_dotenv()

with open("config.yaml", "r", encoding="utf-8") as f:
    config = yaml.safe_load(f)


#from langchain_google_community import GoogleSearchAPIWrapper
class GoogleSearchAPIWrapper(BaseModel):
    """Wrapper for Google Custom Search API.

    Performs web searches using Google Custom Search API and returns results
    with snippets, titles, and links.

    !!! note "Setup Required"

        1. Enable [Custom Search API](https://console.cloud.google.com/apis/library/customsearch.googleapis.com)
        2. Create API key in [Google Cloud Console](https://console.cloud.google.com/apis/credentials)
        3. Create custom search engine at [Programmable Search Engine](https://programmablesearchengine.google.com)
        4. Set `GOOGLE_API_KEY` and `GOOGLE_CSE_ID` environment variables
    """

    search_engine: Any = None

    google_api_key: Optional[str] = None
    """Google API key for authentication."""

    google_cse_id: Optional[str] = None
    """Custom Search Engine ID."""

    k: int = 10
    """Number of results to return."""

    siterestrict: bool = False
    """Whether to restrict search to specific sites."""

    model_config = ConfigDict(
        extra="forbid",
    )

    def _google_search_results(self, search_term: str, **kwargs: Any) -> List[dict]:
        cse = self.search_engine.cse()
        if self.siterestrict:
            cse = cse.siterestrict()
        res = cse.list(q=search_term, cx=self.google_cse_id, **kwargs).execute()
        return res.get("items", [])

    @model_validator(mode="before")
    @classmethod
    def validate_environment(cls, values: Dict) -> Any:
        """Validate that api key and python package exists in environment."""
        google_api_key = get_from_dict_or_env(
            values, "google_api_key", "GOOGLE_API_KEY"
        )
        values["google_api_key"] = google_api_key

        google_cse_id = get_from_dict_or_env(values, "google_cse_id", "GOOGLE_CSE_ID")
        values["google_cse_id"] = google_cse_id

        try:
            from googleapiclient.discovery import build  # type: ignore[import]

        except ImportError:
            raise ImportError(
                "google-api-python-client is not installed. "
                "Please install it with `pip install langchain-google-community`"
            )

        service = build("customsearch", "v1", developerKey=google_api_key)
        values["search_engine"] = service

        return values

    def run(self, query: str) -> str:
        """Run query through Google Search and parse result."""
        snippets = []
        results = self._google_search_results(query, num=self.k)
        if len(results) == 0:
            return "No good Google Search Result was found"
        for result in results:
            if "snippet" in result:
                snippets.append(result["snippet"])

        return " ".join(snippets)

    def results(
        self,
        query: str,
        num_results: int,
        search_params: Optional[Dict[str, str]] = None,
    ) -> List[Dict]:
        """Run query through Google Search and return metadata.

        Args:
            query: The query to search for.
            num_results: Number of results to return.
            search_params: Additional search parameters.

        Returns:
            Search results with snippet, title, and link for each result.
        """
        metadata_results = []
        results = self._google_search_results(
            query, num=num_results, **(search_params or {})
        )
        if len(results) == 0:
            return [{"Result": "No good Google Search Result was found"}]
        for result in results:
            metadata_result = {
                "title": result["title"],
                "link": result["link"],
            }
            if "snippet" in result:
                metadata_result["snippet"] = result["snippet"]
            metadata_results.append(metadata_result)

        return metadata_results

def get_from_dict_or_env(
    data: Dict[str, Any], key: str, env_key: str, default: Optional[str] = None
) -> str:
    """Get a value from a dictionary or an environment variable."""
    if key in data and data[key]:
        return data[key]
    else:
        return get_from_env(key, env_key, default=default)

def get_from_env(key: str, env_key: str, default: Optional[str] = None) -> str:
    """Get a value from a dictionary or an environment variable."""
    if env_key in os.environ and os.environ[env_key]:
        return os.environ[env_key]
    elif default is not None:
        return default
    else:
        raise ValueError(
            f"Did not find {key}, please add an environment variable"
            f" `{env_key}` which contains it, or pass"
            f" `{key}` as a named parameter."
        )


if config['api_use']['elsevier_api']:
    
    elsevier_tdm = ElsClient(os.getenv("ELSEVIER_API_KEY"))
    
    def elsevier_extract_from_pii(pii, n_retry = 2):

        doc = FullDoc(sd_pii = pii)
        
        for attempt in range(1, n_retry + 1):
            #time.sleep(random.uniform(0, 3))
            read_status = doc.read(elsevier_tdm)
            if read_status: break
        
        if read_status:
            content = doc.data     
            doi = content['coredata']['prism:doi']
            text = content['originalText']
            
            if isinstance(text, str):
                return doi, text
            
            else:
                print('*** ERROR(parse): elsevier pii', pii)
                return None, None

        else:
            print('*** ERROR(load): elsevier pii', pii)
            return None, None


if config['api_use']['wiley_api']:
    
    wiley_tdm = TDMClient()

    def wiley_extract_from_doi(doi, n_retry = 2):
        
        for attempt in range(1, n_retry + 1):
            #time.sleep(random.uniform(1, 3))
            file = wiley_tdm.download_pdf(doi)
            if file.path: break

        if file.path:
            try:
                text = parse_pdf(str(file.path))
                return doi, text

            except Exception as e:
                print('*** ERROR(parse): wiley doi', doi, '-', e)
                return None, None 

        else:
            print('*** ERROR(load): wiley doi', doi)
            return None, None 


if config['api_use']['springernature_api']:
    
    sn_tdm = tdm.TDMAPI(api_key=os.getenv("SN_API_KEY"))
    
    def sn_extract_from_doi(doi, n_retry = 2):

        for attempt in range(1, n_retry + 1):
            response = sn_tdm.search(q=f"doi:{doi}", p=1, s=1)
            if response: break
        
        if response and "<total>0</total>" not in response:
            try:
                text = parse_xml(response)
                return doi, text

            except Exception as e:
                print('*** ERROR(parse): springernature doi', doi, '-', e)
                return None, None 
            
        else:
            print('*** ERROR(load): springernature doi', doi)
            return None, None 


def normalize_doi(doi: str):
    doi = doi.split("?", 1)[0]
    doi = doi.split("#", 1)[0]
    
    return doi

 
def parse_pdf(file_path: str):
    
    return pymupdf4llm.to_markdown(pymupdf.open(file_path))


def parse_xml(xml: str):
    
    return BeautifulSoup(xml, "xml").get_text()


keywords = ['mobile phase','column','buffer','additive','flow rate','retention time','eluent','elution','separation','detection','detector','lc ','lc-','lc/','v/v','gradient','isocratic']

def get_chunk(text, query, chunk_size=100, stride=50, padding=25, thr1=200, thr2=800):
    
    def _fuzzy_match_score(query: str, text: str) -> float:
        score = fuzz.partial_ratio(query.lower(), text.lower()) / 100.0

        return score

    def _merge_intervals(intervals, min_val=0, max_val=None):
        intervals.sort(key=lambda x: x[0])
        
        merged = [intervals[0]]
        for current in intervals[1:]:
            last = merged[-1]
            if current[0] <= last[1]:
                merged[-1] = (last[0], max(last[1], current[1]))
            else:
                merged.append(current)

        limited = []
        for start, end in merged:
            start = max(start, min_val)
            end = min(end, max_val)
            if start <= end: limited.append((start, end))
                
        return limited
    
    words = [w for w in text.split() if len(w) < 50]

    chunk_indices = []
    for start in range(0, max(1, len(words) - chunk_size + stride), stride):
        chunk = " ".join(words[start:start + chunk_size]).lower()
        
        chunk_score_1 = _fuzzy_match_score(query, chunk)
        chunk_score_2 = sum([chunk.count(k) > 0 for k in keywords])
        
        chunk_indices.append([start, chunk_score_1+1e-2*chunk_score_2, chunk_score_2+1e-2*chunk_score_1])

    chunk_indices = np.array(chunk_indices)
    max_score_1 = np.max(chunk_indices[:,1])
    max_score_2 = np.max(chunk_indices[:,2])
    #print(max_score_1, max_score_2)
    if max_score_1 < 0.5 or max_score_2 < 5:
        return None 
    
    sorted_1 = chunk_indices[chunk_indices[:,1].argsort()[::-1], 0].astype(int)
    sorted_2 = chunk_indices[chunk_indices[:,2].argsort()[::-1], 0].astype(int)

    chunk_intervals = []
    for i in sorted_1:
        chunk_intervals.append((i-padding, i+chunk_size+padding))
        chunk_intervals = _merge_intervals(chunk_intervals, 0, len(words))
        if sum([b-a for (a, b) in chunk_intervals]) > thr1:
            break
        
    for i in sorted_2:
        chunk_intervals.append((i-padding, i+chunk_size+padding))
        chunk_intervals = _merge_intervals(chunk_intervals, 0, len(words))
        if sum([b-a for (a, b) in chunk_intervals]) > thr2:
            break    
    
    return '\n\n'.join(['### CHUNK %d'%(i+1)+'\n'+' '.join(words[a:b]) for i, (a, b) in enumerate(chunk_intervals)])