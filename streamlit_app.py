import os
import uuid
from contextlib import contextmanager
from datetime import datetime

import streamlit as st
from werkzeug.security import check_password_hash
from werkzeug.utils import secure_filename


def _sync_streamlit_secrets_to_env() -> None:
    """Make Streamlit Cloud secrets usable by code that expects os.environ.

    Streamlit's `st.secrets` is not automatically mirrored into environment
    variables. The existing Flask app reads config from `os.environ`, so we copy
    a small allow-list here before importing it.
    """

    for key in ("SECRET_KEY", "ADMIN_USERNAME", "ADMIN_PASSWORD", "DATABASE_URL"):
        try:
            if key not in os.environ and key in st.secrets:
                os.environ[key] = str(st.secrets[key])
        except Exception:
            # If secrets aren't configured (local dev), just do nothing.
            pass


_sync_streamlit_secrets_to_env()

import app as flask_app_module


@contextmanager
def flask_context():
    """Provide a Flask app context for DB operations."""
    with flask_app_module.app.app_context():
        yield


def allowed_audio(filename: str) -> bool:
    allowed = {"webm", "wav", "mp3", "ogg", "m4a", "flac"}
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return ext in allowed


def ensure_uploads_dir() -> str:
    base_dir = os.path.abspath(os.path.dirname(__file__))
    uploads_dir = os.path.join(base_dir, "uploads")
    os.makedirs(uploads_dir, exist_ok=True)
    return uploads_dir


def save_audio_bytes(original_name: str, audio_bytes: bytes, question_id: int) -> str:
    uploads_dir = ensure_uploads_dir()

    safe_name = secure_filename(original_name) if original_name else "audio.webm"
    if not allowed_audio(safe_name):
        raise ValueError("Unsupported audio format")

    ext = safe_name.rsplit(".", 1)[-1].lower()
    unique_name = f"{uuid.uuid4().hex}_q{question_id}.{ext}"
    out_path = os.path.join(uploads_dir, unique_name)

    with open(out_path, "wb") as f:
        f.write(audio_bytes)

    return unique_name


def page_candidate():
    st.header("Candidate Interview")

    with flask_context():
        questions = flask_app_module.Question.query.order_by(flask_app_module.Question.id.asc()).all()

    if not questions:
        st.warning("No questions are set yet.")
        return

    st.write("Fill your details and record or upload an audio answer for each question.")

    use_audio_input = hasattr(st, "audio_input")
    if not use_audio_input:
        st.info(
            "Your Streamlit version doesn’t support in-browser recording here. "
            "Please upload audio files (webm/wav/mp3/ogg/m4a/flac)."
        )

    with st.form("candidate_form", clear_on_submit=False):
        name = st.text_input("Name")
        email = st.text_input("Email")

        responses: dict[int, dict[str, object]] = {}

        for q in questions:
            st.subheader(f"Q{q.id}. {q.text}")

            if use_audio_input:
                audio_data = st.audio_input(
                    "Record answer",
                    key=f"audio_input_{q.id}",
                )
                if audio_data is not None:
                    audio_bytes = audio_data.getvalue()
                    st.audio(audio_bytes)
                    responses[q.id] = {
                        "name": f"recording_q{q.id}.wav",
                        "bytes": audio_bytes,
                    }
                else:
                    responses[q.id] = {"name": None, "bytes": None}
            else:
                uploaded = st.file_uploader(
                    "Upload audio",
                    type=["webm", "wav", "mp3", "ogg", "m4a", "flac"],
                    key=f"audio_upload_{q.id}",
                )
                if uploaded is not None:
                    audio_bytes = uploaded.getvalue()
                    st.audio(audio_bytes)
                    responses[q.id] = {"name": uploaded.name, "bytes": audio_bytes}
                else:
                    responses[q.id] = {"name": None, "bytes": None}

        submitted = st.form_submit_button("Submit Interview")

    if not submitted:
        return

    name = (name or "").strip()
    email = (email or "").strip()

    if not name or not email:
        st.error("Name and Email are required.")
        return

    with flask_context():
        existing = flask_app_module.Candidate.query.filter_by(email=email).first()
        if existing:
            st.warning("This email has already submitted an interview.")
            return

        candidate = flask_app_module.Candidate(name=name, email=email)
        flask_app_module.db.session.add(candidate)
        flask_app_module.db.session.commit()

        saved_count = 0
        try:
            for q in questions:
                resp = responses.get(q.id) or {}
                audio_name = resp.get("name")
                audio_bytes = resp.get("bytes")

                if not audio_name or not audio_bytes:
                    continue

                audio_filename = save_audio_bytes(str(audio_name), bytes(audio_bytes), q.id)

                submission = flask_app_module.Submission(
                    candidate_id=candidate.id,
                    question_id=q.id,
                    audio_filename=audio_filename,
                    created_at=datetime.utcnow(),
                )
                flask_app_module.db.session.add(submission)
                saved_count += 1

            flask_app_module.db.session.commit()
        except Exception:
            flask_app_module.db.session.rollback()
            flask_app_module.Candidate.query.filter_by(id=candidate.id).delete()
            flask_app_module.db.session.commit()
            raise

    if saved_count == 0:
        st.warning("No audio was submitted. Please provide at least one answer.")
        return

    st.success(f"Interview submitted successfully! {saved_count} answers recorded.")


def admin_is_logged_in() -> bool:
    return bool(st.session_state.get("admin_id"))


def page_admin_login():
    st.header("Admin Login")

    with st.form("admin_login_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Login")

    if not submitted:
        return

    username = (username or "").strip()
    password = (password or "").strip()

    with flask_context():
        admin = flask_app_module.Admin.query.filter_by(username=username).first()

    if not admin or not check_password_hash(admin.password_hash, password):
        st.error("Invalid admin credentials.")
        return

    st.session_state["admin_id"] = admin.id
    st.success("Logged in.")


def page_admin_dashboard():
    st.header("Admin")

    col1, col2 = st.columns([1, 4])
    with col1:
        if st.button("Logout"):
            st.session_state.pop("admin_id", None)
            st.rerun()

    with flask_context():
        total_candidates = flask_app_module.Candidate.query.count()
        total_questions = flask_app_module.Question.query.count()
        total_submissions = flask_app_module.Submission.query.count()

        latest_submissions = (
            flask_app_module.Submission.query.order_by(flask_app_module.Submission.created_at.desc())
            .limit(20)
            .all()
        )

    st.subheader("Stats")
    c1, c2, c3 = st.columns(3)
    c1.metric("Candidates", total_candidates)
    c2.metric("Questions", total_questions)
    c3.metric("Submissions", total_submissions)

    st.subheader("Latest Submissions")
    for sub in latest_submissions:
        with st.expander(
            f"{sub.candidate.name} — Q{sub.question_id} — {sub.created_at.strftime('%Y-%m-%d %H:%M')}"
        ):
            st.write(f"Email: {sub.candidate.email}")
            st.write(f"Question: {sub.question.text}")

            audio_path = os.path.join(ensure_uploads_dir(), sub.audio_filename)
            if os.path.exists(audio_path):
                with open(audio_path, "rb") as f:
                    st.audio(f.read())
            else:
                st.warning("Audio file not found on server.")

            feedback = st.text_area("Feedback", value=sub.feedback or "", key=f"fb_{sub.id}")
            col_save, col_del = st.columns(2)

            with col_save:
                if st.button("Save Feedback", key=f"save_{sub.id}"):
                    with flask_context():
                        s = flask_app_module.Submission.query.get(sub.id)
                        s.feedback = (feedback or "").strip() or None
                        flask_app_module.db.session.commit()
                    st.success("Feedback saved.")

            with col_del:
                if st.button("Delete Submission", key=f"del_{sub.id}"):
                    with flask_context():
                        s = flask_app_module.Submission.query.get(sub.id)
                        if s:
                            audio_path2 = os.path.join(ensure_uploads_dir(), s.audio_filename)
                            if os.path.exists(audio_path2):
                                os.remove(audio_path2)
                            flask_app_module.db.session.delete(s)
                            flask_app_module.db.session.commit()
                    st.info("Submission deleted.")
                    st.rerun()


def page_admin_questions():
    st.header("Manage Questions")

    col1, col2 = st.columns([1, 4])
    with col1:
        if st.button("Back"):
            st.session_state["admin_view"] = "Dashboard"
            st.rerun()

    with st.form("add_question_form"):
        new_text = st.text_area("New question")
        add = st.form_submit_button("Add Question")

    if add:
        new_text = (new_text or "").strip()
        if not new_text:
            st.error("Question text is required.")
        else:
            with flask_context():
                flask_app_module.db.session.add(flask_app_module.Question(text=new_text))
                flask_app_module.db.session.commit()
            st.success("Question added.")
            st.rerun()

    with flask_context():
        questions = flask_app_module.Question.query.order_by(flask_app_module.Question.id.asc()).all()

    if not questions:
        st.info("No questions yet.")
        return

    for q in questions:
        with st.expander(f"Q{q.id}"):
            updated_text = st.text_area("Text", value=q.text, key=f"qtext_{q.id}")
            col_save, col_del = st.columns(2)

            with col_save:
                if st.button("Save", key=f"qsave_{q.id}"):
                    updated_text = (updated_text or "").strip()
                    if not updated_text:
                        st.error("Question text can’t be empty.")
                    else:
                        with flask_context():
                            qq = flask_app_module.Question.query.get(q.id)
                            qq.text = updated_text
                            flask_app_module.db.session.commit()
                        st.success("Question updated.")
                        st.rerun()

            with col_del:
                if st.button("Delete", key=f"qdel_{q.id}"):
                    with flask_context():
                        has_submissions = (
                            flask_app_module.Submission.query.filter_by(question_id=q.id).count() > 0
                        )
                        if has_submissions:
                            st.error("Cannot delete: submissions exist for this question.")
                        else:
                            qq = flask_app_module.Question.query.get(q.id)
                            flask_app_module.db.session.delete(qq)
                            flask_app_module.db.session.commit()
                            st.info("Question deleted.")
                            st.rerun()


def main():
    st.set_page_config(page_title="Voice Interview App", layout="wide")

    st.title("Voice Interview App")

    mode = st.sidebar.radio("Mode", ["Candidate", "Admin"], index=0)

    if mode == "Candidate":
        page_candidate()
        return

    if not admin_is_logged_in():
        page_admin_login()
        return

    admin_view = st.sidebar.radio("Admin", ["Dashboard", "Questions"], index=0)

    if admin_view == "Dashboard":
        page_admin_dashboard()
    else:
        page_admin_questions()


if __name__ == "__main__":
    main()
