"""
Romax Digital – Website to Wallet Pass Creator
Backend: Python / Flask
"""

import os
import uuid
import hashlib
import datetime
import random

from flask import Flask, request, jsonify, render_template, send_file
from flask_cors import CORS
from flask_login import current_user

from config import Config, PASSES_DIR, apple_cert_dir, google_cert_dir
from extensions import db, login_manager
from models import User, Member
from scraping import scrape_website
from walletgen import build_pkpass, build_google_wallet_save_url
from auth import auth_bp
from portal import portal_bp


def _seed_demo_members():
    """Seed a small shared demo pool the first time the app runs, so the
    Members panel has something to show before a user adds their own.
    Not hardcoded into the API response — lives in the DB and can be
    edited/deleted like any other member from here on."""
    if Member.query.filter_by(user_id=None).first():
        return
    demo = [
        ("Alice Johnson", "Gold", "Active", 24),
        ("Bob Smith", "Silver", "Active", 11),
        ("Carol White", "Standard", "Expired", 7),
        ("David Lee", "Gold", "Active", 52),
        ("Eve Martin", "Silver", "Active", 3),
    ]
    for i, (name, tier, status, checkins) in enumerate(demo, start=1):
        db.session.add(Member(
            user_id=None,
            member_code=f"DEMO{i:03d}{tier[:1].upper()}",
            name=name, tier=tier, status=status, checkins=checkins,
            joined_at=datetime.date.today() - datetime.timedelta(days=random.randint(30, 700)),
        ))
    db.session.commit()


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    CORS(app)
    db.init_app(app)
    login_manager.init_app(app)

    app.register_blueprint(auth_bp)
    app.register_blueprint(portal_bp)

    with app.app_context():
        db.create_all()
        _seed_demo_members()

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    # Pages

    @app.route("/")
    def index():
        return render_template("journey.html")

    @app.route("/trial")
    def trial():
        return render_template("index.html")

    # Scraping

    @app.route("/api/scrape", methods=["POST"])
    def api_scrape():
        data = request.get_json(force=True)
        url = (data.get("url") or "").strip()
        if not url:
            return jsonify({"error": "No URL provided"}), 400
        result = scrape_website(url)
        if "error" in result:
            return jsonify(result), 422
        return jsonify(result)

    # Wallet pass generation — REAL Apple .pkpass + REAL Google save link

    @app.route("/api/generate-pass/apple", methods=["POST"])
    def api_generate_apple():
        cfg = request.get_json(force=True) or {}
        pass_id = str(uuid.uuid4())
        serial = hashlib.md5(pass_id.encode()).hexdigest()[:12].upper()

        user = current_user if current_user.is_authenticated else None
        cert_dir = apple_cert_dir(user.id) if user else None

        pkpass_bytes, signed, sign_error = build_pkpass(cfg, serial, user=user, cert_dir=cert_dir)

        filename = f"romax_{serial}.pkpass"
        path = os.path.join(PASSES_DIR, filename)
        with open(path, "wb") as f:
            f.write(pkpass_bytes)

        return jsonify({
            "pass_id": pass_id,
            "serial": serial,
            "download_url": f"/api/download/{filename}",
            "signed": signed,
            "sign_error": sign_error,
            "wallet_ready": bool(user and user.apple_wallet_ready),
            "logged_in": bool(user),
        })

    @app.route("/api/generate-pass/google", methods=["POST"])
    def api_generate_google():
        cfg = request.get_json(force=True) or {}
        pass_id = str(uuid.uuid4())
        serial = hashlib.md5(pass_id.encode()).hexdigest()[:12].upper()

        user = current_user if current_user.is_authenticated else None
        cert_dir = google_cert_dir(user.id) if user else None

        if user:
            result = build_google_wallet_save_url(cfg, serial, user, cert_dir)
        else:
            result = {"configured": False, "reason": "Log in and connect Google Wallet to generate a real save link."}

        if not result.get("configured"):
            from walletgen import build_google_pass_objects
            preview_object = {
                "hexBackgroundColor": cfg.get("primary_color"),
                "cardTitle": cfg.get("brand_name"),
                "header": cfg.get("member_name"),
                "subheader": cfg.get("pass_type"),
            }
            if user:
                try:
                    _, preview_object = build_google_pass_objects(cfg, serial, user)
                except Exception:
                    pass
            result["preview_object"] = preview_object

        result["pass_id"] = pass_id
        result["serial"] = serial
        result["logged_in"] = bool(user)
        return jsonify(result)

    @app.route("/api/download/<path:filename>")
    def api_download(filename):
        path = os.path.join(PASSES_DIR, filename)
        if not os.path.exists(path):
            return jsonify({"error": "File not found"}), 404
        mimetype = "application/vnd.apple.pkpass" if filename.endswith(".pkpass") else "application/zip"
        return send_file(path, as_attachment=True, download_name=filename, mimetype=mimetype)

    # Member CRM — backed by the Member model, not hardcoded data.
    # Logged-in users see/manage their own members; signed-out visitors
    # (prototype/demo mode) see the shared demo pool (user_id IS NULL).

    @app.route("/api/members", methods=["GET"])
    def api_members():
        user = current_user if current_user.is_authenticated else None
        query = Member.query.filter_by(user_id=(user.id if user else None))
        members = [m.to_dict() for m in query.order_by(Member.joined_at.desc()).all()]
        return jsonify(members)

    @app.route("/api/members", methods=["POST"])
    def api_members_create():
        data = request.get_json(force=True) or {}
        name = (data.get("name") or "").strip()
        tier = (data.get("tier") or "Standard").strip() or "Standard"
        if not name:
            return jsonify({"error": "Member name is required."}), 400

        user = current_user if current_user.is_authenticated else None
        code = f"M{uuid.uuid4().hex[:8].upper()}"
        member = Member(user_id=(user.id if user else None), member_code=code,
                         name=name, tier=tier, status="Active", checkins=0,
                         joined_at=datetime.date.today())
        db.session.add(member)
        db.session.commit()
        return jsonify(member.to_dict()), 201

    @app.route("/api/members/<member_code>", methods=["DELETE"])
    def api_members_delete(member_code):
        user = current_user if current_user.is_authenticated else None
        member = Member.query.filter_by(member_code=member_code, user_id=(user.id if user else None)).first()
        if not member:
            return jsonify({"error": "Member not found."}), 404
        db.session.delete(member)
        db.session.commit()
        return jsonify({"deleted": True})

    @app.route("/api/verify", methods=["POST"])
    def api_verify():
        data = request.get_json(force=True)
        code = (data.get("code") or "").strip().upper()
        if not code:
            return jsonify({"valid": False, "message": "Enter a code to verify."})

        member = Member.query.filter(db.func.upper(Member.member_code) == code).first()
        if not member or member.status != "Active":
            return jsonify({"valid": False, "message": "Code not recognised or expired."})

        member.checkins = (member.checkins or 0) + 1
        member.last_checkin_at = datetime.datetime.utcnow()
        db.session.commit()

        expiry_date = (member.joined_at or datetime.date.today()) + datetime.timedelta(days=365)
        return jsonify({
            "valid": True,
            "member": member.name,
            "tier": member.tier,
            "status": member.status,
            "expires": expiry_date.strftime("%d/%m/%Y"),
            "checkin_time": member.last_checkin_at.strftime("%H:%M %d/%m/%Y"),
        })

    return app


app = create_app()

if __name__ == "__main__":
    app.run(debug=True, port=5000)
