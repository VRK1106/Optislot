"""
FastAPI Dynamic Registry Server for Smart Parking System

This server acts as a URL shortener that auto-updates itself.
QR codes point to this server, which redirects to the current live session.
Each parking unit is identified by a unique metadata ID.
"""

from fastapi import FastAPI, HTTPException, Depends, Query
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from typing import Optional
from contextlib import asynccontextmanager
import sqlite3
import os
import secrets
from datetime import datetime

# Database setup
DB_PATH = os.getenv("DATABASE_PATH", "registry.db")
API_KEY = os.getenv("REGISTRY_API_KEY", "dev-key-change-in-production")


def get_db_connection():
    """Get database connection."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Initialize the database tables."""
    conn = get_db_connection()
    try:
        c = conn.cursor()
        c.execute('''
            CREATE TABLE IF NOT EXISTS units (
                unit_id TEXT PRIMARY KEY,
                current_url TEXT NOT NULL,
                unit_name TEXT,
                last_updated TEXT,
                created_at TEXT
            )
        ''')
        conn.commit()
    finally:
        conn.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup/shutdown."""
    init_db()
    yield


app = FastAPI(
    title="Smart Parking Registry",
    description="Dynamic URL Registry for Permanent QR Codes",
    version="1.0.0",
    lifespan=lifespan
)


# --- Models ---
class RegisterRequest(BaseModel):
    unit_id: str
    current_url: str
    unit_name: Optional[str] = None


class RegisterResponse(BaseModel):
    success: bool
    unit_id: str
    message: str
    qr_base_url: str


class UnitInfo(BaseModel):
    unit_id: str
    current_url: str
    unit_name: Optional[str]
    last_updated: str


# --- API Key Verification ---
def verify_api_key(api_key: str = Query(..., alias="api_key")):
    """Verify the API key for protected endpoints."""
    if api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return api_key


# --- Endpoints ---

@app.get("/")
async def root():
    """Health check and info endpoint."""
    return {
        "service": "Smart Parking Registry",
        "status": "running",
        "version": "1.0.0"
    }


@app.post("/register", response_model=RegisterResponse)
async def register_unit(request: RegisterRequest, api_key: str = Depends(verify_api_key)):
    """Register or update a parking unit's current URL."""
    conn = get_db_connection()
    try:
        c = conn.cursor()
        now = datetime.utcnow().isoformat()
        
        c.execute("SELECT unit_id FROM units WHERE unit_id = ?", (request.unit_id,))
        exists = c.fetchone()
        
        if exists:
            c.execute("""
                UPDATE units 
                SET current_url = ?, unit_name = ?, last_updated = ?
                WHERE unit_id = ?
            """, (request.current_url, request.unit_name, now, request.unit_id))
            message = "Unit URL updated successfully"
        else:
            c.execute("""
                INSERT INTO units (unit_id, current_url, unit_name, last_updated, created_at)
                VALUES (?, ?, ?, ?, ?)
            """, (request.unit_id, request.current_url, request.unit_name, now, now))
            message = "Unit registered successfully"
        
        conn.commit()
    finally:
        conn.close()
    
    qr_base_url = os.getenv("REGISTRY_PUBLIC_URL", "http://localhost:8000")
    
    return RegisterResponse(
        success=True,
        unit_id=request.unit_id,
        message=message,
        qr_base_url=f"{qr_base_url}/r/{request.unit_id}"
    )


@app.get("/r/{unit_id}/{slot_id}")
async def redirect_to_slot(unit_id: str, slot_id: str):
    """Redirect to the unit's current URL with the slot ID."""
    conn = get_db_connection()
    try:
        c = conn.cursor()
        c.execute("SELECT current_url FROM units WHERE unit_id = ?", (unit_id,))
        row = c.fetchone()
        
        if not row:
            raise HTTPException(
                status_code=404, 
                detail=f"Unit '{unit_id}' not found. The parking system may be offline."
            )
        
        current_url = row["current_url"]
    finally:
        conn.close()
    
    redirect_url = f"{current_url}/verify_ui?slot_id={slot_id}"
    return RedirectResponse(url=redirect_url, status_code=302)


@app.get("/unit/{unit_id}", response_model=UnitInfo)
async def get_unit_info(unit_id: str):
    """Get information about a registered unit."""
    conn = get_db_connection()
    try:
        c = conn.cursor()
        c.execute("SELECT * FROM units WHERE unit_id = ?", (unit_id,))
        row = c.fetchone()
        
        if not row:
            raise HTTPException(status_code=404, detail="Unit not found")
        
        return UnitInfo(
            unit_id=row["unit_id"],
            current_url=row["current_url"],
            unit_name=row["unit_name"],
            last_updated=row["last_updated"]
        )
    finally:
        conn.close()


@app.get("/units")
async def list_units(api_key: str = Depends(verify_api_key)):
    """List all registered units (admin endpoint)."""
    conn = get_db_connection()
    try:
        c = conn.cursor()
        c.execute("SELECT unit_id, current_url, unit_name, last_updated FROM units")
        rows = c.fetchall()
        
        return {
            "count": len(rows),
            "units": [dict(row) for row in rows]
        }
    finally:
        conn.close()


@app.get("/generate-key")
async def generate_api_key():
    """Generate a secure API key (for initial setup)."""
    return {"api_key": secrets.token_urlsafe(32)}
