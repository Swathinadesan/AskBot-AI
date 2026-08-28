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

sh the next time that account logs in.
