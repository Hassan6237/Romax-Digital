"""
Romax Digital – Wallet Pass Creator
portal.py – Logged-in area: dashboard, saved passes, Wallet credential setup
"""

import json
import os

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, send_file
from flask_login import login_required, current_user
from cryptography import x509
from cryptography.hazmat.primitives import serialization

from extensions import db
from models import SavedPass
from config import apple_cert_dir, google_cert_dir, PASSES_DIR

portal_bp = Blueprint("portal", __name__)


# Stage 5 – Select Subscription (prototype: captures the choice, pricing TBD)

PLANS = [
    {"id": "starter", "name": "Starter", "blurb": "Small teams getting started", "features": ["1 programme", "Up to 500 members", "Standard support"]},
    {"id": "growth", "name": "Growth", "blurb": "Growing organisations", "features": ["Up to 5 programmes", "Up to 10,000 members", "Priority support"]},
    {"id": "enterprise", "name": "Enterprise", "blurb": "Fully managed at scale", "features": ["Unlimited programmes", "Unlimited members", "Dedicated account manager"]},
]


@portal_bp.route("/subscription", methods=["GET", "POST"])
@login_required
def subscription():
    if request.method == "POST":
        current_user.selected_plan = request.form.get("plan", "starter")
        current_user.billing_frequency = request.form.get("billing_frequency", "monthly")
        db.session.commit()
        flash("Subscription selected — pricing is still to be confirmed by our team before you go live.", "success")
        return redirect(url_for("portal.dashboard"))

    return render_template(
        "subscription.html",
        plans=PLANS,
        selected_plan=getattr(current_user, "selected_plan", None) or "growth",
        billing_frequency=getattr(current_user, "billing_frequency", None) or "monthly",
    )



@portal_bp.route("/dashboard")
@login_required
def dashboard():
    my_passes = (SavedPass.query
                 .filter_by(user_id=current_user.id)
                 .order_by(SavedPass.created_at.desc())
                 .all())
    return render_template("dashboard.html", passes=my_passes)


# Wallet credential setup (Apple certs + Google service account)

@portal_bp.route("/settings/wallet", methods=["GET", "POST"])
@login_required
def wallet_settings():
    if request.method == "POST":
        section = request.form.get("section")

        if section == "apple":
            current_user.apple_team_id = (request.form.get("apple_team_id") or "").strip()
            current_user.apple_pass_type_id = (request.form.get("apple_pass_type_id") or "").strip()
            current_user.apple_key_password = request.form.get("apple_key_password") or ""

            cert_file = request.files.get("apple_cert")
            key_file = request.files.get("apple_key")
            wwdr_file = request.files.get("apple_wwdr")

            if cert_file and key_file and wwdr_file and all(f.filename for f in (cert_file, key_file, wwdr_file)):
                cert_bytes = cert_file.read()
                key_bytes = key_file.read()
                wwdr_bytes = wwdr_file.read()
                try:
                    x509.load_pem_x509_certificate(cert_bytes)
                    x509.load_pem_x509_certificate(wwdr_bytes)
                    serialization.load_pem_private_key(
                        key_bytes,
                        password=(current_user.apple_key_password.encode()
                                  if current_user.apple_key_password else None),
                    )
                except Exception as exc:
                    flash(f"Could not validate Apple certificates: {exc}", "error")
                    db.session.commit()
                    return redirect(url_for("portal.wallet_settings"))

                cdir = apple_cert_dir(current_user.id)
                with open(os.path.join(cdir, "cert.pem"), "wb") as f:
                    f.write(cert_bytes)
                with open(os.path.join(cdir, "key.pem"), "wb") as f:
                    f.write(key_bytes)
                with open(os.path.join(cdir, "wwdr.pem"), "wb") as f:
                    f.write(wwdr_bytes)
                current_user.apple_certs_uploaded = True
                flash("Apple Wallet certificates verified & saved. Passes will now be signed for real.", "success")

            db.session.commit()

        elif section == "google":
            current_user.google_issuer_id = (request.form.get("google_issuer_id") or "").strip()
            current_user.google_class_suffix = (request.form.get("google_class_suffix") or "romax_generic_class").strip()

            sa_file = request.files.get("google_service_account")
            if sa_file and sa_file.filename:
                raw = sa_file.read()
                try:
                    data = json.loads(raw)
                    assert data.get("private_key") and data.get("client_email")
                except Exception:
                    flash("That doesn't look like a valid Google service-account JSON key.", "error")
                    db.session.commit()
                    return redirect(url_for("portal.wallet_settings"))

                gdir = google_cert_dir(current_user.id)
                with open(os.path.join(gdir, "service_account.json"), "wb") as f:
                    f.write(raw)
                current_user.google_creds_uploaded = True
                current_user.google_service_account_email = data.get("client_email", "")
                flash("Google Wallet service account verified & saved. Passes will now generate real save links.", "success")

            db.session.commit()

        return redirect(url_for("portal.wallet_settings"))

    return render_template("settings_wallet.html")


@portal_bp.route("/settings/wallet/remove/<provider>", methods=["POST"])
@login_required
def wallet_settings_remove(provider):
    if provider == "apple":
        cdir = apple_cert_dir(current_user.id)
        for fname in ("cert.pem", "key.pem", "wwdr.pem"):
            p = os.path.join(cdir, fname)
            if os.path.exists(p):
                os.remove(p)
        current_user.apple_certs_uploaded = False
        flash("Apple Wallet credentials removed.", "success")
    elif provider == "google":
        gdir = google_cert_dir(current_user.id)
        p = os.path.join(gdir, "service_account.json")
        if os.path.exists(p):
            os.remove(p)
        current_user.google_creds_uploaded = False
        flash("Google Wallet credentials removed.", "success")
    db.session.commit()
    return redirect(url_for("portal.wallet_settings"))


# Saved passes API (dashboard <-> creator)

@portal_bp.route("/api/my-passes")
@login_required
def api_my_passes():
    my_passes = (SavedPass.query
                 .filter_by(user_id=current_user.id)
                 .order_by(SavedPass.created_at.desc())
                 .all())
    return jsonify([p.to_dict() for p in my_passes])


@portal_bp.route("/api/save-pass", methods=["POST"])
@login_required
def api_save_pass():
    cfg = request.get_json(force=True) or {}
    if not cfg.get("brand_name"):
        return jsonify({"error": "Nothing to save yet — create a pass first."}), 400

    saved = SavedPass(
        user_id=current_user.id,
        serial=cfg.get("serial") or "DRAFT",
        brand_name=cfg.get("brand_name", ""),
        pass_type=cfg.get("pass_type", ""),
        design_variant=cfg.get("design_variant", "brand-bold"),
        config_json=json.dumps(cfg),
    )
    db.session.add(saved)
    db.session.commit()
    return jsonify({"saved": True, "pass": saved.to_dict()})


@portal_bp.route("/api/my-passes/<int:pass_id>", methods=["DELETE"])
@login_required
def api_delete_pass(pass_id):
    saved = SavedPass.query.filter_by(id=pass_id, user_id=current_user.id).first()
    if not saved:
        return jsonify({"error": "Not found"}), 404
    db.session.delete(saved)
    db.session.commit()
    return jsonify({"deleted": True})
