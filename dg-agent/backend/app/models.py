"""Database schema.

Regulatory data is version-controlled: every dangerous goods entry belongs to a
RegulatorySource (publisher / edition / amendment / effective dates / licence) and
carries its own verification status. Engines never treat data as authoritative
unless both the source and the entry are marked verified by a qualified person.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import JSON, Boolean, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


# --- verification vocabularies -------------------------------------------------
SOURCE_VERIFICATION = ("verified", "unverified", "demo_seed", "test_fixture")
SOURCE_STATUS = ("current", "superseded", "not_yet_effective", "catalogue_only")
RULE_SETS = ("UN_MODEL", "IMDG", "IATA", "SITE")


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(255), default="")
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(32), default="viewer")
    qualification: Mapped[str] = mapped_column(String(255), default="")  # e.g. "DGSA cert no..., IMDG trained"
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class RegulatorySource(Base):
    __tablename__ = "regulatory_sources"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True)  # stable key e.g. "IMDG-42-24"
    rule_set: Mapped[str] = mapped_column(String(16))  # UN_MODEL | IMDG | IATA | SITE
    publisher: Mapped[str] = mapped_column(String(255))
    title: Mapped[str] = mapped_column(String(512))
    edition: Mapped[str] = mapped_column(String(128), default="")
    amendment: Mapped[str] = mapped_column(String(128), default="")
    publication_date: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    effective_date: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    expiry_date: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    licence: Mapped[str] = mapped_column(Text, default="")
    authorized_usage: Mapped[str] = mapped_column(Text, default="")
    location: Mapped[str] = mapped_column(String(1024), default="")
    ingestion_date: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    verification_status: Mapped[str] = mapped_column(String(32), default="unverified")
    status: Mapped[str] = mapped_column(String(32), default="current")
    content_loaded: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str] = mapped_column(Text, default="")
    entries: Mapped[list[DGEntry]] = relationship(back_populates="source")


class DGEntry(Base):
    """One Dangerous Goods List entry within a specific source/edition."""

    __tablename__ = "dg_entries"
    __table_args__ = (UniqueConstraint("source_id", "un_number", "variant", name="uq_entry_variant"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("regulatory_sources.id"), index=True)
    un_number: Mapped[str] = mapped_column(String(8), index=True)  # "UN1203" / "ID8000"
    variant: Mapped[str] = mapped_column(String(64), default="")  # distinguishes multiple rows for one UN no.
    proper_shipping_name: Mapped[str] = mapped_column(String(512))
    hazard_class: Mapped[str] = mapped_column(String(8))
    subsidiary_hazards: Mapped[list] = mapped_column(JSON, default=list)
    packing_groups: Mapped[list] = mapped_column(JSON, default=list)  # [] => not applicable / not assigned
    special_provisions: Mapped[list | None] = mapped_column(JSON, nullable=True)  # None => not loaded
    marine_pollutant: Mapped[str | None] = mapped_column(String(16), nullable=True)  # "P" | "-" | None(not loaded)
    mode_data: Mapped[dict] = mapped_column(JSON, default=dict)  # e.g. {"ems": "F-E,S-E", "segregation_codes": [...]}
    section_ref: Mapped[str] = mapped_column(String(255), default="")
    synonyms: Mapped[list] = mapped_column(JSON, default=list)
    cas_numbers: Mapped[list] = mapped_column(JSON, default=list)
    verification_status: Mapped[str] = mapped_column(String(32), default="unverified")
    verified_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    verified_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    verification_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[RegulatorySource] = relationship(back_populates="entries")


class RuleTable(Base):
    """Deterministic rule tables (e.g. IMDG 7.2.4 segregation table) with provenance."""

    __tablename__ = "rule_tables"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("regulatory_sources.id"))
    name: Mapped[str] = mapped_column(String(255))
    section_ref: Mapped[str] = mapped_column(String(255), default="")
    data: Mapped[dict] = mapped_column(JSON)
    complete: Mapped[bool] = mapped_column(Boolean, default=False)  # False => known subset only
    verification_status: Mapped[str] = mapped_column(String(32), default="unverified")
    verified_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    verified_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[RegulatorySource] = relationship()


class StoredFile(Base):
    __tablename__ = "stored_files"
    id: Mapped[int] = mapped_column(primary_key=True)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    original_name: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(128))
    size: Mapped[int] = mapped_column(Integer)
    path: Mapped[str] = mapped_column(String(1024))
    purpose: Mapped[str] = mapped_column(String(64))  # sds | photo | document
    uploaded_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    extraction: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class Report(Base):
    """Any generated record: verification, segregation, spill, ERP, inspection, risk..."""

    __tablename__ = "reports"
    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(48), index=True)
    title: Mapped[str] = mapped_column(String(512))
    status: Mapped[str] = mapped_column(String(32), default="draft")  # draft|pending_review|approved|rejected
    criticality: Mapped[str] = mapped_column(String(16), default="critical")  # critical | standard
    content: Mapped[dict] = mapped_column(JSON)
    inputs: Mapped[dict] = mapped_column(JSON, default=dict)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    approvals: Mapped[list[Approval]] = relationship(back_populates="report", order_by="Approval.id")


class Approval(Base):
    __tablename__ = "approvals"
    id: Mapped[int] = mapped_column(primary_key=True)
    report_id: Mapped[int] = mapped_column(ForeignKey("reports.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    decision: Mapped[str] = mapped_column(String(32))  # submitted|reviewed|approved|rejected
    comment: Mapped[str] = mapped_column(Text, default="")
    qualification: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    report: Mapped[Report] = relationship(back_populates="approvals")


class CorrectiveAction(Base):
    __tablename__ = "corrective_actions"
    id: Mapped[int] = mapped_column(primary_key=True)
    report_id: Mapped[int | None] = mapped_column(ForeignKey("reports.id"), nullable=True, index=True)
    description: Mapped[str] = mapped_column(Text)
    action_type: Mapped[str] = mapped_column(String(16), default="corrective")  # corrective|preventive
    responsible: Mapped[str] = mapped_column(String(255), default="")
    due_date: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="open")  # open|in_progress|closed
    closure_note: Mapped[str] = mapped_column(Text, default="")
    closed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    closed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class RiskMatrix(Base):
    __tablename__ = "risk_matrices"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True)
    config: Mapped[dict] = mapped_column(JSON)  # likelihood[], severity[], bands[]
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)


class AuditLog(Base):
    """Append-only, hash-chained audit trail (DB triggers block UPDATE/DELETE)."""

    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    ts: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    user_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    action: Mapped[str] = mapped_column(String(64), index=True)
    entity: Mapped[str] = mapped_column(String(64), default="")
    entity_id: Mapped[str] = mapped_column(String(64), default="")
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    prev_hash: Mapped[str] = mapped_column(String(64))
    hash: Mapped[str] = mapped_column(String(64), unique=True)
