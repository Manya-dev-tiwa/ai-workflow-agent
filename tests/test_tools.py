"""
tests/test_tools.py
─────────────────────────────────────────────────────────────────────────────
Unit tests for the non-LLM reusable tools.

Tests cover:
  • file_data_loader
  • tabular_validator_cleaner (invalid vendor rows)
  • data_calculator_aggregator (low stock, 10% price diff, failure aggregation)
  • entity_lookup_tool (order found/not found)
  • text_similarity_matcher (duplicate products)
  • report_formatter
─────────────────────────────────────────────────────────────────────────────
"""

import os
from pathlib import Path
import pytest

# Ensure we can import from src
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.config import MOCK_DATA_DIR, SAMPLES_DIR
from src.tools.registry import call_tool, get_all_schemas

# ── file_data_loader ──────────────────────────────────────────────────────────

def test_file_data_loader_csv():
    # Test loading a CSV
    file_path = str(MOCK_DATA_DIR / "inventory.csv")
    result = call_tool("file_data_loader", file_path=file_path)
    
    assert result["ok"] is True
    data = result["data"]
    assert isinstance(data, list)
    assert len(data) > 0
    assert "SKU" in data[0]

def test_file_data_loader_json():
    # Test loading a JSON
    file_path = str(SAMPLES_DIR / "campaign_brief_input.json")
    result = call_tool("file_data_loader", file_path=file_path)
    
    assert result["ok"] is True
    data = result["data"]
    assert isinstance(data, dict)
    assert "campaign_goal" in data

def test_file_data_loader_missing():
    # Test loading missing file
    result = call_tool("file_data_loader", file_path="missing.csv")
    assert result["ok"] is False
    assert "File not found" in result["error"]

# ── tabular_validator_cleaner ──────────────────────────────────────────────────

def test_tabular_validator_cleaner_vendor_rows():
    # Load the vendor upload sample
    file_path = str(SAMPLES_DIR / "vendor_upload.csv")
    loader_result = call_tool("file_data_loader", file_path=file_path)
    rows = loader_result["data"]
    
    # Validate
    result = call_tool(
        "tabular_validator_cleaner",
        rows=rows,
        required_columns=["SKU", "Product_Name", "Price"],
        required_fields=["SKU", "Product_Name", "Price"]
    )
    
    assert result["ok"] is True
    data = result["data"]
    
    # Check invalid rows (some have empty SKU, Product_Name, or Price)
    invalid = data["invalid_rows"]
    valid = data["valid_rows"]
    assert data["invalid_count"] > 0
    assert "validation_errors" in invalid[0]

# ── data_calculator_aggregator ─────────────────────────────────────────────────

def test_calculator_below_threshold_stock():
    file_path = str(MOCK_DATA_DIR / "inventory.csv")
    rows = call_tool("file_data_loader", file_path=file_path)["data"]
    
    result = call_tool(
        "data_calculator_aggregator",
        rows=rows,
        operation="below_threshold",
        column_a="Current_Stock",
        threshold=10,
        id_column="SKU"
    )
    
    assert result["ok"] is True
    flagged = result["data"]["flagged_rows"]
    # Check that flagged rows actually have Current_Stock < 10
    for row in flagged:
        assert float(row["Current_Stock"]) < 10

def test_calculator_compare_columns_price():
    # We need to join products and vendor prices or use a dataset with two prices.
    # Let's mock a simple dataset for this test.
    rows = [
        {"SKU": "1", "Internal_Price": "100", "Vendor_Price": "105"},
        {"SKU": "2", "Internal_Price": "100", "Vendor_Price": "120"}, # 20% diff
        {"SKU": "3", "Internal_Price": "100", "Vendor_Price": "95"}
    ]
    
    result = call_tool(
        "data_calculator_aggregator",
        rows=rows,
        operation="compare_columns",
        column_a="Internal_Price",
        column_b="Vendor_Price",
        threshold=10, # 10% diff
        id_column="SKU"
    )
    
    assert result["ok"] is True
    flagged = result["data"]["flagged_rows"]
    assert len(flagged) == 1
    assert flagged[0]["SKU"] == "2"

def test_calculator_aggregate_failure_rate():
    file_path = str(MOCK_DATA_DIR / "execution_logs.csv")
    rows = call_tool("file_data_loader", file_path=file_path)["data"]
    
    # We can aggregate duration seconds by workflow id
    result = call_tool(
        "data_calculator_aggregator",
        rows=rows,
        operation="aggregate",
        group_by_column="Workflow_ID",
        value_column="Duration_Seconds"
    )
    
    assert result["ok"] is True
    groups = result["data"]["groups"]
    assert "WF001" in groups
    assert groups["WF001"]["count"] > 0
    assert "average" in groups["WF001"]

# ── entity_lookup_tool ─────────────────────────────────────────────────────────

def test_entity_lookup_tool_found():
    file_path = str(MOCK_DATA_DIR / "orders.csv")
    rows = call_tool("file_data_loader", file_path=file_path)["data"]
    
    result = call_tool(
        "entity_lookup_tool",
        rows=rows,
        lookup_column="Order_ID",
        lookup_value="ORD-1001"
    )
    
    assert result["ok"] is True
    assert result["data"]["found"] is True
    assert result["data"]["match_count"] == 1
    assert result["data"]["matches"][0]["Order_ID"] == "ORD-1001"

def test_entity_lookup_tool_not_found():
    file_path = str(MOCK_DATA_DIR / "orders.csv")
    rows = call_tool("file_data_loader", file_path=file_path)["data"]
    
    result = call_tool(
        "entity_lookup_tool",
        rows=rows,
        lookup_column="Order_ID",
        lookup_value="ORD-9999"
    )
    
    assert result["ok"] is True
    assert result["data"]["found"] is False
    assert result["data"]["match_count"] == 0

# ── text_similarity_matcher ────────────────────────────────────────────────────

def test_text_similarity_matcher_duplicates():
    file_path = str(MOCK_DATA_DIR / "catalog.csv")
    rows = call_tool("file_data_loader", file_path=file_path)["data"]
    
    result = call_tool(
        "text_similarity_matcher",
        rows=rows,
        text_column="Product_Name",
        confidence_threshold=80,
        id_column="SKU"
    )
    
    assert result["ok"] is True
    groups = result["data"]["groups"]
    # There should be duplicate groups found in the mock catalog
    assert len(groups) > 0
    assert groups[0]["confidence"] >= 80

# ── report_formatter ───────────────────────────────────────────────────────────

def test_report_formatter():
    rows = [
        {"SKU": "1", "Name": "Product A"},
        {"SKU": "2", "Name": "Product B"}
    ]
    
    result = call_tool(
        "report_formatter",
        data=rows,
        title="Test Report",
        format="markdown"
    )
    
    assert result["ok"] is True
    report = result["data"]["report"]
    assert "Test Report" in report
    assert "| SKU | Name |" in report
    assert "| 1 | Product A |" in report

def test_list_data_files():
    result = call_tool("list_data_files")
    assert result["ok"] is True
    assert isinstance(result["data"], list)
    assert len(result["data"]) > 0
    file_map = {item["file_path"]: item["columns"] for item in result["data"]}
    assert "data/mock_data/employees.csv" in file_map
    assert "data/mock_data/execution_logs.csv" in file_map
    assert "Employee_ID" in file_map["data/mock_data/employees.csv"]
    assert "Run_ID" in file_map["data/mock_data/execution_logs.csv"]


def test_registry_schemas():
    schemas = get_all_schemas()
    assert len(schemas) == 7
    names = [s["name"] for s in schemas]
    assert "file_data_loader" in names
    assert "tabular_validator_cleaner" in names
    assert "data_calculator_aggregator" in names
    assert "entity_lookup_tool" in names
    assert "text_similarity_matcher" in names
    assert "report_formatter" in names
    assert "list_data_files" in names
