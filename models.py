"""
Romax Digital – Wallet Pass Creator
models.py – SQLAlchemy models: User accounts + saved pass designs
"""

import datetime
import json

from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

from extensions import db


class User(db.Model, UserMixin):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    organisation = db.Column(db.String(160), default="")
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

    # ---- Apple Wallet configuration -------------------------------------
    apple_team_id = db.Column(db.String(60), default="")
    apple_pass_type_id = db.Column(db.String(160), default="")
    apple_key_password = db.Column(db.String(255), default="")
    apple_certs_uploaded = db.Column(db.Boolean, default=False)

    # ---- Google Wallet configuration -------------------------------------
    google_issuer_id = db.Column(db.String(60), default="")
    google_class_suffix = db.Column(db.String(120), default="romax_generic_class")
    google_service_account_email = db.Column(db.String(255), default="")
    google_creds_uploaded = db.Column(db.Boolean, default=False)

    # ---- Subscription (Stage 5) -------------------------------------------
    selected_plan = db.Column(db.String(40), default="")
    billing_frequency = db.Column(db.String(20), default="")

    passes = db.relationship("SavedPass", backref="owner", lazy=True,
                              cascade="all, delete-orphan")

    def set_password(self, raw_password: str):
        self.password_hash = generate_password_hash(raw_password)

    def check_password(self, raw_password: str) -> bool:
        return check_password_hash(self.password_hash, raw_password)

    @property
    def apple_wallet_ready(self) -> bool:
        return bool(self.apple_certs_uploaded and self.apple_team_id and self.apple_pass_type_id)

    @property
    def google_wallet_ready(self) -> bool:
        return bool(self.google_creds_uploaded and self.google_issuer_id)

    def to_public_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "email": self.email,
            "organisation": self.organisation,
            "apple_wallet_ready": self.apple_wallet_ready,
            "google_wallet_ready": self.google_wallet_ready,
        }


class Member(db.Model):
    __tablename__ = "members"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)
    member_code = db.Column(db.String(40), unique=True, nullable=False, index=True)
    name = db.Column(db.String(160), nullable=False)
    tier = db.Column(db.String(40), default="Standard")
    status = db.Column(db.String(20), default="Active")
    joined_at = db.Column(db.Date, default=datetime.date.today)
    checkins = db.Column(db.Integer, default=0)
    last_checkin_at = db.Column(db.DateTime, nullable=True)

    def to_dict(self):
        return {
            "id": self.member_code,
            "name": self.name,
            "tier": self.tier,
            "joined": self.joined_at.strftime("%Y-%m-%d") if self.joined_at else "",
            "status": self.status,
            "checkins": self.checkins,
        }


class SavedPass(db.Model):
    __tablename__ = "saved_passes"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    serial = db.Column(db.String(40), nullable=False)
    brand_name = db.Column(db.String(160), default="")
    pass_type = db.Column(db.String(80), default="")
    design_variant = db.Column(db.String(40), default="brand-bold")
    config_json = db.Column(db.Text, nullable=False)
    apple_filename = db.Column(db.String(255), default="")
    apple_signed = db.Column(db.Boolean, default=False)
    google_save_url = db.Column(db.Text, default="")
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

    @property
    def config(self):
        try:
            return json.loads(self.config_json)
        except Exception:
            return {}

    def to_dict(self):
        return {
            "id": self.id,
            "serial": self.serial,
            "brand_name": self.brand_name,
            "pass_type": self.pass_type,
            "design_variant": self.design_variant,
            "config": self.config,
            "apple_filename": self.apple_filename,
            "apple_signed": self.apple_signed,
            "google_save_url": self.google_save_url,
            "created_at": self.created_at.strftime("%d/%m/%Y %H:%M"),
        }
