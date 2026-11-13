# server.py
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import pandas as pd
import io

import ai_manager
import logic_manager
import validator
from DataManager import MongoDataManager

app = FastAPI(title="Shipment Risk Assessment API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

Mongo_DM = MongoDataManager()

# ----------------- Models -----------------
class ShipmentInput(BaseModel):
    origin_port: str
    destination_port: str
    departure_time: str
    arrival_time: str

class SearchFilter(BaseModel):
    shipment_id: Optional[str] = None
    route_id: Optional[str] = None
    origin: Optional[str] = None
    overall_risk: Optional[str] = None
    outcome: Optional[str] = None
    needs_human: Optional[bool] = None

def assign_ids(df: pd.DataFrame) -> pd.DataFrame:
    df = df.drop(columns="shipment_id", errors="ignore")
    df.insert(0, "shipment_id", [f"SHP-{i:03d}" for i in range(1, len(df) + 1)])
    return df

# ----------------- Endpoints -----------------

@app.get("/api/ports")
def get_ports():
    """Return choices for port autocomplete."""
    return {"ports": validator.PORT_CHOICES}

@app.post("/api/shipments/evaluate")
def evaluate_manual_shipments(shipments: List[ShipmentInput]):
    """Receives manual shipments, runs AI & Logic Manager, stores to Mongo."""
    if not shipments:
        raise HTTPException(status_code=400, detail="No shipments provided")
    
    df = pd.DataFrame([s.model_dump() for s in shipments])
    df = assign_ids(df)

    assessments = ai_manager.assess_shipments(df)
    results = logic_manager.evaluate_shipments(assessments, Mongo_DM)
    Mongo_DM.InsertRecord(results)

    return {
        "assessments": assessments.to_dict("records"),
        "results": [{"record": r, "decision": d} for r, d in results]
    }

@app.post("/api/shipments/upload-csv")
async def upload_csv_shipments(file: UploadFile = File(...)):
    """Parses CSV and returns normalized shipment rows to frontend."""
    contents = await file.read()
    try:
        df = pd.read_csv(io.BytesIO(contents), dtype=str, keep_default_na=False)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid CSV: {str(e)}")
    
    return {"shipments": df.to_dict("records")}

@app.post("/api/records/search")
def search_records(criteria: SearchFilter):
    """Executes Mongo_DM.FindRecord with non-empty filters."""
    filter_dict = {k: v for k, v in criteria.model_dump().items() if v is not None and v != ""}
    records = Mongo_DM.FindRecord(filter_dict)
    return {"records": records}