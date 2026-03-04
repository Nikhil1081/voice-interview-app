import os
import uuid
import csv
import io
from datetime import datetime, timedelta

from flask import (
    Flask, render_template, request, redirect, url_for,
    flash, session, send_from_directory, abort, jsonify, Response
)
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import inspect, or_, text
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "change-this-secret-key-in-production")

app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv(
    "DATABASE_URL",
    "sqlite:///" + os.path.join(BASE_DIR, "interview.db")
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

UPLOAD_FOLDER = os.getenv("UPLOAD_FOLDER") or os.path.join(BASE_DIR, "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # 50MB max file

db = SQLAlchemy(app)


# -------------------- DB MODELS --------------------
class Admin(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)


class Question(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    text = db.Column(db.Text, nullable=False)
    # 0/NULL means no time limit.
    duration_minutes = db.Column(db.Integer, nullable=True, default=2)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Candidate(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    email = db.Column(db.String(200), nullable=False, unique=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Submission(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    candidate_id = db.Column(db.Integer, db.ForeignKey("candidate.id"), nullable=False)
    candidate = db.relationship("Candidate", backref=db.backref("submissions", lazy=True))

    question_id = db.Column(db.Integer, db.ForeignKey("question.id"), nullable=False)
    question = db.relationship("Question", backref=db.backref("submissions", lazy=True))

    audio_filename = db.Column(db.String(255), nullable=False)
    transcript = db.Column(db.Text, nullable=True)
    feedback = db.Column(db.Text, nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# -------------------- INIT DB + DEFAULT ADMIN --------------------
def create_default_admin():
    """Create a default admin if none exists"""
    existing = Admin.query.first()
    if not existing:
        default_user = os.getenv("ADMIN_USERNAME", "admin")
        default_pass = os.getenv("ADMIN_PASSWORD", "admin123")
        admin = Admin(
            username=default_user,
            password_hash=generate_password_hash(default_pass)
        )
        db.session.add(admin)
        db.session.commit()
        print("✅ Default admin created:")
        print(f"   Username: {default_user}")
        print(f"   Password: {default_pass}")


def create_sample_questions_if_empty():
    """Create sample questions if database is empty"""
    if Question.query.count() == 0:
        sample = [
            "Tell me about yourself in 30 seconds.",
            "Why do you want this internship?",
            "Explain a project you built and what challenges you faced."
        ]
        for q in sample:
            db.session.add(Question(text=q, duration_minutes=2))
        db.session.commit()
        print("✅ Sample questions created.")


def ensure_schema_columns():
    """Best-effort schema migration for small, single-file deployments.

    This project does not use Alembic. Streamlit/Render deployments may boot
    against an existing SQLite/Postgres database. We add new columns if missing.
    """

    inspector = inspect(db.engine)
    try:
        columns = {c["name"] for c in inspector.get_columns("question")}
    except Exception:
        # If reflection fails for any reason, don't block app startup.
        return

    if "duration_minutes" not in columns:
        try:
            with db.engine.begin() as conn:
                conn.execute(text("ALTER TABLE question ADD COLUMN duration_minutes INTEGER"))
                conn.execute(
                    text(
                        "UPDATE question SET duration_minutes = :d "
                        "WHERE duration_minutes IS NULL"
                    ),
                    {"d": 2},
                )
        except Exception:
            # Don't crash the app if ALTER TABLE isn't supported by the backing DB.
            return


with app.app_context():
    db.create_all()
    ensure_schema_columns()
    create_default_admin()
    create_sample_questions_if_empty()


# -------------------- HELPERS --------------------
def admin_required():
    """Check if user is logged in as admin"""
    if "admin_id" not in session:
        flash("Please login as admin.", "warning")
        return False
    return True


def admin_required_api():
    """Check admin auth for JSON endpoints."""
    return "admin_id" in session


def _json_body() -> dict:
    data = request.get_json(silent=True)
    if isinstance(data, dict):
        return data
    return {}


def allowed_audio(filename):
    """Check if uploaded file is a valid audio format"""
    allowed = {"webm", "wav", "mp3", "ogg", "m4a", "flac"}
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return ext in allowed


# -------------------- CANDIDATE ROUTES --------------------
@app.route("/")
def index():
    """Homepage"""
    return render_template("index.html")


@app.route("/interview", methods=["GET", "POST"])
def interview():
    """Candidate interview page - record answers"""
    questions = Question.query.order_by(Question.id.asc()).all()
    if not questions:
        flash("No questions set by admin yet.", "danger")
        return render_template("interview.html", questions=[])

    if request.method == "GET":
        return render_template("interview.html", questions=questions)

    # POST: Candidate details + audio files
    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip()

    if not name or not email:
        flash("Name and Email are required.", "danger")
        return redirect(url_for("interview"))

    # Check if candidate already exists
    existing_candidate = Candidate.query.filter_by(email=email).first()
    if existing_candidate:
        flash("This email has already submitted an interview.", "info")
        return redirect(url_for("interview"))

    # Create candidate
    candidate = Candidate(name=name, email=email)
    db.session.add(candidate)
    db.session.commit()

    # For each question, expect file field: audio_<question_id>
    saved_count = 0
    for q in questions:
        file_key = f"audio_{q.id}"
        audio_file = request.files.get(file_key)

        if not audio_file or audio_file.filename == "":
            continue

        filename = secure_filename(audio_file.filename)
        if not allowed_audio(filename):
            flash(f"Invalid audio format for question {q.id}.", "danger")
            continue

        ext = filename.rsplit(".", 1)[-1].lower()
        unique_name = f"{uuid.uuid4().hex}_q{q.id}.{ext}"
        path = os.path.join(app.config["UPLOAD_FOLDER"], unique_name)
        audio_file.save(path)

        submission = Submission(
            candidate_id=candidate.id,
            question_id=q.id,
            audio_filename=unique_name
        )
        db.session.add(submission)
        saved_count += 1

    db.session.commit()

    if saved_count == 0:
        flash("No audio was submitted. Please record at least one answer.", "warning")
        # Delete candidate if no submissions
        Candidate.query.filter_by(id=candidate.id).delete()
        db.session.commit()
        return redirect(url_for("interview"))

    flash(f"✅ Interview submitted successfully! {saved_count} answers recorded.", "success")
    return render_template("thankyou.html", candidate_name=name)


@app.route("/uploads/<filename>")
def uploaded_file(filename):
    """Serve uploaded audio files"""
    try:
        return send_from_directory(app.config["UPLOAD_FOLDER"], filename)
    except FileNotFoundError:
        abort(404)


# -------------------- ADMIN AUTH --------------------
@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    """Admin login page"""
    if request.method == "GET":
        return render_template("admin/login.html")

    username = request.form.get("username", "").strip()
    password = request.form.get("password", "").strip()

    admin = Admin.query.filter_by(username=username).first()
    if not admin or not check_password_hash(admin.password_hash, password):
        flash("Invalid admin credentials.", "danger")
        return redirect(url_for("admin_login"))

    session["admin_id"] = admin.id
    flash("✅ Logged in successfully.", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/logout")
def admin_logout():
    """Admin logout"""
    session.clear()
    flash("Logged out successfully.", "info")
    return redirect(url_for("admin_login"))


# -------------------- ADMIN DASHBOARD --------------------
@app.route("/admin")
def admin_dashboard():
    """Admin dashboard with statistics"""
    if not admin_required():
        return redirect(url_for("admin_login"))

    now = datetime.utcnow()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    total_candidates = Candidate.query.count()
    total_questions = Question.query.count()
    total_submissions = Submission.query.count()

    candidates_today = Candidate.query.filter(Candidate.created_at >= today_start).count()
    submissions_today = Submission.query.filter(Submission.created_at >= today_start).count()
    feedback_done = Submission.query.filter(Submission.feedback.isnot(None)).count()
    feedback_pending = max(total_submissions - feedback_done, 0)

    latest_submissions = Submission.query.order_by(Submission.created_at.desc()).limit(10).all()

    return render_template(
        "admin/dashboard.html",
        total_candidates=total_candidates,
        total_questions=total_questions,
        total_submissions=total_submissions,
        candidates_today=candidates_today,
        submissions_today=submissions_today,
        feedback_done=feedback_done,
        feedback_pending=feedback_pending,
        latest_submissions=latest_submissions
    )


# -------------------- ADMIN QUESTIONS CRUD --------------------
@app.route("/admin/questions", methods=["GET", "POST"])
def admin_questions():
    """Manage interview questions"""
    if not admin_required():
        return redirect(url_for("admin_login"))

    if request.method == "POST":
        text = request.form.get("text", "").strip()
        if text:
            db.session.add(Question(text=text))
            db.session.commit()
            flash("✅ Question added.", "success")
        return redirect(url_for("admin_questions"))

    questions = Question.query.order_by(Question.id.asc()).all()
    return render_template("admin/questions.html", questions=questions)


@app.route("/admin/questions/<int:qid>/delete", methods=["POST"])
def delete_question(qid):
    """Delete a question"""
    if not admin_required():
        return redirect(url_for("admin_login"))

    q = Question.query.get_or_404(qid)

    # Prevent deletion if already has submissions
    if Submission.query.filter_by(question_id=q.id).count() > 0:
        flash("Cannot delete question: submissions exist for it.", "danger")
        return redirect(url_for("admin_questions"))

    db.session.delete(q)
    db.session.commit()
    flash("✅ Question deleted.", "info")
    return redirect(url_for("admin_questions"))


@app.route("/admin/questions/<int:qid>/edit", methods=["POST"])
def edit_question(qid):
    """Edit a question"""
    if not admin_required():
        return redirect(url_for("admin_login"))

    q = Question.query.get_or_404(qid)
    new_text = request.form.get("text", "").strip()
    if new_text:
        q.text = new_text
        db.session.commit()
        flash("✅ Question updated.", "success")
    return redirect(url_for("admin_questions"))


# -------------------- ADMIN SUBMISSIONS --------------------
@app.route("/admin/submissions")
def admin_submissions():
    """View all candidate submissions"""
    if not admin_required():
        return redirect(url_for("admin_login"))

    submissions = Submission.query.order_by(Submission.created_at.desc()).all()
    return render_template("admin/submissions.html", submissions=submissions)


def _submissions_query_from_request_args():
    query = Submission.query.join(Candidate).join(Question)

    search = (request.args.get("q") or "").strip()
    if search:
        pattern = f"%{search}%"
        query = query.filter(
            or_(
                Candidate.name.ilike(pattern),
                Candidate.email.ilike(pattern),
                Question.text.ilike(pattern),
            )
        )

    feedback = (request.args.get("feedback") or "").strip().lower()
    if feedback == "yes":
        query = query.filter(Submission.feedback.isnot(None))
    elif feedback == "no":
        query = query.filter(Submission.feedback.is_(None))

    return query.order_by(Submission.created_at.desc())


@app.route("/admin/submissions/export.csv")
def admin_submissions_export():
    """Export submissions as CSV (supports the same filters as the submissions page)."""
    if not admin_required():
        return redirect(url_for("admin_login"))

    query = _submissions_query_from_request_args()
    rows = query.all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "submission_id",
        "candidate_name",
        "candidate_email",
        "question_id",
        "question_text",
        "audio_filename",
        "created_at",
        "transcript",
        "feedback",
    ])
    for sub in rows:
        writer.writerow([
            sub.id,
            sub.candidate.name,
            sub.candidate.email,
            sub.question_id,
            sub.question.text,
            sub.audio_filename,
            sub.created_at.isoformat() if sub.created_at else "",
            sub.transcript or "",
            sub.feedback or "",
        ])

    csv_data = output.getvalue()
    return Response(
        csv_data,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=submissions.csv"},
    )


@app.route("/admin/api/questions", methods=["GET", "POST"])
def admin_api_questions():
    if not admin_required_api():
        return jsonify({"error": "unauthorized"}), 401

    if request.method == "GET":
        questions = Question.query.order_by(Question.id.asc()).all()
        return jsonify({
            "items": [{"id": q.id, "text": q.text} for q in questions]
        })

    data = _json_body()
    text = (data.get("text") or request.form.get("text") or "").strip()
    if not text:
        return jsonify({"error": "Question text is required"}), 400

    q = Question(text=text)
    db.session.add(q)
    db.session.commit()
    return jsonify({"id": q.id, "text": q.text}), 201


@app.route("/admin/api/questions/<int:qid>", methods=["PUT", "DELETE"])
def admin_api_question_detail(qid):
    if not admin_required_api():
        return jsonify({"error": "unauthorized"}), 401

    q = Question.query.get_or_404(qid)

    if request.method == "DELETE":
        if Submission.query.filter_by(question_id=q.id).count() > 0:
            return jsonify({"error": "Cannot delete: submissions exist for this question"}), 409
        db.session.delete(q)
        db.session.commit()
        return jsonify({"ok": True})

    data = _json_body()
    text = (data.get("text") or "").strip()
    if not text:
        return jsonify({"error": "Question text is required"}), 400

    q.text = text
    db.session.commit()
    return jsonify({"id": q.id, "text": q.text})


@app.route("/admin/api/submissions", methods=["GET"])
def admin_api_submissions():
    if not admin_required_api():
        return jsonify({"error": "unauthorized"}), 401

    query = _submissions_query_from_request_args()
    limit = min(int(request.args.get("limit") or 200), 500)
    rows = query.limit(limit).all()

    items = []
    for sub in rows:
        items.append({
            "id": sub.id,
            "candidate_name": sub.candidate.name,
            "candidate_email": sub.candidate.email,
            "question_id": sub.question_id,
            "question_text": sub.question.text,
            "audio_url": url_for("uploaded_file", filename=sub.audio_filename),
            "has_feedback": bool(sub.feedback),
            "created_at": sub.created_at.isoformat() if sub.created_at else None,
        })

    return jsonify({"items": items})


@app.route("/admin/api/submissions/<int:sid>", methods=["PUT"])
def admin_api_submission_update(sid):
    if not admin_required_api():
        return jsonify({"error": "unauthorized"}), 401

    sub = Submission.query.get_or_404(sid)
    data = _json_body()

    transcript = (data.get("transcript") or "").strip()
    feedback = (data.get("feedback") or "").strip()

    sub.transcript = transcript if transcript else None
    sub.feedback = feedback if feedback else None
    db.session.commit()

    return jsonify({
        "ok": True,
        "id": sub.id,
        "transcript": sub.transcript,
        "feedback": sub.feedback,
    })


@app.route("/admin/submissions/<int:sid>", methods=["GET", "POST"])
def submission_detail(sid):
    """View and give feedback on a submission"""
    if not admin_required():
        return redirect(url_for("admin_login"))

    sub = Submission.query.get_or_404(sid)

    if request.method == "POST":
        transcript = request.form.get("transcript", "").strip()
        feedback = request.form.get("feedback", "").strip()
        sub.transcript = transcript if transcript else None
        sub.feedback = feedback if feedback else None
        db.session.commit()
        flash("✅ Feedback saved.", "success")
        return redirect(url_for("submission_detail", sid=sid))

    return render_template("admin/submission_detail.html", sub=sub)


@app.route("/admin/submissions/<int:sid>/delete", methods=["POST"])
def delete_submission(sid):
    """Delete a submission"""
    if not admin_required():
        return redirect(url_for("admin_login"))

    sub = Submission.query.get_or_404(sid)
    
    # Delete audio file
    audio_path = os.path.join(app.config["UPLOAD_FOLDER"], sub.audio_filename)
    if os.path.exists(audio_path):
        os.remove(audio_path)
    
    db.session.delete(sub)
    db.session.commit()
    flash("✅ Submission deleted.", "info")
    return redirect(url_for("admin_submissions"))


# -------------------- ERROR HANDLERS --------------------
@app.errorhandler(404)
def page_not_found(e):
    return render_template("404.html"), 404


@app.errorhandler(500)
def server_error(e):
    return render_template("500.html"), 500


# -------------------- RUN --------------------
if __name__ == "__main__":
    app.run(debug=True)