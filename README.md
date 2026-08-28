# Placementor AI

A placement and interview preparation assistant for campus recruitment. Single Flask
application: landing page, auth, a chatbot that checks a curated MongoDB knowledge
base first and falls back to Ollama Cloud, and an admin dashboard with real usage
analytics.

## How the chatbot works

1. A student sends a question.
2. Flask normalizes it and searches the `qa_data` MongoDB collection for a match.
3. **Match found** -> that answer is returned instantly (source: `mongodb`).
4. **No match** -> Ollama Cloud generates an answer, which streams back to the
   browser and is saved into `qa_data` so the same question is answered instantly
   next time (source: `ollama`).
5. Every exchange is logged to `chat_history` with its source, timestamp, and
   response time, which powers the admin analytics.
6. Each student's own past questions also appear in a sidebar on the chat page
   (`GET /chat/history`, their own questions only) with a "New chat" button to
   start fresh - clicking a past question just re-displays it instantly from
   what's already stored, it doesn't call Ollama again.

## Project structure

```
chatbot/
├── app.py                  # All routes: pages, auth, chat API, admin analytics API
├── db.py                   # MongoDB connection (reads MONGO_URI)
├── ollama_client.py        # Ollama Cloud client (reads OLLAMA_API_KEY)
├── requirements.txt
├── Procfile                 # gunicorn start command, for Render
├── .python-version          # Python version pin, for Render
├── .env.example              # Template - copy to .env
├── .env                     # Your real secrets (git-ignored)
├── dataset/questions.json    # Present in the original project; empty/unused
├── scripts/
│   ├── upload_pdf.py          # Seeds the `questions` collection from the PDF
│   ├── test_connection.py     # Verifies MONGO_URI works, prints collection counts
│   └── Interview_QA_50 (1).pdf
├── static/
│   ├── css/                  # base.css (shared tokens) + one file per page
│   └── js/                   # theme.js (shared) + one file per page
└── templates/
    ├── base.html             # Shared <head>/layout
    ├── landing.html, login.html, register.html, admin_login.html
    ├── chat.html, admin_dashboard.html
    └── error.html
```

## Environment variables

| Variable          | Required | Description                                              |
|--------------------|:--------:|------------------------------------------------------------|
| `MONGO_URI`        | Yes      | MongoDB connection string (local or Atlas)                |
| `OLLAMA_API_KEY`   | Yes      | API key from https://ollama.com/settings/keys              |
| `OLLAMA_MODEL`     | No       | Defaults to `gpt-oss:20b`                                  |
| `OLLAMA_BASE_URL`  | No       | Defaults to `https://ollama.com`                            |
| `SECRET_KEY`       | Yes      | Signs login session cookies - a random one is pre-filled in `.env` |
| `PORT`             | No       | Local dev only; Render sets this automatically              |

## Run locally

```bash
python -m venv venv
# Windows: venv\Scripts\activate      macOS/Linux: source venv/bin/activate
venv/bin/pip install -r requirements.txt

# Edit .env and fill in MONGO_URI and OLLAMA_API_KEY

python app.py
```

Visit `http://localhost:5000`.

To confirm your database connection independently:

```bash
python scripts/test_connection.py
```

## Deploy to Render

1. Push this project to a GitHub repository (`.env` will not be included, thanks
   to `.gitignore` - that's intentional).
2. On Render: **New +** -> **Web Service** -> connect the repository.
3. Settings:
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `gunicorn app:app`
4. Add environment variables in the Render dashboard: `MONGO_URI`,
   `OLLAMA_API_KEY`, `SECRET_KEY` (and optionally `OLLAMA_MODEL`).
5. Deploy. Render will build and start the app with gunicorn automatically. The
   Python version comes from `.python-version` (3.12.3).

If your MongoDB is local-only (not Atlas or another externally reachable
instance), Render's servers won't be able to reach it - use MongoDB Atlas's free
tier for a deployed app.

## Notes on existing data

- The `qa_data` collection (what the chatbot actually searches) is untouched -
  nothing was deleted or migrated.
- `scripts/upload_pdf.py` still writes to the separate `questions` collection,
  exactly as it did before - that's a pre-existing split in the original project,
  not something introduced here. See the comment at the top of that file.
- Existing plaintext passwords in `users` / `admins` still work - each one is
  transparently upgraded to a secure hash the next time that account logs in.
