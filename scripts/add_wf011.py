import openpyxl
from copy import copy

path = "data/workflows.xlsx"
wb = openpyxl.load_workbook(path)
ws = wb["Workflows"]

row = [
    "WF011",
    "Overdue Orders Report",
    "User asks which orders are overdue, late, delayed, or past their estimated delivery date",
    "Orders dataset (Order_ID, Status, Shipment_Status, Estimated_Delivery)",
    "Load orders data → Compare Estimated_Delivery with today's date → Keep orders where Estimated_Delivery is before today and Status is not Delivered or Cancelled → Calculate days overdue → Format report",
    "Flag an order as overdue only if Estimated_Delivery is before today and Status is not Delivered or Cancelled. Orders with no Estimated_Delivery are not flagged. If none are overdue, say so clearly. Do not invent orders.",
    "CSV reader; calculator/aggregator; report formatter",
    "List of overdue orders with Order_ID, Customer_Name, Status, Estimated_Delivery, and days overdue, plus a total count",
]

for col, value in enumerate(row, start=1):
    cell = ws.cell(row=12, column=col, value=value)
    src = ws.cell(row=11, column=col)
    cell.font = copy(src.font)
    cell.alignment = copy(src.alignment)
    cell.border = copy(src.border)

wb.save(path)
print("Row 12 written")