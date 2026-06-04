# Educational Content Curation MVP

Local JSON-first proof of concept for the frozen architecture.

## Commands

Use Command Prompt from `D:\Internship`:

```cmd
set PYTHONPATH=src && python -m edu_curator.cli validate-seed
set PYTHONPATH=src && python -m edu_curator.cli ingest
set PYTHONPATH=src && python -m edu_curator.cli chunk
set PYTHONPATH=src && python -m edu_curator.cli map-topic
set PYTHONPATH=src && python -m edu_curator.cli check-llm-config
set PYTHONPATH=src && python -m edu_curator.cli list-models
set PYTHONPATH=src && python -m edu_curator.cli test-llm
set PYTHONPATH=src && python -m edu_curator.cli extract
set PYTHONPATH=src && python -m edu_curator.cli resolve
```

Current local MVP flow:

```text
sources.json
-> documents.json
-> content_chunks.json
-> source_to_topic_mapping.json
-> fact_extractions.json
-> topic_knowledge.json
```

If a website blocks direct fetching, save its readable text as `.txt` or `.md`
under `data/raw/sources/`, then set that source's `local_path` in
`data/seed/sources.json`.
