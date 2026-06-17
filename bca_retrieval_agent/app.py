"""
BCA Retrieval and Intelligence Agent — Streamlit UI.

A retrieval, indexing, and benchmarking system for transportation
Benefit-Cost Analysis documents. This is NOT a chatbot or BCA generator.
"""

import json
import logging
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from agents.classifier_agent import ClassifierAgent
from agents.crawler_agent import CrawlerAgent
from agents.metadata_agent import MetadataAgent
from agents.packaging_agent import PackagingAgent
from agents.search_agent import SearchAgent
from config import (
    GRANT_PROGRAMS,
    OPENAI_API_KEY,
    ANTHROPIC_API_KEY,
    PROJECT_TYPES,
    SERPAPI_KEY,
    BING_SEARCH_API_KEY,
    US_STATES,
    ensure_directories,
)
from core.database import Database
from schemas.run_schema import RunConfig, RunLog

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

ensure_directories()

st.set_page_config(
    page_title="BCA Retrieval Agent",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Session state initialization
DEFAULTS = {
    "run_id": None,
    "run_log": None,
    "candidate_urls": [],
    "documents": [],
    "classifications": [],
    "metadata": [],
    "exports": {},
    "search_complete": False,
}
for key, val in DEFAULTS.items():
    if key not in st.session_state:
        st.session_state[key] = val


def _api_status() -> dict[str, bool]:
    return {
        "SerpAPI": bool(SERPAPI_KEY),
        "Bing Search": bool(BING_SEARCH_API_KEY),
        "OpenAI": bool(OPENAI_API_KEY),
        "Anthropic": bool(ANTHROPIC_API_KEY),
    }


# --- Sidebar ---
with st.sidebar:
    st.title("BCA Retrieval Agent")
    st.caption("Transportation Benefit-Cost Analysis document retrieval & indexing")

    st.divider()
    st.subheader("API Status")
    for name, active in _api_status().items():
        st.write(f"{'🟢' if active else '⚪'} {name}")

    if not any(_api_status().values()):
        st.info("No search/LLM APIs configured. Direct URL and crawl modes still work.")

    st.divider()
    st.subheader("Search Modes")
    st.markdown("""
    - **General Web** — Search public web (SerpAPI → Bing → DuckDuckGo)
    - **Targeted Crawl** — Crawl a specific website for BCA links
    - **Direct URL** — Paste URLs to download directly
    """)

    if st.session_state.run_id:
        st.divider()
        st.subheader("Current Run")
        st.code(st.session_state.run_id)


# --- Main UI ---
st.header("BCA Retrieval and Intelligence Agent")
st.markdown(
    "Search, download, classify, and index public transportation "
    "**Benefit-Cost Analysis** documents."
)

col1, col2 = st.columns([2, 1])

with col1:
    search_query = st.text_area(
        "Search Query or URL List",
        placeholder='e.g. "Find bridge replacement BCAs" or paste URLs (one per line)',
        height=100,
    )

with col2:
    target_domain = st.text_input(
        "Target Website / Domain (optional)",
        placeholder="e.g. transportation.gov or https://www.mdot.maryland.gov",
    )

    search_mode = st.selectbox(
        "Search Mode",
        ["direct_url", "general_web", "targeted_crawl"],
        format_func=lambda x: {
            "direct_url": "Direct URL List",
            "general_web": "General Web Search",
            "targeted_crawl": "Targeted Website Crawl",
        }[x],
    )

    max_results = st.number_input("Max Results", min_value=1, max_value=100, value=20)

file_types = st.multiselect(
    "File Types",
    ["pdf", "docx", "xlsx", "xlsm", "html"],
    default=["pdf", "docx", "xlsx", "html"],
)

filter_cols = st.columns(3)
with filter_cols[0]:
    grant_filter = st.selectbox("Grant Program Filter", ["(none)"] + GRANT_PROGRAMS)
with filter_cols[1]:
    project_filter = st.selectbox("Project Type Filter", ["(none)"] + PROJECT_TYPES)
with filter_cols[2]:
    state_filter = st.selectbox("State Filter", ["(none)"] + US_STATES)

package_name = st.text_input(
    "Download Package Name (optional)",
    placeholder="bca_retrieval_run_custom",
)

st.divider()

btn_cols = st.columns(5)

with btn_cols[0]:
    run_search_btn = st.button("🔍 Run Search", type="primary", use_container_width=True)
with btn_cols[1]:
    classify_btn = st.button("🏷️ Classify Documents", use_container_width=True)
with btn_cols[2]:
    metadata_btn = st.button("📋 Extract Metadata", use_container_width=True)
with btn_cols[3]:
    export_btn = st.button("📤 Export Results", use_container_width=True)
with btn_cols[4]:
    zip_btn = st.button("📦 Download ZIP", use_container_width=True)


def _build_config() -> RunConfig:
    direct_urls = []
    if search_mode == "direct_url":
        for line in search_query.strip().splitlines():
            url = line.strip().rstrip(",")
            if url.startswith("http"):
                direct_urls.append(url)

    return RunConfig(
        query=search_query,
        target_domain=target_domain or None,
        search_mode=search_mode,
        max_results=max_results,
        file_types=file_types,
        grant_program_filter=grant_filter if grant_filter != "(none)" else None,
        project_type_filter=project_filter if project_filter != "(none)" else None,
        state_filter=state_filter if state_filter != "(none)" else None,
        package_name=package_name or None,
        direct_urls=direct_urls,
    )


# --- Actions ---
if run_search_btn:
    if not search_query.strip():
        st.error("Please enter a search query or URL list.")
    else:
        config = _build_config()
        with st.spinner("Searching for BCA documents..."):
            search_agent = SearchAgent()
            run_id, run_log, results = search_agent.run(config)

            st.session_state.run_id = run_id
            st.session_state.run_log = run_log
            st.session_state.candidate_urls = results
            st.session_state.search_complete = True

            if results:
                urls = [(r.url, r.title) for r in results]
                crawler = CrawlerAgent()
                documents, errors = crawler.download_and_extract(run_id, urls, run_log)
                st.session_state.documents = documents
                st.session_state.run_log = run_log

                if errors:
                    st.warning(f"{len(errors)} download(s) failed.")
            else:
                st.warning("No candidate URLs found.")

        st.success(f"Search complete. Run ID: {run_id}")

if classify_btn:
    if not st.session_state.run_id:
        st.error("Run a search first.")
    else:
        with st.spinner("Classifying documents..."):
            agent = ClassifierAgent()
            run_log = st.session_state.run_log or RunLog(
                run_id=st.session_state.run_id,
                start_time=datetime.utcnow().isoformat(),
            )
            results = agent.classify_run(
                st.session_state.run_id, run_log, use_llm=bool(OPENAI_API_KEY or ANTHROPIC_API_KEY)
            )
            st.session_state.classifications = results
            st.session_state.run_log = run_log
        st.success(f"Classified {len(results)} document(s).")

if metadata_btn:
    if not st.session_state.run_id:
        st.error("Run a search and classify first.")
    else:
        with st.spinner("Extracting metadata..."):
            agent = MetadataAgent()
            run_log = st.session_state.run_log or RunLog(
                run_id=st.session_state.run_id,
                start_time=datetime.utcnow().isoformat(),
            )
            metadata = agent.extract_run(
                st.session_state.run_id,
                run_log,
                use_llm=bool(OPENAI_API_KEY or ANTHROPIC_API_KEY),
            )
            st.session_state.metadata = metadata
            st.session_state.run_log = run_log
        st.success(f"Extracted metadata from {len(metadata)} document(s).")

if export_btn or zip_btn:
    if not st.session_state.run_id:
        st.error("No run to export.")
    else:
        with st.spinner("Creating exports..."):
            agent = PackagingAgent()
            run_log = st.session_state.run_log or RunLog(
                run_id=st.session_state.run_id,
                start_time=datetime.utcnow().isoformat(),
            )
            exports = agent.export_run(
                st.session_state.run_id,
                package_name=package_name or None,
                run_log=run_log,
            )
            st.session_state.exports = exports
            st.session_state.run_log = run_log
        st.success("Exports created.")

# --- Display Sections ---
st.divider()

tab_urls, tab_docs, tab_class, tab_meta, tab_exports = st.tabs([
    "Candidate URLs",
    "Downloaded Documents",
    "Classifications",
    "Metadata",
    "Downloads",
])

with tab_urls:
    st.subheader("Candidate URLs Found")
    if st.session_state.candidate_urls:
        url_data = [
            {"URL": r.url, "Title": r.title or "", "Source": r.source}
            for r in st.session_state.candidate_urls
        ]
        st.dataframe(pd.DataFrame(url_data), use_container_width=True)
        st.caption(f"Total: {len(url_data)}")
    else:
        st.info("No URLs yet. Run a search to discover candidate documents.")

with tab_docs:
    st.subheader("Downloaded Documents")
    if st.session_state.run_id:
        db = Database()
        docs = db.get_documents_by_run(st.session_state.run_id)
        if docs:
            st.dataframe(pd.DataFrame(docs), use_container_width=True)
        else:
            st.info("No documents downloaded yet.")
    else:
        st.info("No active run.")

with tab_class:
    st.subheader("BCA Classification Results")
    if st.session_state.run_id:
        db = Database()
        classifications = db.get_classifications_by_run(st.session_state.run_id)
        if classifications:
            display_cols = [
                "title", "source_url", "classification", "confidence", "reason"
            ]
            df = pd.DataFrame(classifications)
            available = [c for c in display_cols if c in df.columns]
            st.dataframe(df[available], use_container_width=True)

            definite = sum(1 for c in classifications if c.get("classification") == "Definite BCA")
            likely = sum(1 for c in classifications if c.get("classification") == "Likely BCA")
            m1, m2, m3 = st.columns(3)
            m1.metric("Definite BCAs", definite)
            m2.metric("Likely BCAs", likely)
            m3.metric("Total Classified", len(classifications))
        else:
            st.info("No classifications yet. Click 'Classify Documents'.")
    else:
        st.info("No active run.")

with tab_meta:
    st.subheader("Extracted Metadata")
    if st.session_state.run_id:
        db = Database()
        metadata_list = db.get_metadata_by_run(st.session_state.run_id)
        if metadata_list:
            rows = [m.to_flat_dict() for m in metadata_list]
            st.dataframe(pd.DataFrame(rows), use_container_width=True)
        else:
            st.info("No metadata yet. Classify documents, then click 'Extract Metadata'.")
    else:
        st.info("No active run.")

with tab_exports:
    st.subheader("Export Downloads")
    exports = st.session_state.exports
    if exports:
        for label, path in exports.items():
            if Path(path).exists():
                with open(path, "rb") as f:
                    ext = Path(path).suffix
                    mime = {
                        ".csv": "text/csv",
                        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        ".zip": "application/zip",
                    }.get(ext, "application/octet-stream")
                    st.download_button(
                        f"Download {label.upper()} ({Path(path).name})",
                        data=f.read(),
                        file_name=Path(path).name,
                        mime=mime,
                        key=f"dl_{label}",
                    )
    else:
        st.info("No exports yet. Click 'Export Results' or 'Download ZIP'.")

# Run log summary
if st.session_state.run_log:
    with st.expander("Run Log"):
        st.json(st.session_state.run_log.to_dict() if hasattr(st.session_state.run_log, "to_dict") else st.session_state.run_log)
