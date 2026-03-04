import os
import time
import uuid
from contextlib import contextmanager
from datetime import datetime

import streamlit as st
from werkzeug.security import check_password_hash
from werkzeug.utils import secure_filename
import importlib


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


def _import_flask_app_module():
    """Import the Flask app module.

    Historically this project used `app.py`, but this workspace currently ships
    the Flask app in `main.py`. Streamlit Cloud will crash at import time if we
    hardcode the wrong module name, so we try both.
    """

    def is_full_flask_module(module) -> bool:
        """Return True if this module exports app + DB models used by Streamlit.

        Streamlit uses the Flask app's SQLAlchemy models directly (e.g.
        `Question.query`). Some deployments include an `app.py` shim that only
        re-exports the Flask `app` object; importing that shim would succeed but
        the models wouldn't exist, causing AttributeError at runtime.
        """

        required_attrs = ("app", "db", "Question", "Candidate", "Submission", "Admin")
        return all(hasattr(module, attr) for attr in required_attrs)

    # Prefer `main` because this repo's `app.py` is a WSGI shim.
    for module_name in ("main", "app"):
        try:
            module = importlib.import_module(module_name)
        except ModuleNotFoundError as exc:
            # Only swallow the error if *this* module doesn't exist.
            # If an inner import fails (e.g. missing dependency), re-raise.
            if getattr(exc, "name", None) == module_name:
                continue
            raise

        if is_full_flask_module(module):
            return module

    raise ModuleNotFoundError(
        "Unable to import the Flask app module. Expected either `app.py` "
        "(import name: 'app') or `main.py` (import name: 'main') at repo root."
    )


flask_app_module = _import_flask_app_module()


def inject_streamlit_css() -> None:
        st.markdown(
                """
                <style>
                    /* Keep this minimal: just spacing + chat feel */
                    .block-container { padding-top: 1.25rem; }
                    [data-testid="stSidebar"] { border-right: 1px solid rgba(48,54,61,0.85); }
                    .nxt-card {
                        background: rgba(22, 27, 34, 0.75);
                        border: 1px solid rgba(48,54,61,0.85);
                        border-radius: 14px;
                        padding: 16px 18px;
                    }
                    .nxt-muted { color: rgba(139,148,158,1); }
                    .nxt-pill {
                        display: inline-block;
                        padding: 4px 10px;
                        border-radius: 999px;
                        border: 1px solid rgba(48,54,61,0.85);
                        background: rgba(13,17,23,0.35);
                        font-size: 12px;
                    }
                </style>
                """,
                unsafe_allow_html=True,
        )


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


def _question_time_limit_seconds(question) -> int | None:
    """Return time limit in seconds, or None if unlimited/unknown."""

    mins = getattr(question, "duration_minutes", None)
    try:
        mins_int = int(mins) if mins is not None else 0
    except Exception:
        mins_int = 0
    if mins_int <= 0:
        return None
    return mins_int * 60


def _format_mmss(seconds: int) -> str:
    seconds = max(int(seconds), 0)
    mm, ss = divmod(seconds, 60)
    return f"{mm:02d}:{ss:02d}"


def page_candidate():
    st.markdown("<div class='nxt-card'>", unsafe_allow_html=True)
    st.header("Candidate Interview")
    st.caption("Chat-style interview: answer each prompt with an audio response.")
    st.markdown("</div>", unsafe_allow_html=True)

    with flask_context():
        if hasattr(flask_app_module.Question, "query"):
            questions = (
                flask_app_module.Question.query.order_by(flask_app_module.Question.id.asc()).all()
            )
        else:
            questions = (
                flask_app_module.db.session.query(flask_app_module.Question)
                .order_by(flask_app_module.Question.id.asc())
                .all()
            )

    if not questions:
        st.warning("No questions are set yet.")
        return

    if st.sidebar.button("Reset interview"):
        for key in list(st.session_state.keys()):
            if key.startswith("cand_"):
                st.session_state.pop(key, None)
        st.rerun()

    use_audio_input = hasattr(st, "audio_input")

    # Step 1: identity
    st.session_state.setdefault("cand_started", False)
    st.session_state.setdefault("cand_name", "")
    st.session_state.setdefault("cand_email", "")
    st.session_state.setdefault("cand_index", 0)
    st.session_state.setdefault("cand_answers", {})

    if not st.session_state["cand_started"]:
        with st.container():
            st.subheader("Your details")
            c1, c2 = st.columns(2)
            with c1:
                st.session_state["cand_name"] = st.text_input("Name", value=st.session_state["cand_name"])
            with c2:
                st.session_state["cand_email"] = st.text_input("Email", value=st.session_state["cand_email"])

            if st.button("Start interview"):
                name = (st.session_state["cand_name"] or "").strip()
                email = (st.session_state["cand_email"] or "").strip()
                if not name or not email:
                    st.error("Name and Email are required.")
                else:
                    with flask_context():
                        existing = flask_app_module.Candidate.query.filter_by(email=email).first()
                    if existing:
                        st.warning("This email has already submitted an interview.")
                    else:
                        st.session_state["cand_started"] = True
                        st.rerun()
        return

    # Step 2: chat flow
    name = (st.session_state["cand_name"] or "").strip()
    email = (st.session_state["cand_email"] or "").strip()
    index = int(st.session_state.get("cand_index") or 0)
    answers: dict[int, dict[str, object]] = dict(st.session_state.get("cand_answers") or {})

    total = len(questions)
    st.progress(min(index / max(total, 1), 1.0))
    st.caption(f"Progress: {min(index, total)} / {total}")

    for i, q in enumerate(questions):
        if i > index:
            break

        with st.chat_message("assistant"):
            st.markdown(f"**Q{i + 1}.** {q.text}")

        if i < index:
            resp = answers.get(q.id) or {}
            with st.chat_message("user"):
                st.markdown("**Audio answer**")
                audio_bytes = resp.get("bytes")
                if audio_bytes:
                    st.audio(bytes(audio_bytes))
                else:
                    st.caption("(No audio)")
            continue

        # Current question input
        limit_seconds = _question_time_limit_seconds(q)
        remaining_seconds: int | None = None
        if limit_seconds is not None:
            start_key = f"cand_q_start_{q.id}"
            if start_key not in st.session_state:
                st.session_state[start_key] = time.time()
            try:
                started_at = float(st.session_state[start_key])
            except Exception:
                started_at = time.time()
                st.session_state[start_key] = started_at

            elapsed = max(0.0, time.time() - started_at)
            remaining_seconds = max(0, int(limit_seconds - elapsed))

            st.caption(
                f"Time limit: {int(limit_seconds / 60)} min • Remaining: {_format_mmss(remaining_seconds)}"
            )

            if remaining_seconds <= 0:
                st.error("Time is up for this question.")
                if st.button("Next question", key=f"cand_next_{q.id}"):
                    st.session_state["cand_index"] = index + 1
                    st.rerun()
                return

        with st.chat_message("user"):
            st.markdown("**Record or upload your answer**")

            if use_audio_input:
                audio_data = st.audio_input("Record", key=f"cand_record_{q.id}")
                audio_name = f"recording_q{q.id}.wav"
                audio_bytes = audio_data.getvalue() if audio_data is not None else None
            else:
                st.info(
                    "Your Streamlit version doesn’t support in-browser recording here. "
                    "Please upload audio files (webm/wav/mp3/ogg/m4a/flac)."
                )
                uploaded = st.file_uploader(
                    "Upload",
                    type=["webm", "wav", "mp3", "ogg", "m4a", "flac"],
                    key=f"cand_upload_{q.id}",
                )
                audio_name = uploaded.name if uploaded is not None else None
                audio_bytes = uploaded.getvalue() if uploaded is not None else None

            if audio_bytes:
                st.audio(audio_bytes)

            if st.button("Send answer", key=f"cand_send_{q.id}"):
                if limit_seconds is not None and (remaining_seconds is None or remaining_seconds <= 0):
                    st.error("Time is up. Please click Next question.")
                    return
                if not audio_bytes or not audio_name:
                    st.error("Please record or upload audio before sending.")
                else:
                    answers[q.id] = {"name": str(audio_name), "bytes": bytes(audio_bytes)}
                    st.session_state["cand_answers"] = answers
                    st.session_state["cand_index"] = index + 1
                    st.rerun()

    if index < total:
        return

    st.divider()
    st.subheader("Submit")
    st.caption("We’ll save your answers and lock this email from re-submitting.")

    if st.button("Submit interview", type="primary"):
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
                    resp = answers.get(q.id) or {}
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
    st.markdown("<div class='nxt-card'>", unsafe_allow_html=True)
    st.header("Admin Login")
    st.caption("Sign in to manage questions and review submissions.")
    st.markdown("</div>", unsafe_allow_html=True)

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
    st.header("Admin Dashboard")

    if st.sidebar.button("Logout"):
        st.session_state.pop("admin_id", None)
        st.rerun()

    with flask_context():
        total_candidates = flask_app_module.Candidate.query.count()
        total_questions = flask_app_module.Question.query.count()
        total_submissions = flask_app_module.Submission.query.count()

        now = datetime.utcnow()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        candidates_today = flask_app_module.Candidate.query.filter(
            flask_app_module.Candidate.created_at >= today_start
        ).count()
        submissions_today = flask_app_module.Submission.query.filter(
            flask_app_module.Submission.created_at >= today_start
        ).count()
        feedback_done = flask_app_module.Submission.query.filter(
            flask_app_module.Submission.feedback.isnot(None)
        ).count()
        feedback_pending = max(total_submissions - feedback_done, 0)

    st.subheader("KPIs")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Candidates", total_candidates, delta=str(candidates_today))
    c2.metric("Questions", total_questions)
    c3.metric("Submissions", total_submissions, delta=str(submissions_today))
    c4.metric("Feedback pending", feedback_pending)

    st.caption("Use the Submissions tab to review and add notes.")


def page_admin_questions():
    st.header("Manage Questions")

    col1, col2 = st.columns([1, 4])
    with col1:
        if st.button("Back"):
            st.session_state["admin_view"] = "Dashboard"
            st.rerun()

    with st.form("add_question_form"):
        new_text = st.text_area("New question")
        duration_minutes = st.number_input(
            "Timer (minutes, 0 = no limit)",
            min_value=0,
            step=1,
            value=2,
        )
        add = st.form_submit_button("Add Question")

    if add:
        new_text = (new_text or "").strip()
        if not new_text:
            st.error("Question text is required.")
        else:
            with flask_context():
                dur = int(duration_minutes) if duration_minutes is not None else 0
                flask_app_module.db.session.add(
                    flask_app_module.Question(text=new_text, duration_minutes=dur)
                )
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
            current_dur = getattr(q, "duration_minutes", None)
            try:
                current_dur_int = int(current_dur) if current_dur is not None else 0
            except Exception:
                current_dur_int = 0
            updated_dur = st.number_input(
                "Timer (minutes, 0 = no limit)",
                min_value=0,
                step=1,
                value=max(current_dur_int, 0),
                key=f"qdur_{q.id}",
            )
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
                            qq.duration_minutes = int(updated_dur) if updated_dur is not None else 0
                            flask_app_module.db.session.commit()
                        st.success("Question updated.")
                        st.rerun()


def page_admin_submissions():
    st.header("Submissions")

    with flask_context():
        questions = flask_app_module.Question.query.order_by(flask_app_module.Question.id.asc()).all()

    col_filters, col_export = st.columns([4, 1])
    with col_filters:
        search = st.text_input("Search", placeholder="name, email, question…")
        feedback_filter = st.selectbox("Feedback", ["Any", "Yes", "No"], index=0)
    with col_export:
        st.write("")
        st.write("")

    with flask_context():
        q = flask_app_module.Submission.query.join(flask_app_module.Candidate).join(flask_app_module.Question)

        if search.strip():
            pattern = f"%{search.strip()}%"
            q = q.filter(
                (flask_app_module.Candidate.name.ilike(pattern))
                | (flask_app_module.Candidate.email.ilike(pattern))
                | (flask_app_module.Question.text.ilike(pattern))
            )

        if feedback_filter == "Yes":
            q = q.filter(flask_app_module.Submission.feedback.isnot(None))
        elif feedback_filter == "No":
            q = q.filter(flask_app_module.Submission.feedback.is_(None))

        submissions = q.order_by(flask_app_module.Submission.created_at.desc()).limit(200).all()

    # CSV export (in-memory)
    csv_rows = [
        [
            "submission_id",
            "candidate_name",
            "candidate_email",
            "question_id",
            "question_text",
            "audio_filename",
            "created_at",
            "transcript",
            "feedback",
        ]
    ]
    for s in submissions:
        csv_rows.append(
            [
                s.id,
                s.candidate.name,
                s.candidate.email,
                s.question_id,
                s.question.text,
                s.audio_filename,
                s.created_at.isoformat() if s.created_at else "",
                s.transcript or "",
                s.feedback or "",
            ]
        )
    csv_text = "\n".join([",".join([str(x).replace("\n", " ").replace(",", " ") for x in row]) for row in csv_rows])
    st.download_button("Export CSV", data=csv_text, file_name="submissions.csv", mime="text/csv")

    if not submissions:
        st.info("No submissions match your filters.")
        return

    # Select a submission to review
    options = {
        f"{s.id} — {s.candidate.name} — {s.created_at.strftime('%Y-%m-%d %H:%M')}": s.id for s in submissions
    }
    selected_label = st.selectbox("Select submission", list(options.keys()))
    sid = options[selected_label]

    with flask_context():
        sub = flask_app_module.Submission.query.get(sid)

    st.subheader("Review")
    st.write(f"**Candidate:** {sub.candidate.name} ({sub.candidate.email})")
    st.write(f"**Question:** {sub.question.text}")

    audio_path = os.path.join(ensure_uploads_dir(), sub.audio_filename)
    if os.path.exists(audio_path):
        with open(audio_path, "rb") as f:
            st.audio(f.read())
    else:
        st.warning("Audio file not found on server.")

    transcript = st.text_area("Transcript (optional)", value=sub.transcript or "", height=140)
    feedback = st.text_area("Feedback / Notes", value=sub.feedback or "", height=180)

    col_save, col_delete = st.columns(2)
    with col_save:
        if st.button("Save", type="primary"):
            with flask_context():
                s = flask_app_module.Submission.query.get(sub.id)
                s.transcript = (transcript or "").strip() or None
                s.feedback = (feedback or "").strip() or None
                flask_app_module.db.session.commit()
            st.success("Saved.")

    with col_delete:
        if st.button("Delete"):
            with flask_context():
                s = flask_app_module.Submission.query.get(sub.id)
                if s:
                    audio_path2 = os.path.join(ensure_uploads_dir(), s.audio_filename)
                    if os.path.exists(audio_path2):
                        os.remove(audio_path2)
                    flask_app_module.db.session.delete(s)
                    flask_app_module.db.session.commit()
            st.info("Deleted.")
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

    inject_streamlit_css()

    st.title("Voice Interview App")

    mode = st.sidebar.radio("Mode", ["Candidate", "Admin"], index=0)

    if mode == "Candidate":
        page_candidate()
        return

    if not admin_is_logged_in():
        page_admin_login()
        return

    admin_view = st.sidebar.radio("Admin", ["Dashboard", "Submissions", "Questions"], index=0)

    if admin_view == "Dashboard":
        page_admin_dashboard()
    elif admin_view == "Submissions":
        page_admin_submissions()
    else:
        page_admin_questions()


if __name__ == "__main__":
    main()
