from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Text, DateTime, Date, Boolean, ForeignKey, JSON
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class Inspection(Base):
    __tablename__ = "inspections"

    id = Column(Integer, primary_key=True)
    fda_inspection_id = Column(String(64), unique=True, nullable=False)
    firm_name = Column(String(256))
    city = Column(String(128))
    state = Column(String(64))
    country = Column(String(64))
    zip_code = Column(String(32))
    inspection_end_date = Column(Date)
    product_type = Column(String(128))
    center = Column(String(32))  # CDER, CBER, CVM, etc.
    pdf_url = Column(Text)
    pdf_local_path = Column(Text)
    pdf_downloaded = Column(Boolean, default=False)
    raw_text = Column(Text)
    num_observations = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    observations = relationship("Observation", back_populates="inspection", cascade="all, delete-orphan")
    analysis = relationship("InspectionAnalysis", back_populates="inspection", uselist=False, cascade="all, delete-orphan")


class Observation(Base):
    __tablename__ = "observations"

    id = Column(Integer, primary_key=True)
    inspection_id = Column(Integer, ForeignKey("inspections.id"), nullable=False)
    observation_number = Column(Integer)
    observation_text = Column(Text)
    gmp_category = Column(String(128))  # e.g., "Documentation", "CAPA", "Quality Systems"
    created_at = Column(DateTime, default=datetime.utcnow)

    inspection = relationship("Inspection", back_populates="observations")
    gmp_mappings = relationship("GMPMapping", back_populates="observation", cascade="all, delete-orphan")


class GMPMapping(Base):
    __tablename__ = "gmp_mappings"

    id = Column(Integer, primary_key=True)
    observation_id = Column(Integer, ForeignKey("observations.id"), nullable=False)
    framework = Column(String(32))       # EU_GMP, FDA_GMP, PICS, ICH, WHO
    reference_code = Column(String(128)) # e.g., "21 CFR 211.68", "EU GMP Chapter 4"
    reference_title = Column(String(256))
    relevance_explanation = Column(Text)

    observation = relationship("Observation", back_populates="gmp_mappings")


class InspectionAnalysis(Base):
    __tablename__ = "inspection_analyses"

    id = Column(Integer, primary_key=True)
    inspection_id = Column(Integer, ForeignKey("inspections.id"), nullable=False, unique=True)
    executive_summary = Column(Text)
    key_themes = Column(JSON)           # list of theme strings
    risk_level = Column(String(16))     # Critical, Major, Minor
    top_gmp_gaps = Column(JSON)         # list of {framework, reference, gap_description}
    recommendations = Column(Text)
    model_used = Column(String(64))
    analyzed_at = Column(DateTime, default=datetime.utcnow)

    inspection = relationship("Inspection", back_populates="analysis")


class WeeklyReport(Base):
    __tablename__ = "weekly_reports"

    id = Column(Integer, primary_key=True)
    report_week_start = Column(Date)
    report_week_end = Column(Date)
    total_inspections = Column(Integer)
    total_observations = Column(Integer)
    report_markdown = Column(Text)
    report_path = Column(Text)
    generated_at = Column(DateTime, default=datetime.utcnow)
