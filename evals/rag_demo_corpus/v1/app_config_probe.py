"""Read effective Settings in a subprocess environment without exposing secrets."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import json
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[3]
PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"
BACKEND = ROOT / "backend"


def probe_config(environment: dict[str, str]) -> dict:
    script = """
import json
from app.core.config import Settings
s=Settings()
print(json.dumps({
 'search_top_k_max':s.search_top_k_max,
 'llm_provider':s.llm_provider,
 'llm_host':urlparse(s.llm_base_url).hostname if s.llm_base_url else None,
 'rag_configuration':{
  'top_k':s.rag_top_k_default,
  'candidate_expansion':min(s.search_top_k_max,max(s.rag_top_k_default*3,s.rag_top_k_default)),
  'min_score':s.rag_min_score,
  'max_sources':s.rag_max_sources,
  'max_chunk_chars':s.rag_max_chunk_chars,
  'max_context_chars':s.rag_max_context_chars,
  'query_rewrite_enabled':s.rag_query_rewrite_enabled,
  'history_messages':s.rag_history_messages,
  'history_chars':s.rag_history_chars
 }
}))
"""
    script = "from urllib.parse import urlparse\n" + script
    result = subprocess.run(
        [str(PYTHON), "-c", script], cwd=BACKEND, env=environment,
        check=True, capture_output=True, text=True,
    )
    return json.loads(result.stdout)


if __name__ == "__main__":
    print(json.dumps(probe_config(os.environ.copy()), ensure_ascii=False, indent=2))
