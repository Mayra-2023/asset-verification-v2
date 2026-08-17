from flask import Flask, render_template, request, redirect, url_for, flash
import os
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials
import cloudinary
import cloudinary.uploader

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "asset-verification-secret")

# ============================================================
# GOOGLE SHEETS
# ============================================================

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


def get_google_credentials():
    """
    Creates Google credentials from the GOOGLE_CREDENTIALS
    environment variable stored in Render.
    """
    credentials_json = os.environ.get("GOOGLE_CREDENTIALS")

    if not credentials_json:
        raise Exception("GOOGLE_CREDENTIALS environment variable is missing.")

    import json

    credentials_data = json.loads(credentials_json)

    return Credentials.from_service_account_info(
        credentials_data,
        scopes=SCOPES
    )


def get_sheet():
    """
    Opens the Google Spreadsheet and the Assets worksheet.
    """

    credentials = get_google_credentials()

    client = gspread.authorize(credentials)

    spreadsheet_id = os.environ.get("GOOGLE_SHEET_ID")

    if not spreadsheet_id:
        raise Exception("GOOGLE_SHEET_ID environment variable is missing.")

    spreadsheet = client.open_by_key(spreadsheet_id)

    try:
        worksheet = spreadsheet.worksheet("Assets")
    except gspread.WorksheetNotFound:
        worksheet = spreadsheet.add_worksheet(
            title="Assets",
            rows=1000,
            cols=20
        )

        headers = [
            "Asset ID",
            "Fleet Number",
            "Year",
            "Registration Number",
            "Fleet Type",
            "Description",
            "Make",
            "Model",
            "Engine Number",
            "Chassis Number",
            "Depot",
            "Status",
            "Verification Status",
            "Captured By",
            "Employee Number",
            "Photo URL",
            "Verification Date",
            "Notes",
            "Created At"
        ]

        worksheet.append_row(headers)

    return worksheet


# ============================================================
# CLOUDINARY
# ============================================================

cloudinary.config(
    cloud_name=os.environ.get("CLOUDINARY_CLOUD_NAME"),
    api_key=os.environ.get("CLOUDINARY_API_KEY"),
    api_secret=os.environ.get("CLOUDINARY_API_SECRET")
)


# ============================================================
# HELPERS
# ============================================================

HEADERS = [
    "Asset ID",
    "Fleet Number",
    "Year",
    "Registration Number",
    "Fleet Type",
    "Description",
    "Make",
    "Model",
    "Engine Number",
    "Chassis Number",
    "Depot",
    "Status",
    "Verification Status",
    "Captured By",
    "Employee Number",
    "Photo URL",
    "Verification Date",
    "Notes",
    "Created At"
]


def get_all_assets():
    worksheet = get_sheet()

    records = worksheet.get_all_records()

    return records


def calculate_verification_status(verification_date, status):
    if str(status).strip().lower() == "missing":
        return "Missing"

    if not verification_date:
        return "Overdue"

    try:
        date_value = datetime.strptime(
            str(verification_date),
            "%Y-%m-%d %H:%M:%S"
        )

        days = (datetime.now() - date_value).days

        if days <= 180:
            return "Verified"

        return "Overdue"

    except Exception:
        return "Overdue"


# ============================================================
# HOME
# ============================================================

@app.route("/")
def index():

    try:
        assets = get_all_assets()

        total = len(assets)

        verified = sum(
            1 for a in assets
            if a.get("Verification Status") == "Verified"
        )

        overdue = sum(
            1 for a in assets
            if a.get("Verification Status") == "Overdue"
        )

        missing = sum(
            1 for a in assets
            if a.get("Verification Status") == "Missing"
        )

        return render_template(
            "index.html",
            assets=assets,
            total=total,
            verified=verified,
            overdue=overdue,
            missing=missing
        )

    except Exception as e:

        return f"""
        <h2>Asset Verification System</h2>
        <p>System configuration is not complete.</p>
        <p><strong>Error:</strong> {e}</p>
        """


# ============================================================
# ADD ASSET
# ============================================================

@app.route("/add-asset", methods=["GET", "POST"])
def add_asset():

    if request.method == "POST":

        try:

            worksheet = get_sheet()

            asset_id = request.form.get("asset_id", "").strip()

            if not asset_id:
                flash("Asset ID is required.", "danger")
                return redirect(url_for("add_asset"))

            # Check duplicate Asset ID
            existing_assets = worksheet.get_all_records()

            for asset in existing_assets:

                if str(asset.get("Asset ID", "")).strip() == asset_id:

                    flash(
                        f"Asset {asset_id} already exists.",
                        "danger"
                    )

                    return redirect(url_for("add_asset"))

            photo_url = ""

            # Upload image to Cloudinary
            image = request.files.get("image")

            if image and image.filename:

                result = cloudinary.uploader.upload(
                    image,
                    folder="asset-verification"
                )

                photo_url = result.get("secure_url", "")

            status = request.form.get(
                "status",
                "Active"
            )

            verification_date = datetime.now().strftime(
                "%Y-%m-%d %H:%M:%S"
            )

            verification_status = calculate_verification_status(
                verification_date,
                status
            )

            row = [
                asset_id,
                request.form.get("fleet_number", ""),
                request.form.get("year", ""),
                request.form.get("registration_number", ""),
                request.form.get("fleet_type", ""),
                request.form.get("description", ""),
                request.form.get("make", ""),
                request.form.get("model", ""),
                request.form.get("engine_number", ""),
                request.form.get("chassis_number", ""),
                request.form.get("depot", ""),
                status,
                verification_status,
                request.form.get("captured_by", ""),
                request.form.get("employee_number", ""),
                photo_url,
                verification_date,
                request.form.get("notes", ""),
                datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            ]

            worksheet.append_row(row)

            flash(
                "Asset successfully added.",
                "success"
            )

            return redirect(url_for("index"))

        except Exception as e:

            flash(
                f"Error adding asset: {e}",
                "danger"
            )

            return redirect(url_for("add_asset"))

    return render_template("add_asset.html")


# ============================================================
# SEARCH
# ============================================================

@app.route("/search")
def search():

    query = request.args.get("q", "").strip().lower()

    assets = get_all_assets()

    results = []

    if query:

        for asset in assets:

            searchable = " ".join([
                str(asset.get("Asset ID", "")),
                str(asset.get("Fleet Number", "")),
                str(asset.get("Registration Number", "")),
                str(asset.get("Description", "")),
                str(asset.get("Depot", ""))
            ]).lower()

            if query in searchable:
                results.append(asset)

    return render_template(
        "search.html",
        results=results,
        query=query
    )


# ============================================================
# UPDATE REQUIRED
# ============================================================

@app.route("/updates")
def updates():

    assets = get_all_assets()

    overdue_assets = []

    for asset in assets:

        verification_status = asset.get(
            "Verification Status",
            ""
        )

        if verification_status in [
            "Overdue",
            "Missing"
        ]:

            overdue_assets.append(asset)

    return render_template(
        "updates.html",
        assets=overdue_assets
    )


# ============================================================
# DASHBOARD
# ============================================================

@app.route("/dashboard")
def dashboard():

    assets = get_all_assets()

    status_counts = {}

    depot_counts = {}

    for asset in assets:

        status = asset.get(
            "Status",
            "Unknown"
        )

        depot = asset.get(
            "Depot",
            "Unknown"
        )

        status_counts[status] = (
            status_counts.get(status, 0) + 1
        )

        depot_counts[depot] = (
            depot_counts.get(depot, 0) + 1
        )

    return render_template(
        "dashboard.html",
        assets=assets,
        status_counts=status_counts,
        depot_counts=depot_counts
    )


# ============================================================
# HEALTH CHECK
# ============================================================

@app.route("/health")
def health():

    return {
        "status": "ok",
        "service": "Asset Verification System"
    }


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":

    port = int(
        os.environ.get(
            "PORT",
            5000
        )
    )

    app.run(
        host="0.0.0.0",
        port=port
    )
