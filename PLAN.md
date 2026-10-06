# AI Workflow Agent - Project Implementation Plan

> **Revision notes (applied from user review):** Engine design updated to LLM-driven tool-selection per step (Section 4). Threshold sourcing rule added (Section 4 + config notes). `data/samples/` folder added (Section 4). Error-handling spec added (Section 4). Streamlit UI (`src/app.py`) added (Section 4).

---

## 1. Summary of All 10 Business Workflows

| ID | Workflow Name | Trigger | Inputs | Steps | Decision Logic | Tools Required | Expected Output |
|---|---|---|---|---|---|---|---|
| **WF001** | Inventory Restock Check | User asks which products need restocking | Product inventory CSV; minimum stock threshold | Load inventory → compare current stock with minimum threshold → identify low-stock products → calculate reorder quantity → generate restock list | If `current_stock < minimum_stock`, mark product for restock | CSV reader; calculator | List of products requiring restock with current stock, threshold, and suggested reorder quantity |
| **WF002** | Product Price Validation | User asks to validate product prices | Product CSV; vendor price list | Load product prices → match products by SKU → compare internal and vendor prices → calculate percentage difference → flag exceptions | Flag when price difference exceeds `10%` (from Decision_Logic; never hard-coded in tool) | CSV reader; calculator | Validation report showing matched products, price differences, and exceptions |
| **WF003** | Vendor File Processing | User provides a vendor file for processing | CSV/XLSX file containing vendor product data | Read file → detect columns → normalize column names → validate required fields → identify invalid rows → produce cleaned dataset | Rows missing `SKU` or `product name` are invalid | Excel/CSV parser; data validation | Cleaned file plus validation summary and invalid-row report |
| **WF004** | Product Description Generator | User asks to generate product content | Product name; category; attributes; material; color; target audience | Validate required attributes → create product description → generate short description → generate SEO title → generate meta description | Do not invent missing product attributes; explicitly mark missing information | LLM; text validation | Product description, short description, SEO title, and meta description |
| **WF005** | Customer Order Status | User asks for an order status | Order ID or customer email | Validate identifier → search order data → retrieve order status → retrieve shipment information → summarize current status | If no order is found, ask for another identifier | Order database/API; shipment lookup | Order status, items, shipment status, and tracking information when available |
| **WF006** | Duplicate Product Detection | User asks to find duplicate products | Product catalog | Load products → normalize names/SKUs → compare identifiers → compare product attributes → group likely duplicates → assign confidence | Exact SKU match is a definite duplicate; high attribute similarity is a possible duplicate | CSV/database reader; text similarity | Duplicate groups with matching fields and confidence level |
| **WF007** | Marketing Campaign Brief | User asks to create a campaign brief | Campaign goal; product list; target audience; promotion; dates | Validate inputs → identify campaign objective → summarize products → create messaging → create channel recommendations → create campaign checklist | If campaign goal or dates are missing, request them before generating the brief | LLM; product data reader | Structured campaign brief with objective, audience, messaging, channels, timeline, and checklist |
| **WF008** | SEO Keyword Classification | User uploads or provides a keyword list | Keyword CSV; product/category information | Read keywords → remove duplicates → classify search intent → map keywords to categories → identify high-priority keywords → export results | Classify each keyword as *informational*, *commercial*, *transactional*, or *navigational* | CSV reader; LLM/classifier | Keyword report with intent, category, priority, and recommended target page |
| **WF009** | Employee Task Assignment | Manager asks the agent to assign a task | Task description; employee list; skills; workload; priority; deadline | Understand task requirements → compare employee skills → check current workload → rank candidates → select employee → generate assignment summary | Prefer employees with required skills and available capacity; escalate if no suitable employee exists | Employee/task database; ranking logic | Recommended employee, reasoning, priority, deadline, and task summary |
| **WF010** | Workflow Performance Report | User asks for a performance report | Workflow execution logs | Load execution logs → calculate success/failure rate → calculate average execution time → identify frequent errors → identify slow steps → generate recommendations | Flag workflows with failure rate above `10%` or average execution time above defined threshold (default threshold in `config.py`; **ASSUMPTION**: default = 30 seconds) | CSV/database reader; calculator; reporting | Performance summary with metrics, problem areas, and improvement recommendations |

---

## 2. Test Questions Mapping (`Test_Questions` Sheet)

| Workflow ID | Test Request | What To Check | Sample Input File |
|---|---|---|---|
| **WF001** | *"Which products need restocking?"* | Tests workflow selection and threshold logic | `data/mock_data/inventory.csv` |
| **WF002** | *"Find products where vendor price differs by more than 10%."* | Tests comparison and decision logic | `data/mock_data/products.csv` + `data/mock_data/vendor_prices.csv` |
| **WF003** | *"Process this vendor spreadsheet and show invalid rows."* | Tests file ingestion and validation | `data/samples/vendor_upload.csv` |
| **WF004** | *"Generate SEO content for this product."* | Tests LLM workflow and missing-data handling | `data/samples/product_input.json` |
| **WF005** | *"Where is order ORD-1001?"* | Tests lookup and missing-order handling | `data/mock_data/orders.csv` |
| **WF006** | *"Find likely duplicate products in the catalog."* | Tests similarity and confidence | `data/mock_data/catalog.csv` |
| **WF007** | *"Create a campaign brief for the new collection."* | Tests structured content generation | `data/samples/campaign_brief_input.json` |
| **WF008** | *"Classify these keywords and map them to pages."* | Tests classification and mapping | `data/samples/keywords.csv` |
| **WF009** | *"Assign this urgent task to the best available developer."* | Tests ranking and decision logic | `data/mock_data/employees.csv` |
| **WF010** | *"Which workflows are failing most often?"* | Tests aggregation and reporting | `data/mock_data/execution_logs.csv` |

---

## 3. Small Reusable Tools (Generic Across All Workflows)

Rather than building per-workflow tools, the system uses **8 atomic, generic tools**. No tool contains `if workflow_id == "WF00X"` logic; all parameters (thresholds, required fields, etc.) are passed at call time by the engine.

1. **`file_data_loader`**: Loads CSV / XLSX / JSON files into standard pandas DataFrames or Python dicts.
2. **`tabular_validator_cleaner`**: Standardizes column headers, validates mandatory fields (passed as parameter), flags invalid/missing rows, and filters datasets.
3. **`data_calculator_aggregator`**: Executes numeric calculations (price diff %, threshold checks, aggregations). Threshold values always supplied as input parameters—never hard-coded inside the tool.
4. **`entity_lookup_tool`**: Searches structured datasets for matching records by ID or attribute (e.g., Order lookup, Employee skills lookup).
5. **`text_similarity_matcher`**: Computes fuzzy similarity scores (RapidFuzz / Levenshtein) and returns confidence levels.
6. **`llm_content_generator`**: Prompts the LLM for structured text generation (product descriptions, campaign briefs). Never invents missing data.
7. **`llm_classifier`**: Classifies text items into a caller-specified taxonomy (e.g., intent buckets).
8. **`report_formatter`**: Standardizes tool outputs into clean Markdown tables and summary JSON for Streamlit and CLI.

---

## 4. Proposed Architecture & Folder Structure

### Engine Design (Updated)

The execution engine receives the workflow's **Steps**, **Decision_Logic**, and **Expected_Output** fields (loaded from Excel) together with the **typed tool schemas** (all 8 tools above). It sends these to the LLM in a single system prompt. The LLM then selects tool calls **one at a time**, returning a structured JSON call for each step. The engine:

- Enforces a **configurable `MAX_STEPS` limit** (prevents infinite loops).
- Validates every LLM response as JSON; if parsing fails, raises a clear `InvalidLLMResponseError`.
- Wraps every tool call in a try/except; on failure emits a `ToolExecutionError` with the tool name, inputs, and error message.
- Retries transient LLM failures up to `MAX_RETRIES` times (from `config.py`).
- Appends each step (tool name, inputs, output, status) to an **execution trace** returned to the user.
- Contains **zero `if workflow_id == "WF00X"` conditionals**—the workflow definition drives all behaviour.

### Error Handling Spec

| Error Condition | Behaviour |
|---|---|
| Tool execution failure | Emit `ToolExecutionError`: show tool name, inputs, error message. Never continue with invented data. |
| Invalid / unparseable LLM JSON | Emit `InvalidLLMResponseError` with raw text for debugging. Retry up to `MAX_RETRIES`. |
| No workflow matched | Return clear `"No matching workflow found for your request."` message; suggest rephrasing. |
| Missing API key | Detect at startup in `config.py`; raise `MissingAPIKeyError` with name of missing variable. |
| Missing required data field | Tool raises `MissingDataError` with field name; engine surfaces message to user. |

### Threshold Sourcing Rule

- Thresholds (e.g., `10%` for WF002, `minimum_stock` for WF001) are parsed at runtime from the workflow's **`Decision_Logic`** column in Excel.
- For WF010: the average-execution-time threshold has no numeric value in Excel, so a `DEFAULT_SLOW_STEP_THRESHOLD_SECONDS = 30` constant is defined in `config.py` with a comment marking it as an **ASSUMPTION**.
- Tools **never** hard-code any threshold; they always receive it as a typed parameter.

### Execution Pipeline

```
User Query (CLI via main.py  OR  Web UI via src/app.py)
   │
   ▼
[ 1. LLM Router ] ── Selects Workflow ID; extracts typed parameters from query
   │
   ▼
[ 2. Workflow Registry ] ── Loads Steps, Decision_Logic, Expected_Output from Excel
   │
   ▼
[ 3. Generic Execution Engine ]
   │   Sends {Steps, Decision_Logic, Expected_Output, tool_schemas} → LLM
   │   LLM returns one tool call at a time
   ├── Validate JSON response
   ├── Execute tool (with error handling & retry)
   ├── Append step to execution trace
   └── Repeat until DONE signal or MAX_STEPS reached
   │
   ▼
[ 4. Execution Trace + Final Result ]
   │
   ├── CLI: printed to stdout (main.py)
   └── Web: displayed in Streamlit panels (src/app.py)
          ├── Panel A: Selected Workflow (ID, name, trigger)
          ├── Panel B: Steps Executed (trace table)
          └── Panel C: Final Output
```

### Folder Structure
```
AI-WORKFLOW-AGENT/
├── data/
│   ├── workflows.xlsx              # Master Excel — single source of truth
│   ├── mock_data/                  # Persistent mock datasets for all 10 workflows
│   │   ├── inventory.csv           # WF001 — low-stock and well-stocked items
│   │   ├── products.csv            # WF002 — prices above and below 10% diff
│   │   ├── vendor_prices.csv       # WF002 — vendor price list
│   │   ├── catalog.csv             # WF006 — exact + near-duplicate products
│   │   ├── orders.csv              # WF005 — includes missing order edge case
│   │   ├── employees.csv           # WF009 — varied skills and workloads
│   │   └── execution_logs.csv      # WF010 — failing and slow workflow logs
│   └── samples/                    # One-shot sample inputs for Test_Requests
│       ├── vendor_upload.csv       # WF003 — rows missing SKU / product name
│       ├── product_input.json      # WF004 — some attributes present, some missing
│       ├── campaign_brief_input.json # WF007 — goal, products, audience, dates
│       └── keywords.csv            # WF008 — mixed intent keywords
├── src/
│   ├── agent/
│   │   ├── __init__.py
│   │   ├── registry.py             # Loads workflows & test questions from Excel
│   │   ├── router.py               # LLM-based intent matching & param extraction
│   │   └── engine.py               # LLM-driven step execution engine
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── data_tools.py           # file_data_loader, tabular_validator_cleaner,
│   │   │                           #   data_calculator_aggregator, entity_lookup_tool
│   │   ├── similarity_tools.py     # text_similarity_matcher
│   │   ├── llm_tools.py            # llm_content_generator, llm_classifier
│   │   └── report_tools.py         # report_formatter
│   ├── config.py                   # Env vars, MAX_STEPS, MAX_RETRIES, thresholds
│   ├── app.py                      # Streamlit web UI
│   └── main.py                     # CLI entry point
├── tests/
│   └── test_workflows.py           # Verifies all 10 Test_Questions requests
├── scripts/
│   └── verify_registry.py          # Prints all loaded workflows (Phase 1 check)
├── PLAN.md
├── SPEC.md
├── .env.example
├── requirements.txt
├── .gitignore
└── README.md
```

---

## 5. Extensibility Model: Adding an 11th Workflow

To add **WF011** (e.g., "Customer Churn Risk Analysis"):
1. **Add 1 row in `data/workflows.xlsx`** — fill in all 8 columns.
2. **Zero changes to router or engine** — both are fully data-driven; WF011 is auto-registered at startup.
3. **Add mock data** in `data/mock_data/` if the workflow needs new input files.
4. **Optional**: add a new tool in `src/tools/` only if WF011 needs a capability not covered by the 8 existing tools.

---

## 6. Code vs. LLM Responsibilities Breakdown

| Component / Task | Implementation Method | Rationale & Rules |
|---|---|---|
| **Workflow Selection & Routing** | **LLM** | Semantic matching of user query to workflow trigger descriptions |
| **Parameter Extraction** | **LLM** | Parses entities (e.g., `ORD-1001`, `10%`) from free-form user text into typed JSON |
| **Engine Step Scheduling** | **LLM** | LLM reads Steps + Decision_Logic + tool schemas and issues one tool call at a time |
| **CSV/Excel File Loading** | **Real Code (Pandas / OpenPyXL)** | Deterministic, fast; no token-limit risk |
| **Data Validation & Cleaning** | **Real Code (Pandas)** | Header normalization, required-field checking, row flagging |
| **Calculations & Threshold Checking** | **Real Code (Pandas / Python)** | Threshold values passed as parameters; math is always exact |
| **Duplicate / Similarity Search** | **Real Code (RapidFuzz)** | Deterministic confidence scores; not subject to LLM hallucination |
| **Structured Content Generation** | **LLM** | Product descriptions, campaign briefs — bounded strictly by provided inputs |
| **SEO Keyword Intent Classification** | **LLM** | Nuanced language classification into intent buckets |
| **Employee Task Matching** | **Real Code + LLM** | Code ranks by skills + workload; LLM writes human-readable assignment rationale |
| **Execution Logging & Output Formatting** | **Real Code (Python)** | Deterministic step trace and Markdown table generation |
| **Error & Retry Handling** | **Real Code (Python)** | Engine enforces MAX_RETRIES, MAX_STEPS; raises typed errors with clear messages |

---

## 7. Build Phases

### Phase 1 — Foundation & Data (build first, then stop)
- `requirements.txt`, `.gitignore`, `.env.example`
- `src/config.py`
- `src/agent/registry.py`
- All mock data (`data/mock_data/`) and sample inputs (`data/samples/`)
- `scripts/verify_registry.py` — prints loaded workflows for visual verification

### Phase 2 — Tools
- `src/tools/data_tools.py`
- `src/tools/similarity_tools.py`
- `src/tools/llm_tools.py`
- `src/tools/report_tools.py`

### Phase 3 — Agent (Router + Engine)
- `src/agent/router.py`
- `src/agent/engine.py`

### Phase 4 — UI & Tests
- `src/main.py` (CLI)
- `src/app.py` (Streamlit)
- `tests/test_workflows.py`
- `README.md`
