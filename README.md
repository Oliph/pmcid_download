# pmcid_download

A biomedical data extraction pipeline that downloads open-access scientific articles from [Europe PMC](https://europepmc.org/), filters for human-focused research, parses full-text XML, and stores structured metadata in a SQLite database.

## Repository Structure

```
pmcid_download/
├── config/
│   └── config.yaml                    # Main configuration file
├── pmcid_dl/
│   ├── dl_pmcids.py                   # Download PMCID archive and filter by species
│   ├── parseXML.py                    # Fetch, parse XML and store in database
│   ├── explore_xml_tags.py            # XML structure exploration utility
│   ├── tags_exploration.ipynb         # Jupyter notebook for exploratory analysis
│   └── utils/
│       ├── retrieve_data_from_xml.py  # XML parsing classes (XmlParser, DynamicXmlParser)
│       ├── record_data_to_db.py       # SQLite database operations
│       └── relevant_tags.py           # Section type mappings
├── LICENSE                            # Apache 2.0
└── .gitignore
```

## Pipeline

The pipeline runs in three phases:

### Phase 1 — Article Discovery (`dl_pmcids.py`)

1. Downloads the full PMCID archive from Europe PMC's FTP (gzipped list of all open-access article IDs).
2. Queries the Europe PMC Annotations API for species annotations on each article (concurrent threading).
3. Filters articles whose species match human-related terms (`human`, `humans`, `man`, `homo sapiens`, `h. sapiens`, `homo_sapiens`).
4. Outputs `data/pmcid_species.txt` (all species annotations) and `data/pmcid_humans.txt` (filtered human PMCIDs).

### Phase 2 — XML Extraction & Parsing (`parseXML.py`)

1. Reads the filtered PMCID list from Phase 1.
2. Checks the SQLite database for already-processed articles to avoid duplicates.
3. Fetches full-text XML from the Europe PMC REST API (or from local files), using 20 concurrent workers with exponential backoff retry logic (up to 5 retries).
4. Parses XML with `DynamicXmlParser`, extracting:
   - **Sections**: abstract, introduction, methods, results, discussion, conclusion
   - **Metadata**: title, authors, keywords, journal, publication date, DOI, PMCID, publisher ID, funding, categories, copyright
   - **Status**: API response codes, article type, per-field extraction success flags
5. Optionally saves raw XML files locally.
6. Reports extraction success statistics on completion.

### Phase 3 — Database Storage (`record_data_to_db.py`)

Data is stored in three SQLite tables, all linked by `pmcid`:

| Table | Contents |
|---|---|
| `sections` | Article body text by section (abstract, intro, methods, results, discussion, conclusion) |
| `article_metadata` | Title, authors, keywords, journal, publication date, DOI, funding, categories, copyright |
| `status` | API response codes, article type, extraction success/failure flags per field |

Features: dynamic schema evolution (columns added as needed), nested dict flattening, list-to-JSON serialization, and idempotent writes (`INSERT OR REPLACE`).

### Optional — XML Structure Exploration (`explore_xml_tags.py`)

Analyses downloaded XML files to catalogue tag hierarchies, attribute frequencies, and section naming conventions. Outputs CSV files under `data/exploration/` for statistical analysis.

## Configuration

All settings are in `config/config.yaml`. Key sections:

| Section | Key Settings |
|---|---|
| `api_europepmc_params` | API endpoint URLs (REST, OAI, Annotations, Archive FTP), local file paths, database location, `record_files` (save XML locally), `xml_origin` (`"api"` or `"files"`) |
| `search_params` | `query` (Europe PMC search query), `human_terms` (species filter list), `rerun_archive` (force re-download) |
| `db_params` | Table names for `status`, `sections`, `article_metadata`, `inference` |
| `data_loading` | `source` (`"test_set"` or `"database"`), `article_type_filter` (e.g. `"research-article"`) |
| `extraction_results` | Output format (`"sqlite"`, `"json"`, `"both"`), output directory and filename |

The default query targets eLife open-access articles with full text:
```
eLIfe AND (HAS_FT:Y AND OPEN_ACCESS:Y)
```

## Usage

```bash
# 1. Edit config/config.yaml to match your needs

# 2. Download PMCID archive and filter for human articles
python -m pmcid_dl.dl_pmcids

# 3. Fetch XML, parse articles, and store in SQLite
python -m pmcid_dl.parseXML

# 4. (Optional) Explore XML tag structure
python -m pmcid_dl.explore_xml_tags
```

## Dependencies

- `requests`
- `lxml`
- `pyyaml`
- `tqdm`
- Python standard library: `sqlite3`, `concurrent.futures`, `urllib3`, `re`, `json`, `datetime`, `gzip`, `csv`

## Key Design Details

- **Section mapping**: `relevant_tags.py` defines 7 standardized section categories (INTRO, METHODS, SUBJECTS, RESULTS, DISCUSSION, CONCLUSION, ACK_FUND) with extensive pattern matching (15–60+ naming variants each) to handle diverse article formatting conventions.
- **Idempotent pipeline**: Re-running any phase skips already-processed articles.
- **Resilient fetching**: Exponential backoff with up to 5 retries handles transient network and SSL errors.

## License

Apache 2.0 — see [LICENSE](LICENSE).
