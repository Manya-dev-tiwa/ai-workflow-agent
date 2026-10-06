# AI Workflow Agent

A reusable, data-driven AI Agent system that dynamically loads business workflow definitions from Excel (`data/workflows.xlsx`), routes natural language requests to the correct workflow, executes step-by-step tool operations using an LLM reasoning engine, and produces clean Markdown reports.

---

## 🌟 Key Features

* **Excel as Single Source of Truth**: All 10 business workflows (triggers, steps, decision logic, tools, inputs, expected outputs) are loaded dynamically from `data/workflows.xlsx`. No workflow logic is hard-coded.
* **8 Generic Atomic Tools**: Tool functionality (data loading, tabular cleaning, calculations, entity lookup, text similarity, LLM generation, LLM classification, report formatting) is modular and caller-driven.
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
│   │   ├── data_tools.py           # file_data_loader, tabular_validator_cleaner,
│   │   │                           #   data_calculator_aggregator, entity_lookup_tool
│   │   ├── similarity_tools.py     # text_similarity_matcher
│   │   ├── llm_tools.py            # llm_content_generator, llm_classifier
│   │   └── report_tools.py         # report_formatter
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
LLM_PROVIDER=openai
OPENAI_API_KEY=your_openai_api_key_here
OPENAI_MODEL=gpt-4o-mini
```
*(Alternatively, set `LLM_PROVIDER=gemini` and configure `GEMINI_API_KEY`.)*

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
```bash
pytest
```
*Executes 34 tests across tools, router, engine, and workflow registry.*

### Verify Excel Registry Loading
```bash
python scripts/verify_registry.py
```

### Execute All 10 Workflows End-to-End
```bash
python scripts/run_all_workflows.py
```
*Runs all 10 test requests sequentially and saves individual Markdown execution reports into `examples/outputs/`.*

---

## 📊 Summary of Implemented Workflows

| ID | Workflow Name | Trigger / Query | Key Tools Used |
|---|---|---|---|
| **WF001** | Inventory Restock Check | *"Which products need restocking?"* | `file_data_loader`, `data_calculator_aggregator`, `report_formatter` |
| **WF002** | Product Price Validation | *"Find products where vendor price differs by more than 10%."* | `file_data_loader`, `data_calculator_aggregator`, `report_formatter` |
| **WF003** | Vendor File Processing | *"Process this vendor spreadsheet and show invalid rows."* | `file_data_loader`, `tabular_validator_cleaner`, `report_formatter` |
| **WF004** | Product Description Generator | *"Generate SEO content for this product."* | `file_data_loader`, `llm_content_generator`, `report_formatter` |
| **WF005** | Customer Order Status | *"Where is order ORD-1001?"* | `file_data_loader`, `entity_lookup_tool`, `report_formatter` |
| **WF006** | Duplicate Product Detection | *"Find likely duplicate products in the catalog."* | `file_data_loader`, `text_similarity_matcher`, `report_formatter` |
| **WF007** | Marketing Campaign Brief | *"Create a campaign brief for the new collection."* | `file_data_loader`, `llm_content_generator`, `report_formatter` |
| **WF008** | SEO Keyword Classification | *"Classify these keywords and map them to pages."* | `file_data_loader`, `llm_classifier`, `report_formatter` |
| **WF009** | Employee Task Assignment | *"Assign this urgent task to the best available developer."* | `file_data_loader`, `entity_lookup_tool`, `report_formatter` |
| **WF010** | Workflow Performance Report | *"Which workflows are failing most often?"* | `file_data_loader`, `data_calculator_aggregator`, `report_formatter` |

---

## ➕ Extensibility Model: Adding an 11th Workflow

To add a new workflow (e.g., `WF011` - Customer Churn Risk Analysis):
1. **Add a Row in `data/workflows.xlsx`**: Add `WF011`, its name, trigger, inputs, steps, decision logic, tools, and expected output.
2. **Add Mock Data (if needed)**: Place any required dataset in `data/mock_data/` or `data/samples/`.
3. **No Code Changes Required**: The Router automatically includes `WF011` in its dynamic catalog prompt, and the Engine executes it using the existing 8 atomic tools.
