# AI Workflow Agent

A reusable, data-driven AI Agent system that dynamically loads business workflow definitions from Excel (`data/workflows.xlsx`), routes natural language requests to the correct workflow, executes step-by-step tool operations using an LLM reasoning engine, and produces clean Markdown reports.

---

## 🌟 Key Features

* **Excel as Single Source of Truth**: All 10 business workflows (triggers, steps, decision logic, tools, inputs, expected outputs) are loaded dynamically from `data/workflows.xlsx`. No workflow logic is hard-coded.
* **7 Generic Atomic Tools**: Modular, caller-driven tools for data loading (`file_data_loader`), tabular validation/cleaning (`tabular_validator_cleaner`), numeric calculations (`data_calculator_aggregator`), entity lookup (`entity_lookup_tool`), text similarity (`text_similarity_matcher`), data file discovery (`list_data_files`), and report formatting (`report_formatter`).
* **LLM Router & Reasoning Engine**:
  * **Router**: Classifies intent and extracts typed parameters using a dynamically constructed catalog prompt.
  * **Engine**: Step-by-step tool-selection loop that executes tools deterministically and handles errors, retries, and step caps.
* **Zero Hard-Coded Conditionals**: Neither the Router nor the Engine contains `if workflow_id == "WF00X"` checks.
* **Extensible Architecture**: Adding an 11th workflow requires only adding a row to `data/workflows.xlsx` (and optional input files).
* **Dual Interfaces**: Full-featured CLI and interactive Streamlit web dashboard.

---

## 📁 Repository Structure

```
AI-WORKFLOW-AGENT/
├── data/
│   ├── workflows.xlsx              # Master Excel catalog (Workflows & Test_Questions)
│   ├── mock_data/                  # Persistent mock datasets (inventory, orders, catalog, etc.)
│   └── samples/                    # Sample input files for test requests
├── src/
│   ├── agent/
│   │   ├── registry.py             # Excel parser and registry index
│   │   ├── router.py               # LLM intent matching & parameter extraction
│   │   └── engine.py               # Step-by-step LLM tool execution engine
│   ├── tools/
│   │   ├── data_calculator_aggregator.py # Numeric calculations and aggregations
│   │   ├── entity_lookup_tool.py         # Search datasets for records by ID/attribute
│   │   ├── file_data_loader.py           # Load CSV, XLSX, JSON files
│   │   ├── list_data_files.py            # List available data files and column schemas
│   │   ├── registry.py                   # Tool registry and schema loader
│   │   ├── report_formatter.py           # Markdown table and summary reporting
│   │   ├── tabular_validator_cleaner.py  # Header normalization and row validation
│   │   └── text_similarity_matcher.py    # Fuzzy similarity and deduplication
│   ├── llm/
│   │   └── client.py               # Unified LLM provider client (OpenAI & Gemini)
│   ├── config.py                   # Central settings, environment loading, guardrails
│   ├── app.py                      # Streamlit Web UI dashboard
│   └── main.py                     # CLI entry point
├── tests/
│   ├── test_engine.py              # Engine unit tests with offline mock LLM
│   ├── test_router.py              # Router unit tests
│   ├── test_tools.py               # Tool unit tests
│   └── test_workflows.py           # End-to-end workflow validation tests
├── scripts/
│   ├── verify_registry.py          # Registry verification script
│   └── run_all_workflows.py        # End-to-end test runner for all 10 workflows
├── PLAN.md                         # Detailed design and architectural plan
├── SPEC.md                         # Original technical assignment specification
├── pytest.ini                      # Pytest configuration (pythonpath = .)
├── requirements.txt                # Python dependencies
├── .env.example                    # Environment variable template
└── README.md                       # Project documentation
```

---

## 🚀 Setup & Installation

### 1. Prerequisites
* Python 3.10+ installed
* An OpenAI API key (`OPENAI_API_KEY`) or Google Gemini API key (`GEMINI_API_KEY`)

### 2. Virtual Environment Setup
```bash
# Clone or navigate to project directory
cd AI-WORKFLOW-AGENT

# Create and activate virtual environment
python -m venv .venv

# On Windows:
.venv\Scripts\activate

# On Linux/macOS:
source .venv/bin/activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Configure Environment Variables
Copy `.env.example` to `.env` and fill in your API key:
```env
# ── LLM Provider Selection ("openai" or "gemini") ──────────────────────────────
LLM_PROVIDER=gemini

# ── OpenAI API settings ────────────────────────────────────────────────────────
# Obtain from: https://platform.openai.com/api-keys
OPENAI_API_KEY=sk-...your-openai-key-here...
OPENAI_MODEL=gpt-4o-mini

# ── Gemini API settings ────────────────────────────────────────────────────────
# Obtain from: https://aistudio.google.com/app/apikey
# Uses the NEW google-genai SDK (not google-generativeai).
GEMINI_API_KEY=...your-gemini-key-here...
GEMINI_MODEL=gemini-2.0-flash

# ── LLM Timeout ────────────────────────────────────────────────────────────────
# How many seconds to wait per LLM request before giving up. Default = 60.
# Raise this (e.g., to 120) on slow networks or with large prompts.
LLM_TIMEOUT_SECONDS=60
```

---

## 📂 How Input Files Are Resolved

Input files are resolved in the following priority order:
1. **Explicit `--file` Argument**: Highest priority override supplied directly by the caller (e.g. `--file data/samples/vendor_upload.csv`).
2. **Hint-Based Fallback**: When no `--file` is passed, query hints (e.g. *"this product"*, *"this vendor spreadsheet"*, *"these keywords"*, or *"this campaign brief"*) are matched against the workflow's `Inputs` definition and pre-mapped sample files in `data/samples/`.
3. **User Clarification (`ASK_USER`)**: If no input file is attached or resolved and required business inputs remain missing, the engine stops and prompts the user (`ASK_USER`) naming the missing fields.

---

## 💻 Usage Guide

### Running via CLI (`main.py`)
Run any natural language request directly from the command line:

```bash
# Order Lookup (WF005)
python -m src.main "Where is order ORD-1001?"

# Restock Check (WF001)
python -m src.main "Which products need restocking?"

# Custom file input override
python -m src.main "Process this vendor spreadsheet" --file data/samples/vendor_upload.csv
```

### Running the Web UI (`app.py`)
Launch the Streamlit interactive dashboard:
```bash
streamlit run src/app.py
```
Open [http://localhost:8501](http://localhost:8501) in your browser. The UI features:
* **Panel A**: Selected workflow details, trigger, extracted parameters, and router rationale.
* **Panel B**: Interactive execution trace table showing step sequence, tools invoked, status, and output.
* **Panel C**: Rendered final output.
* **Quick Selector**: Pre-loaded test request dropdown for all 10 workflows.

---

## 🧪 Testing & Verification

### Run Automated Unit Tests
Run plain `pytest` directly:
```bash
pytest
```
*Executes 40 tests across tools, router, engine, and workflow registry.*

### Verify Excel Registry Loading
```bash
python scripts/verify_registry.py
```

### Execute All 10 Workflows End-to-End
```bash
python scripts/run_all_workflows.py
```
*Runs all 10 test requests sequentially and saves individual Markdown execution reports into `examples/outputs/`.*

> **Note**: On the free Google Gemini API tier (15 requests/minute limit), running `run_all_workflows.py` can take several minutes due to rate-limit throttling and exponential backoff retries.

---

## 📊 Summary of Implemented Workflows

| ID | Workflow Name | Trigger / Query | Key Tools Used |
|---|---|---|---|
| **WF001** | Inventory Restock Check | *"Which products need restocking?"* | `file_data_loader`, `data_calculator_aggregator`, `report_formatter` |
| **WF002** | Product Price Validation | *"Find products where vendor price differs by more than 10%."* | `file_data_loader`, `data_calculator_aggregator`, `report_formatter` |
| **WF003** | Vendor File Processing | *"Process this vendor spreadsheet and show invalid rows."* | `file_data_loader`, `tabular_validator_cleaner`, `report_formatter` |
| **WF004** | Product Description Generator | *"Generate SEO content for this product."* | `file_data_loader`, `report_formatter` |
| **WF005** | Customer Order Status | *"Where is order ORD-1001?"* | `file_data_loader`, `entity_lookup_tool`, `report_formatter` |
| **WF006** | Duplicate Product Detection | *"Find likely duplicate products in the catalog."* | `file_data_loader`, `text_similarity_matcher`, `report_formatter` |
| **WF007** | Marketing Campaign Brief | *"Create a campaign brief for the new collection."* | `file_data_loader`, `report_formatter` |
| **WF008** | SEO Keyword Classification | *"Classify these keywords and map them to pages."* | `file_data_loader`, `report_formatter` |
| **WF009** | Employee Task Assignment | *"Assign this urgent task to the best available developer."* | `file_data_loader`, `entity_lookup_tool`, `report_formatter` |
| **WF010** | Workflow Performance Report | *"Which workflows are failing most often?"* | `file_data_loader`, `data_calculator_aggregator`, `report_formatter` |

---

## ➕ Extensibility Model: Adding an 11th Workflow

To add a new workflow (e.g., `WF011` - Customer Churn Risk Analysis):
1. **Add a Row in `data/workflows.xlsx`**: Add `WF011`, its name, trigger, inputs, steps, decision logic, tools, and expected output.
2. **Add Mock Data (if needed)**: Place any required dataset in `data/mock_data/` or `data/samples/`.
3. **No Code Changes Required**: The Router automatically includes `WF011` in its dynamic catalog prompt, and the Engine executes it using the existing atomic tools.
