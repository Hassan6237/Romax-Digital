"""
Romax Digital – Wallet Pass Creator
auth.py – Signup / Login / Logout (session-based, Flask-Login)
"""

import re

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_user, logout_user, login_required, current_user

from extensions import db
from models import User

auth_bp = Blueprint("auth", __name__)

EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")


@auth_bp.route("/signup", methods=["GET", "POST"])
def signup():
    if current_user.is_authenticated:
        return redirect(url_for("portal.dashboard"))

    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        organisation = (request.form.get("organisation") or "").strip()
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        confirm = request.form.get("confirm") or ""
        accept_terms = bool(request.form.get("accept_terms"))

        error = None
        if not name or not email or not password:
            error = "Please fill in your name, email and password."
        elif not EMAIL_RE.match(email):
            error = "Please enter a valid email address."
        elif len(password) < 8:
            error = "Password must be at least 8 characters."
        elif password != confirm:
            error = "Passwords do not match."
        elif not accept_terms:
            error = "Please accept the Terms & Conditions to continue."
        elif User.query.filter_by(email=email).first():
            error = "An account with that email already exists."

        if error:
            flash(error, "error")
            return render_template("signup.html", form={"name": name, "organisation": organisation, "email": email})

        user = User(name=name, organisation=organisation, email=email)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        login_user(user)
        flash(f"Welcome to Romax Digital, {user.name.split(' ')[0]}!", "success")
        return redirect(url_for("portal.dashboard"))

    # Stage 2 reuses Company / Contact / Email collected in Stage 1 (test card)
    prefill = {
        "name": request.args.get("name", ""),
        "organisation": request.args.get("organisation", ""),
        "email": request.args.get("email", ""),
    }
    return render_template("signup.html", form=prefill)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("portal.dashboard"))

    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        remember = bool(request.form.get("remember"))

        user = User.query.filter_by(email=email).first()
        if user and user.check_password(password):
            login_user(user, remember=remember)
            flash(f"Welcome back, {user.name.split(' ')[0]}!", "success")
            next_url = request.args.get("next")
            return redirect(next_url or url_for("portal.dashboard"))

        flash("Incorrect email or password.", "error")
        return render_template("login.html", form={"email": email})

    return render_template("login.html", form={})


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You've been logged out.", "success")
    return redirect(url_for("index"))


@auth_bp.route("/api/me")
def api_me():
    if current_user.is_authenticated:
        return jsonify({"authenticated": True, "user": current_user.to_public_dict()})
    return jsonify({"authenticated": False})
