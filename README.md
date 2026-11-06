# Romax Digital – Website to Wallet Pass Creator

> 🥇 **Winner of the Romax Digital Challenge at Hackabury 2026 (1st of 107 entrants).** The win led to a software development internship at Romax Digital.

Paste any company's website URL and get a branded **Apple Wallet** (`.pkpass`) or **Google Wallet** pass. The app scrapes the site's logo and colours, generates three design variants and lets you edit and preview the pass. It then exports a correctly structured pass, signed when Wallet credentials are connected.

**Stack:** Python · Flask · Flask-Login · SQLAlchemy (SQLite) · BeautifulSoup · Pillow · `cryptography` (PKCS#7) · PyJWT · vanilla JS

---

## 🚀 Quick Start

```bash
git clone https://github.com/Hassan6237/Romax-Digital.git
cd Romax-Digital
python -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
python app.py
# → http://localhost:5000
```

A local SQLite database and a random session secret key are created automatically in `instance/` on first run. That folder is git-ignored, so no credentials ever live in the repository. To set the key yourself, export `ROMAX_SECRET_KEY`. Set `FLASK_DEBUG=1` only for local debugging.

---

## ✨ Features

1. **User accounts (Sign Up / Log In)** — session-based auth (Flask-Login), so people can save designs and connect their own Wallet credentials.
2. **3 selectable design variants from one scrape** — *Brand Bold*, *Minimal Light*, *Dark Contrast* — all built from the exact colours pulled from the scraped site, no re-scraping needed. Pick one, it drives the whole editor + preview.
3. **Real Apple Wallet passes** — clicking **"Add to Apple Wallet"** now builds an actual `.pkpass`: generated icon/logo PNGs, a correct `manifest.json`, and — once you've uploaded your own Apple Pass Type certificates in **Wallet Setup** — a genuine detached CMS/PKCS#7 `signature` file, so the pass really installs on an iPhone. Without certificates connected, you still get the full, correctly-structured `.pkpass` as an "unsigned preview" so you can see exactly what will ship.
4. **Real Google Wallet passes** — clicking **"Add to Google Wallet"** builds a signed JWT (RS256, using your own Google service-account key) and opens the genuine `https://pay.google.com/gp/v/save/...` link, which creates and adds the pass — not a JSON dump.
5. **Dashboard** — every account gets a dashboard of saved pass designs, re-openable in the editor.
6. **Wallet Setup page** — where an organisation uploads its own Apple certs (`cert.pem` / `key.pem` / `wwdr.pem`) and Google service-account JSON key, with inline instructions on how to obtain them, so real (not preview) passes come out the other side.

The original creator flow, colour scheme, and layout are unchanged — this is additive.

---

## 📁 Project Structure

```
romax-digital/
├── app.py                  ← Flask app factory + API routes
├── auth.py                 ← Sign up / Log in / Log out (blueprint)
├── portal.py                ← Dashboard, Wallet Setup, saved-pass API (blueprint)
├── models.py                ← User + SavedPass (SQLAlchemy)
├── extensions.py             ← Shared db / login_manager instances
├── config.py                 ← Paths, secret key, cert storage folders
├── scraping.py               ← Website scraper + 3-variant design generator
├── walletgen.py              ← Real .pkpass builder (signing) + Google Wallet JWT builder
├── requirements.txt
├── start.sh
│
├── templates/
│   ├── index.html            ← Main creator (single-page app)
│   ├── layout.html           ← Shared nav/footer for the pages below
│   ├── login.html / signup.html
│   ├── dashboard.html
│   └── settings_wallet.html  ← Apple cert / Google service-account upload
│
├── static/
│   ├── css/main.css          ← Original styling + additive rules only
│   └── js/main.js
│
├── instance/                 ← SQLite DB + per-user Wallet credentials (gitignored)
└── passes/                   ← Generated .pkpass files (auto-created, gitignored)
```

---

## 🔌 Key API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| GET | `/` | Serve the frontend |
| POST | `/api/scrape` | Scrape a URL → brand data + 3 design variants |
| POST | `/api/generate-pass/apple` | Build a real (or unsigned-preview) `.pkpass` |
| POST | `/api/generate-pass/google` | Build a real (or preview) Google Wallet save link |
| GET | `/api/download/<file>` | Download a generated `.pkpass` |
| POST | `/api/save-pass` | Save current design to the logged-in user's dashboard *(auth required)* |
| GET | `/api/my-passes` | List the logged-in user's saved passes *(auth required)* |
| GET/POST | `/signup`, `/login`, `/logout` | Account management |
| GET | `/dashboard` | Saved passes + Wallet connection status *(auth required)* |
| GET/POST | `/settings/wallet` | Upload/remove Apple certs & Google service account *(auth required)* |
| GET | `/api/members` | Mock CRM member list |
| POST | `/api/verify` | Verify a QR/barcode code |

---

## 🍎 Apple Wallet — making it real

Go to **Wallet Setup** (top nav once logged in) and upload:

1. A **Pass Type ID certificate**, exported as `cert.pem` (from your Apple Developer account → Certificates, Identifiers & Profiles).
2. Its matching **private key**, exported as `key.pem`.
3. Apple's **WWDR intermediate certificate**, as `wwdr.pem`.
4. Your **Team ID** and **Pass Type Identifier**.

From then on, every `.pkpass` you export is signed with a real detached CMS/PKCS#7 signature and will install on an iPhone. Credentials are stored per-account under `instance/apple_certs/<user_id>/` and never leave the server.

## 🤖 Google Wallet — making it real

Go to **Wallet Setup** and upload:

1. Your Google Wallet **Issuer ID** (from the Google Pay & Wallet Console).
2. A **service-account JSON key** with access to that issuer account.

From then on, "Add to Google Wallet" opens a real, signed save link that creates the pass class/object and adds it to the user's Google Wallet on click.

---

## 🛠 Tech Stack

| Layer | Technology |
|---|---|
| Frontend | HTML5 / CSS3 / Vanilla JavaScript |
| Backend | Python 3 / Flask, Flask-Login, Flask-SQLAlchemy |
| Scraping | BeautifulSoup4 + requests |
| Pass images | Pillow (auto-generated icon/logo PNGs) |
| Apple signing | `cryptography` (PKCS#7/CMS detached signature) |
| Google Wallet | PyJWT (RS256-signed save link) |
| QR Codes | QRCode.js (CDN) + Canvas fallback |

---

## 🏆 About Romax Digital

Romax Digital helps organisations issue branded, personalised and secure digital cards stored in smartphone wallets — for access, membership, loyalty, ticketing and engagement.

🔗 [romax.co.uk/digital](https://romax.co.uk/digital/)

---

## 🔒 Security notes

- Passwords are hashed with Werkzeug (`generate_password_hash`) and never stored in plain text.
- The session secret key, database and uploaded Wallet certificates live in `instance/` and are git-ignored.
- Pass downloads are restricted to generated `.pkpass` files, which blocks path traversal.
- Debug mode is off unless `FLASK_DEBUG=1` is set.

---

*Hackathon prototype built by [Hassan Ali](https://github.com/Hassan6237). Romax Digital is a trademark of its owner.*
