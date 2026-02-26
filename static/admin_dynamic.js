(() => {
  function $(sel, root = document) {
    return root.querySelector(sel);
  }

  function $all(sel, root = document) {
    return Array.from(root.querySelectorAll(sel));
  }

  function ensureFlashWrap() {
    const container = $("main.container");
    if (!container) return null;

    let wrap = $(".flash-wrap", container);
    if (!wrap) {
      wrap = document.createElement("div");
      wrap.className = "flash-wrap";
      container.insertBefore(wrap, container.firstChild);
    }

    return wrap;
  }

  function flash(message, category = "info") {
    const wrap = ensureFlashWrap();
    if (!wrap) return;

    const el = document.createElement("div");
    el.className = `flash flash-${category}`;
    el.textContent = message;
    wrap.insertBefore(el, wrap.firstChild);

    window.setTimeout(() => {
      el.style.opacity = "0";
      el.style.transform = "translateX(-10px)";
      window.setTimeout(() => el.remove(), 250);
    }, 3500);
  }

  async function apiFetch(url, options = {}) {
    const res = await fetch(url, {
      headers: {
        "Content-Type": "application/json",
        ...(options.headers || {}),
      },
      ...options,
    });

    const contentType = res.headers.get("content-type") || "";
    const isJson = contentType.includes("application/json");
    const data = isJson ? await res.json().catch(() => null) : null;

    if (!res.ok) {
      const msg = data?.error || `Request failed (${res.status})`;
      const err = new Error(msg);
      err.status = res.status;
      err.data = data;
      throw err;
    }

    return data;
  }

  function initQuestionsPage(root) {
    const addForm = $("#addQuestionForm", root);
    const list = $("#questionsList", root);

    if (addForm && list) {
      addForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const input = $("input[name='text']", addForm);
        const text = (input?.value || "").trim();
        if (!text) {
          flash("Question text is required.", "danger");
          return;
        }

        try {
          const created = await apiFetch("/admin/api/questions", {
            method: "POST",
            body: JSON.stringify({ text }),
          });

          const item = document.createElement("div");
          item.className = "question-item";
          item.dataset.qid = String(created.id);
          item.innerHTML = `
            <form method="POST" action="/admin/questions/${created.id}/edit" class="edit-form" data-qid="${created.id}">
              <input type="text" name="text" value="${escapeHtml(created.text)}" required />
              <button class="btn btn-sm btn-primary" type="submit">✏️ Update</button>
            </form>
            <form method="POST" action="/admin/questions/${created.id}/delete" class="delete-form">
              <button class="btn btn-sm btn-danger" type="submit" data-qid="${created.id}">🗑️ Delete</button>
            </form>
          `;

          list.appendChild(item);
          input.value = "";
          flash("Question added.", "success");
        } catch (err) {
          flash(err.message || "Failed to add question.", "danger");
        }
      });
    }

    // Inline update
    $all("form.edit-form", root).forEach((form) => {
      form.addEventListener("submit", async (e) => {
        e.preventDefault();
        const qid = form.dataset.qid;
        const input = $("input[name='text']", form);
        const text = (input?.value || "").trim();
        if (!qid) return;

        try {
          await apiFetch(`/admin/api/questions/${qid}`, {
            method: "PUT",
            body: JSON.stringify({ text }),
          });
          flash("Question updated.", "success");
        } catch (err) {
          flash(err.message || "Failed to update question.", "danger");
        }
      });
    });

    // Inline delete
    $all("form.delete-form", root).forEach((form) => {
      form.addEventListener("submit", async (e) => {
        e.preventDefault();
        const btn = $("button[data-qid]", form);
        const qid = btn?.dataset.qid;
        if (!qid) {
          form.submit();
          return;
        }

        if (!window.confirm("Delete this question?")) return;

        try {
          await apiFetch(`/admin/api/questions/${qid}`, { method: "DELETE" });
          const item = root.querySelector(`.question-item[data-qid='${CSS.escape(qid)}']`);
          if (item) item.remove();
          flash("Question deleted.", "info");
        } catch (err) {
          flash(err.message || "Failed to delete question.", "danger");
        }
      });
    });
  }

  function escapeHtml(str) {
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/\"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  function initSubmissionsPage(root) {
    const search = $("#subSearch", root);
    const feedback = $("#subFeedback", root);
    const tbody = $("#submissionsTbody", root);
    const exportBtn = $("#exportCsvBtn", root);

    if (!search || !feedback || !tbody) return;

    let debounceId = null;

    function buildParams() {
      const params = new URLSearchParams();
      const q = (search.value || "").trim();
      const fb = (feedback.value || "").trim();
      if (q) params.set("q", q);
      if (fb) params.set("feedback", fb);
      params.set("limit", "200");
      return params;
    }

    function updateExportHref() {
      if (!exportBtn) return;
      const params = new URLSearchParams();
      const q = (search.value || "").trim();
      const fb = (feedback.value || "").trim();
      if (q) params.set("q", q);
      if (fb) params.set("feedback", fb);
      exportBtn.href = `/admin/submissions/export.csv${params.toString() ? `?${params}` : ""}`;
    }

    async function refresh() {
      updateExportHref();
      const params = buildParams();
      const url = `/admin/api/submissions?${params.toString()}`;

      try {
        const data = await apiFetch(url);
        const items = data?.items || [];

        tbody.innerHTML = items
          .map((s) => {
            const qText = s.question_text || "";
            const qShort = qText.length > 30 ? `${qText.slice(0, 30)}...` : qText;
            const badge = s.has_feedback
              ? '<span class="badge badge-success">✅ Yes</span>'
              : '<span class="badge badge-warning">⏳ No</span>';

            const date = s.created_at ? new Date(s.created_at).toISOString().slice(0, 10) : "";

            return `
              <tr>
                <td><strong>${escapeHtml(s.candidate_name || "")}</strong></td>
                <td class="muted">${escapeHtml(s.candidate_email || "")}</td>
                <td>${escapeHtml(qShort)}</td>
                <td><audio controls src="${escapeHtml(s.audio_url || "")}" style="max-width: 150px;"></audio></td>
                <td>${badge}</td>
                <td class="muted">${escapeHtml(date)}</td>
                <td><a class="btn btn-sm btn-primary" href="/admin/submissions/${s.id}">Review</a></td>
              </tr>
            `;
          })
          .join("");
      } catch (err) {
        flash(err.message || "Failed to load submissions.", "danger");
      }
    }

    function onChange() {
      if (debounceId) window.clearTimeout(debounceId);
      debounceId = window.setTimeout(refresh, 250);
    }

    search.addEventListener("input", onChange);
    feedback.addEventListener("change", onChange);

    // First paint updates export URL too
    updateExportHref();
  }

  function initSubmissionDetailPage(root) {
    const page = $("[data-page='submission-detail']", root);
    if (!page) return;

    const sid = page.dataset.submissionId;
    const form = $("#submissionNotesForm", root);
    if (!sid || !form) return;

    form.addEventListener("submit", async (e) => {
      e.preventDefault();

      const transcript = ($("textarea[name='transcript']", form)?.value || "").trim();
      const feedback = ($("textarea[name='feedback']", form)?.value || "").trim();

      try {
        await apiFetch(`/admin/api/submissions/${sid}`, {
          method: "PUT",
          body: JSON.stringify({ transcript, feedback }),
        });
        flash("Saved.", "success");
      } catch (err) {
        flash(err.message || "Failed to save.", "danger");
      }
    });
  }

  document.addEventListener("DOMContentLoaded", () => {
    const root = document;
    const questionsPage = $("[data-page='questions']", root);
    if (questionsPage) initQuestionsPage(root);

    const submissionsPage = $("[data-page='submissions']", root);
    if (submissionsPage) initSubmissionsPage(root);

    initSubmissionDetailPage(root);
  });
})();
