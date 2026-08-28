"""
Placementor AI - main Flask application.

Flow:
1. User sends a question.
2. Normalize the question.
3. Search MongoDB qa_data collection.
4. If found -> return MongoDB answer.
5. If not found -> ask Ollama Cloud (including any uploaded
   document's text as context, if the user has one).
6. Save the Ollama answer into qa_data for future use.
7. Save every chat into chat_history.
8. User can upload a PDF document.
9. PDF text is extracted and saved into MongoDB documents collection.
"""

import os
import re
import time
from collections import Counter
from datetime import datetime, timedelta, timezone
from functools import wraps

from bson import ObjectId
from bson.errors import InvalidId
from dotenv import load_dotenv

from flask import (
    Flask,
    Response,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    stream_with_context,
    url_for,
)

from flask_cors import CORS

from werkzeug.security import (
    check_password_hash,
    generate_password_hash,
)

from werkzeug.utils import secure_filename
from pypdf import PdfReader

from db import (
    admins,
    chat_collection,
    qa_data,
    users,
    resumes,
    documents
)

from ollama_client import (
    OLLAMA_MODEL,
    OllamaError,
    is_configured,
    stream_ollama_response,
)


# =========================================================
# CONFIGURATION
# =========================================================

load_dotenv()

app = Flask(__name__)

app.secret_key = os.environ.get(
    "SECRET_KEY",
    "placementor-dev-secret-change-me"
)

app.config["JSON_SORT_KEYS"] = False

CORS(app)

HASH_PREFIXES = (
    "pbkdf2:",
    "scrypt:"
)

MAX_MESSAGE_LENGTH = 2000

_PUNCT_RE = re.compile(
    r"[?!.,;:'\"()\[\]{}]"
)

_WS_RE = re.compile(
    r"\s+"
)


# =========================================================
# PDF CONFIGURATION
# =========================================================

ALLOWED_RESUME_EXTENSIONS = {
    "pdf"
}

MAX_RESUME_SIZE = (
    10 * 1024 * 1024
)


ALLOWED_DOCUMENT_EXTENSIONS = {
    "pdf"
}

MAX_DOCUMENT_SIZE = (
    10 * 1024 * 1024
)

# How much of an uploaded document's text to feed into the
# Ollama prompt as context. Keeps prompts from getting huge.
MAX_DOCUMENT_CONTEXT_CHARS = 6000


# =========================================================
# HELPERS
# =========================================================

def normalize_question(text):
    """
    Lowercase, remove punctuation and extra spaces.

    Example:
        "What is Python?"
        ->
        "what is python"
    """

    text = (
        text or ""
    ).strip().lower()

    text = _PUNCT_RE.sub(
        "",
        text
    )

    text = _WS_RE.sub(
        " ",
        text
    )

    return text.strip()


def verify_password(
    stored_password,
    provided_password
):
    """
    Supports both:
    - Werkzeug hashed passwords
    - Legacy plaintext passwords
    """

    if not stored_password:
        return False

    if stored_password.startswith(
        HASH_PREFIXES
    ):

        try:

            return check_password_hash(
                stored_password,
                provided_password
            )

        except ValueError:

            return False

    return (
        stored_password
        == provided_password
    )


def upgrade_password_if_legacy(
    collection,
    doc,
    plain_password
):
    """
    Converts an old plaintext password
    into a secure hash.
    """

    if not str(
        doc.get(
            "password",
            ""
        )
    ).startswith(
        HASH_PREFIXES
    ):

        collection.update_one(
            {
                "_id": doc["_id"]
            },
            {
                "$set": {
                    "password":
                        generate_password_hash(
                            plain_password
                        )
                }
            },
        )


def get_request_payload():
    """
    Supports both JSON and normal HTML
    form requests.
    """

    if request.is_json:

        return (
            request.get_json(
                silent=True
            ) or {},
            True
        )

    return (
        request.form,
        False
    )


def respond(
    is_json,
    message,
    status,
    success=False,
    redirect_to=None
):
    """
    Common response helper.
    """

    if is_json:

        payload = {
            "success": success,
            "message": message,
        }

        if redirect_to:

            payload["redirect"] = (
                redirect_to
            )

        return (
            jsonify(payload),
            status
        )

    if success and redirect_to:

        return redirect(
            redirect_to
        )

    return (
        message,
        status
    )


def log_chat(
    user,
    question,
    answer,
    source,
    response_time
):
    """
    Save chat into MongoDB
    chat_history collection.
    """

    chat_collection.insert_one(
        {
            "user": user,
            "question": question,
            "answer": answer,
            "source": source,
            "timestamp":
                datetime.now(
                    timezone.utc
                ),
            "response_time":
                response_time,
        }
    )


def find_qa_match(
    clean_question
):
    """
    Search MongoDB qa_data collection.

    Current version performs
    normalized exact matching.
    """

    for item in qa_data.find({}):

        stored_question = (
            normalize_question(
                item.get(
                    "question",
                    ""
                )
            )
        )

        if (
            stored_question
            == clean_question
        ):

            return item

    return None


def get_latest_document_for_user(user_id):
    """
    Returns the most recently uploaded document
    (from the 'documents' collection) for this user,
    or None if they haven't uploaded one.
    """

    if not user_id:
        return None

    return documents.find_one(
        {"user_id": user_id},
        sort=[("uploaded_at", -1)]
    )


# =========================================================
# AUTH DECORATORS
# =========================================================

def user_page_required(f):

    @wraps(f)
    def wrapper(
        *args,
        **kwargs
    ):

        if "user_id" not in session:

            return redirect(
                url_for(
                    "login_page"
                )
            )

        return f(
            *args,
            **kwargs
        )

    return wrapper


def user_api_required(f):

    @wraps(f)
    def wrapper(
        *args,
        **kwargs
    ):

        if "user_id" not in session:

            return jsonify(
                {
                    "reply":
                        "Please log in to continue.",
                    "error":
                        "unauthorized",
                }
            ), 401

        return f(
            *args,
            **kwargs
        )

    return wrapper


def admin_page_required(f):

    @wraps(f)
    def wrapper(
        *args,
        **kwargs
    ):

        if "admin_id" not in session:

            return redirect(
                url_for(
                    "admin_page"
                )
            )

        return f(
            *args,
            **kwargs
        )

    return wrapper


def admin_api_required(f):

    @wraps(f)
    def wrapper(
        *args,
        **kwargs
    ):

        if "admin_id" not in session:

            return jsonify(
                {
                    "error":
                        "unauthorized"
                }
            ), 401

        return f(
            *args,
            **kwargs
        )

    return wrapper


# =========================================================
# LANDING PAGE
# =========================================================

@app.route("/")
def landing():

    try:

        kb_count = (
            qa_data.count_documents({})
        )

    except Exception:

        kb_count = 0

    return render_template(
        "landing.html",
        logged_in=
            "user_id" in session,
        username=
            session.get(
                "username",
                ""
            ),
        kb_count=kb_count,
    )


# =========================================================
# USER REGISTER
# =========================================================

@app.route(
    "/register",
    methods=["GET"]
)
def register_page():

    if "user_id" in session:

        return redirect(
            url_for(
                "chat_page"
            )
        )

    return render_template(
        "register.html"
    )


@app.route(
    "/register",
    methods=["POST"]
)
def register():

    data, is_json = (
        get_request_payload()
    )

    username = (
        data.get("username")
        or ""
    ).strip()

    email = (
        data.get("email")
        or ""
    ).strip()

    password = (
        data.get("password")
        or ""
    )

    if (
        not username
        or not email
        or not password
    ):

        return respond(
            is_json,
            "Username, email and password are all required.",
            400,
        )

    if len(password) < 6:

        return respond(
            is_json,
            "Password must be at least 6 characters long.",
            400,
        )

    if users.find_one(
        {
            "email": email
        }
    ):

        return respond(
            is_json,
            "Email already registered!",
            409,
        )

    result = users.insert_one(
        {
            "username": username,
            "email": email,
            "password":
                generate_password_hash(
                    password
                ),
            "created_at":
                datetime.now(
                    timezone.utc
                ),
        }
    )

    session["user_id"] = str(
        result.inserted_id
    )

    session["username"] = (
        username
    )

    session["email"] = (
        email
    )

    return respond(
        is_json,
        "Account created!",
        201,
        success=True,
        redirect_to=
            url_for(
                "chat_page"
            ),
    )


# =========================================================
# USER LOGIN
# =========================================================

@app.route(
    "/login",
    methods=["GET"]
)
def login_page():

    if "user_id" in session:

        return redirect(
            url_for(
                "chat_page"
            )
        )

    return render_template(
        "login.html"
    )


@app.route(
    "/login",
    methods=["POST"]
)
def login():

    data, is_json = (
        get_request_payload()
    )

    email = (
        data.get("email")
        or ""
    ).strip()

    password = (
        data.get("password")
        or ""
    )

    if (
        not email
        or not password
    ):

        return respond(
            is_json,
            "Email and password are required.",
            400,
        )

    user = users.find_one(
        {
            "email": email
        }
    )

    if (
        not user
        or not verify_password(
            user.get(
                "password",
                ""
            ),
            password
        )
    ):

        return respond(
            is_json,
            "Invalid Email or Password!",
            401,
        )

    upgrade_password_if_legacy(
        users,
        user,
        password,
    )

    session["user_id"] = str(
        user["_id"]
    )

    session["username"] = (
        user.get(
            "username",
            ""
        )
    )

    session["email"] = (
        user.get(
            "email",
            ""
        )
    )

    return respond(
        is_json,
        "Welcome back!",
        200,
        success=True,
        redirect_to=
            url_for(
                "chat_page"
            ),
    )


# =========================================================
# USER LOGOUT
# =========================================================

@app.route("/logout")
def logout():

    session.pop(
        "user_id",
        None
    )

    session.pop(
        "username",
        None
    )

    session.pop(
        "email",
        None
    )

    return redirect(
        url_for(
            "landing"
        )
    )


# =========================================================
# ADMIN LOGIN
# =========================================================

@app.route("/admin")
def admin_page():

    if "admin_id" in session:

        return redirect(
            url_for(
                "admin_dashboard"
            )
        )

    return render_template(
        "admin_login.html"
    )


@app.route(
    "/admin-login",
    methods=["POST"]
)
def admin_login():

    data, is_json = (
        get_request_payload()
    )

    username = (
        data.get("username")
        or ""
    ).strip()

    password = (
        data.get("password")
        or ""
    )

    if (
        not username
        or not password
    ):

        return respond(
            is_json,
            "Admin username and password are required.",
            400,
        )

    admin = admins.find_one(
        {
            "username": username
        }
    )

    if (
        not admin
        or not verify_password(
            admin.get(
                "password",
                ""
            ),
            password
        )
    ):

        return respond(
            is_json,
            "Invalid Admin Username or Password!",
            401,
        )

    upgrade_password_if_legacy(
        admins,
        admin,
        password,
    )

    session["admin_id"] = str(
        admin["_id"]
    )

    session["admin_username"] = (
        admin.get(
            "username",
            ""
        )
    )

    return respond(
        is_json,
        "Welcome back!",
        200,
        success=True,
        redirect_to=
            url_for(
                "admin_dashboard"
            ),
    )


# =========================================================
# ADMIN LOGOUT
# =========================================================

@app.route("/admin-logout")
def admin_logout():

    session.pop(
        "admin_id",
        None
    )

    session.pop(
        "admin_username",
        None
    )

    return redirect(
        url_for(
            "admin_page"
        )
    )


# =========================================================
# ADMIN DASHBOARD
# =========================================================

@app.route("/admin-dashboard")
@admin_page_required
def admin_dashboard():

    return render_template(
        "admin_dashboard.html",
        admin_username=
            session.get(
                "admin_username",
                "Admin"
            ),
    )


# =========================================================
# ADMIN USERS
# =========================================================

@app.route(
    "/admin/users",
    methods=["GET"]
)
@admin_api_required
def admin_users():

    users_list = list(
        users.find(
            {},
            {
                "_id": 0,
                "username": 1,
                "email": 1,
                "created_at": 1,
            },
        )
    )

    for user in users_list:

        if isinstance(
            user.get(
                "created_at"
            ),
            datetime,
        ):

            user["created_at"] = (
                user["created_at"]
                .isoformat()
            )

    return jsonify(
        users_list
    )


# =========================================================
# RESUME UPLOAD
# =========================================================

@app.route(
    "/upload-resume",
    methods=["POST"]
)
@user_api_required
def upload_resume():

    if "resume" not in request.files:

        return jsonify({
            "success": False,
            "message":
                "Please select a resume PDF."
        }), 400

    resume_file = (
        request.files["resume"]
    )

    if (
        not resume_file
        or not resume_file.filename
    ):

        return jsonify({
            "success": False,
            "message":
                "Please select a resume PDF."
        }), 400

    filename = secure_filename(
        resume_file.filename
    )

    extension = (
        filename.rsplit(
            ".",
            1
        )[-1].lower()
        if "." in filename
        else ""
    )

    if (
        extension
        not in ALLOWED_RESUME_EXTENSIONS
    ):

        return jsonify({
            "success": False,
            "message":
                "Only PDF resumes are supported."
        }), 400

    resume_file.stream.seek(
        0,
        2
    )

    file_size = (
        resume_file.stream.tell()
    )

    resume_file.stream.seek(0)

    if file_size > MAX_RESUME_SIZE:

        return jsonify({
            "success": False,
            "message":
                "Resume must be smaller than 10 MB."
        }), 400

    try:

        reader = PdfReader(
            resume_file.stream
        )

        extracted_text = ""

        for page in reader.pages:

            page_text = (
                page.extract_text()
                or ""
            )

            extracted_text += (
                page_text + "\n"
            )

    except Exception as exc:

        app.logger.warning(
            "Resume PDF extraction failed: %s",
            exc
        )

        return jsonify({
            "success": False,
            "message":
                "Could not read this PDF."
        }), 400

    extracted_text = (
        extracted_text.strip()
    )

    if not extracted_text:

        return jsonify({
            "success": False,
            "message": (
                "No readable text was found in this PDF. "
                "Please upload a text-based PDF."
            )
        }), 400

    user_id = session.get(
        "user_id"
    )

    username = (
        session.get("username")
        or session.get("email")
        or "User"
    )

    resumes.update_one(
        {
            "user_id": user_id
        },
        {
            "$set": {
                "user_id": user_id,
                "username": username,
                "filename": filename,
                "resume_text":
                    extracted_text,
                "uploaded_at":
                    datetime.now(
                        timezone.utc
                    ),
            }
        },
        upsert=True,
    )

    return jsonify({
        "success": True,
        "message":
            "Resume uploaded successfully!",
        "filename": filename,
    })


# =========================================================
# CHATBOT PDF / DOCUMENT UPLOAD
# =========================================================

@app.route(
    "/upload-document",
    methods=["POST"]
)
@user_api_required
def upload_document():

    if "file" not in request.files:

        return jsonify({
            "success": False,
            "message":
                "Please select a PDF file."
        }), 400

    uploaded_file = (
        request.files["file"]
    )

    if (
        not uploaded_file
        or not uploaded_file.filename
    ):

        return jsonify({
            "success": False,
            "message":
                "Please select a PDF file."
        }), 400

    original_filename = (
        uploaded_file.filename
    )

    filename = secure_filename(
        original_filename
    )

    extension = (
        filename.rsplit(
            ".",
            1
        )[-1].lower()
        if "." in filename
        else ""
    )

    if (
        extension
        not in ALLOWED_DOCUMENT_EXTENSIONS
    ):

        return jsonify({
            "success": False,
            "message":
                "Only PDF files are supported."
        }), 400

    # -----------------------------------------------------
    # Check file size
    # -----------------------------------------------------

    uploaded_file.stream.seek(
        0,
        2
    )

    file_size = (
        uploaded_file.stream.tell()
    )

    uploaded_file.stream.seek(0)

    if file_size > MAX_DOCUMENT_SIZE:

        return jsonify({
            "success": False,
            "message":
                "PDF must be smaller than 10 MB."
        }), 400

    # -----------------------------------------------------
    # Extract PDF text
    # -----------------------------------------------------

    try:

        reader = PdfReader(
            uploaded_file.stream
        )

        extracted_text = ""

        for page in reader.pages:

            page_text = (
                page.extract_text()
                or ""
            )

            extracted_text += (
                page_text + "\n"
            )

    except Exception as exc:

        app.logger.warning(
            "PDF extraction failed: %s",
            exc
        )

        return jsonify({
            "success": False,
            "message":
                "Could not read this PDF."
        }), 400

    extracted_text = (
        extracted_text.strip()
    )

    if not extracted_text:

        return jsonify({
            "success": False,
            "message": (
                "No readable text was found "
                "in this PDF."
            )
        }), 400

    # -----------------------------------------------------
    # Current user
    # -----------------------------------------------------

    user_id = session.get(
        "user_id"
    )

    username = (
        session.get("username")
        or session.get("email")
        or "User"
    )

    # -----------------------------------------------------
    # Save PDF content in MongoDB
    # -----------------------------------------------------

    document = {
        "user_id": user_id,
        "username": username,
        "filename": filename,
        "original_filename":
            original_filename,
        "document_type":
            "chatbot_pdf",
        "text":
            extracted_text,
        "file_size":
            file_size,
        "uploaded_at":
            datetime.now(
                timezone.utc
            ),
    }

    result = documents.insert_one(
        document
    )

    return jsonify({
        "success": True,
        "message":
            "PDF uploaded successfully!",
        "document_id":
            str(
                result.inserted_id
            ),
        "filename":
            original_filename,
        "text_length":
            len(extracted_text),
    }), 200


# =========================================================
# CHAT PAGE
# =========================================================

@app.route(
    "/chat",
    methods=["GET"]
)
@user_page_required
def chat_page():

    return render_template(
        "chat.html",
        username=session.get(
            "username",
            "there"
        ),
    )


# =========================================================
# CHAT API
# =========================================================

@app.route(
    "/chat",
    methods=["POST"]
)
@user_api_required
def chat():

    start_time = (
        time.perf_counter()
    )

    data = request.get_json(
        silent=True
    )

    if (
        not data
        or "message" not in data
    ):

        return jsonify(
            {
                "reply":
                    "No message received."
            }
        ), 400

    user_message = (
        data["message"] or ""
    ).strip()

    if not user_message:

        return jsonify(
            {
                "reply":
                    "Please enter a message."
            }
        ), 400

    if (
        len(user_message)
        > MAX_MESSAGE_LENGTH
    ):

        return jsonify(
            {
                "reply": (
                    "That question is a little long - "
                    "please shorten it and try again."
                )
            }
        ), 400

    clean_question = (
        normalize_question(
            user_message
        )
    )

    asker = (
        session.get("username")
        or session.get("email")
        or "Guest"
    )

    # =====================================================
    # PULL IN ANY DOCUMENT THE USER UPLOADED
    #
    # Fixes the bug where /upload-document saved the PDF text
    # into MongoDB but /chat never looked it up again, so
    # questions like "summarize my resume" were sent to
    # Ollama with no idea a file had been uploaded.
    # =====================================================

    user_id = session.get("user_id")

    document_context = ""
    document_name = ""

    latest_doc = get_latest_document_for_user(user_id)

    if latest_doc:

        document_context = (
            latest_doc.get("text", "")[:MAX_DOCUMENT_CONTEXT_CHARS]
        )

        document_name = latest_doc.get(
            "original_filename",
            latest_doc.get("filename", "the uploaded file")
        )

    # =====================================================
    # SPECIAL CREATOR RESPONSE
    # =====================================================

    if "swathi" in user_message.lower():

        return Response(
            "Swathi is the awesome creator behind Placementor AI. 🚀",
            mimetype="text/plain",
        )

    # =====================================================
    # 1. SEARCH MONGODB FIRST
    # =====================================================

    question_data = (
        find_qa_match(
            clean_question
        )
    )

    if question_data:

        ai_reply = (
            question_data.get(
                "answer",
                "No answer found."
            )
        )

        response_time = round(
            time.perf_counter()
            - start_time,
            4,
        )

        log_chat(
            asker,
            user_message,
            ai_reply,
            "mongodb",
            response_time,
        )

        response = Response(
            ai_reply,
            mimetype="text/plain",
        )

        response.headers[
            "X-Answer-Source"
        ] = "mongodb"

        return response

    # =====================================================
    # 2. FALL BACK TO OLLAMA
    # =====================================================

    try:

        if document_context:

            ollama_prompt = (
                f"The user uploaded a document called "
                f"'{document_name}'. Here is its content:\n\n"
                f"{document_context}\n\n"
                f"Now answer the user's question below. Use the "
                f"document above if it's relevant to the question:\n\n"
                f"{user_message}"
            )

        else:

            ollama_prompt = user_message

        chunks = (
            stream_ollama_response(
                ollama_prompt
            )
        )

    except OllamaError as exc:

        app.logger.warning(
            "Ollama Cloud error: %s",
            exc,
        )

        return jsonify(
            {
                "reply": (
                    "Placementor AI's cloud assistant "
                    "is unavailable right now. "
                    "Please try again shortly."
                )
            }
        ), 502

    # =====================================================
    # STREAM OLLAMA RESPONSE
    # =====================================================

    def ollama_stream():

        full_reply = ""
        completed = False

        try:

            for text in chunks:

                full_reply += text

                yield text

            completed = True

        except Exception as exc:

            app.logger.warning(
                "Streaming error: %s",
                exc,
            )

        finally:

            cleaned_reply = (
                full_reply.strip()
            )

            if (
                cleaned_reply
                and completed
            ):

                response_time = round(
                    time.perf_counter()
                    - start_time,
                    4,
                )

                # Save new Q&A into MongoDB
                # so next time MongoDB
                # can answer it.
                #
                # Skip saving into the shared knowledge base
                # when the answer came from a personal
                # uploaded document - that answer is specific
                # to this user's file, not a general fact.

                if (
                    not document_context
                    and find_qa_match(
                        clean_question
                    )
                    is None
                ):

                    qa_data.insert_one(
                        {
                            "question":
                                user_message,
                            "answer":
                                cleaned_reply,
                            "source":
                                "ollama_learned",
                            "created_at":
                                datetime.now(
                                    timezone.utc
                                ),
                        }
                    )

                log_chat(
                    asker,
                    user_message,
                    cleaned_reply,
                    "ollama",
                    response_time,
                )

    response = Response(
        stream_with_context(
            ollama_stream()
        ),
        mimetype="text/plain",
    )

    response.headers[
        "X-Answer-Source"
    ] = "ollama"

    return response


# =========================================================
# USER CHAT HISTORY
# =========================================================

@app.route(
    "/chat/history",
    methods=["GET"]
)
@user_api_required
def chat_history_for_user():

    identity = (
        session.get("username")
        or session.get("email")
    )

    if not identity:

        return jsonify([])

    limit = request.args.get(
        "limit",
        default=100,
        type=int,
    ) or 100

    limit = max(
        1,
        min(limit, 200)
    )

    cursor = (
        chat_collection.find(
            {
                "user": identity,
                "question": {
                    "$exists": True
                },
            },
            {
                "question": 1,
                "answer": 1,
                "source": 1,
                "timestamp": 1,
                "response_time": 1,
            },
        )
        .sort(
            [
                ("timestamp", -1)
            ]
        )
        .limit(limit)
    )

    results = []

    for doc in cursor:

        timestamp = (
            doc.get("timestamp")
        )

        results.append(
            {
                "id": str(
                    doc["_id"]
                ),
                "question":
                    doc.get(
                        "question",
                        "",
                    ),
                "answer":
                    doc.get(
                        "answer",
                        "",
                    ),
                "source":
                    doc.get(
                        "source",
                        "mongodb",
                    ),
                "timestamp": (
                    timestamp.isoformat()
                    if isinstance(
                        timestamp,
                        datetime,
                    )
                    else None
                ),
                "response_time":
                    doc.get(
                        "response_time"
                    ),
            }
        )

    return jsonify(
        results
    )


# =========================================================
# DELETE USER CHAT HISTORY ITEM
# =========================================================

@app.route(
    "/chat/history/<item_id>",
    methods=["DELETE"],
)
@user_api_required
def delete_chat_history_item(
    item_id
):

    identity = (
        session.get("username")
        or session.get("email")
    )

    if not identity:

        return jsonify(
            {
                "success": False,
                "message":
                    "Not logged in.",
            }
        ), 401

    try:

        object_id = ObjectId(
            item_id
        )

    except (
        InvalidId,
        TypeError,
    ):

        return jsonify(
            {
                "success": False,
                "message": (
                    "That history item doesn't exist."
                ),
            }
        ), 400

    result = (
        chat_collection.delete_one(
            {
                "_id": object_id,
                "user": identity,
            }
        )
    )

    if result.deleted_count == 0:

        return jsonify(
            {
                "success": False,
                "message": (
                    "History item not found."
                ),
            }
        ), 404

    return jsonify(
        {
            "success": True
        }
    )


# =========================================================
# ADMIN CHAT HISTORY
# =========================================================

@app.route(
    "/history",
    methods=["GET"]
)
@admin_api_required
def history():

    chats = list(
        chat_collection.find(
            {},
            {
                "_id": 0
            },
        )
    )

    for chat in chats:

        if isinstance(
            chat.get("timestamp"),
            datetime,
        ):

            chat["timestamp"] = (
                chat["timestamp"]
                .isoformat()
            )

    return jsonify(
        chats
    )


# =========================================================
# ADMIN OVERVIEW
# =========================================================

@app.route(
    "/admin/api/overview"
)
@admin_api_required
def admin_overview():

    total_users = (
        users.count_documents({})
    )

    total_chats = (
        chat_collection.count_documents({})
    )

    mongodb_count = (
        chat_collection.count_documents(
            {
                "source": "mongodb"
            }
        )
    )

    ollama_count = (
        chat_collection.count_documents(
            {
                "source": "ollama"
            }
        )
    )

    unclassified_count = max(
        total_chats
        - mongodb_count
        - ollama_count,
        0,
    )

    total_kb_entries = (
        qa_data.count_documents({})
    )

    learned_kb_entries = (
        qa_data.count_documents(
            {
                "source":
                    "ollama_learned"
            }
        )
    )

    avg_agg = list(
        chat_collection.aggregate(
            [
                {
                    "$match": {
                        "response_time": {
                            "$exists": True,
                            "$ne": None,
                        }
                    }
                },
                {
                    "$group": {
                        "_id": None,
                        "avg_time": {
                            "$avg":
                                "$response_time"
                        },
                        "count": {
                            "$sum": 1
                        },
                    }
                },
            ]
        )
    )

    avg_response_time = (
        round(
            avg_agg[0]["avg_time"],
            3,
        )
        if avg_agg
        else None
    )

    avg_sample_size = (
        avg_agg[0]["count"]
        if avg_agg
        else 0
    )

    return jsonify(
        {
            "total_users":
                total_users,
            "total_chats":
                total_chats,
            "mongodb_count":
                mongodb_count,
            "ollama_count":
                ollama_count,
            "unclassified_count":
                unclassified_count,
            "total_kb_entries":
                total_kb_entries,
            "curated_kb_entries":
                max(
                    total_kb_entries
                    - learned_kb_entries,
                    0,
                ),
            "learned_kb_entries":
                learned_kb_entries,
            "avg_response_time":
                avg_response_time,
            "avg_response_time_sample_size":
                avg_sample_size,
            "ollama_configured":
                is_configured(),
            "ollama_model":
                OLLAMA_MODEL,
        }
    )


# =========================================================
# ADMIN ACTIVITY
# =========================================================

@app.route(
    "/admin/api/activity"
)
@admin_api_required
def admin_activity():

    days = request.args.get(
        "days",
        default=14,
        type=int,
    ) or 14

    days = max(
        1,
        min(days, 90)
    )

    since = (
        datetime.now(
            timezone.utc
        )
        - timedelta(days=days)
    )

    cursor = chat_collection.find(
        {
            "timestamp": {
                "$exists": True,
                "$gte": since,
            }
        },
        {
            "timestamp": 1,
            "source": 1,
        },
    )

    buckets = {}

    for doc in cursor:

        timestamp = (
            doc.get("timestamp")
        )

        if not isinstance(
            timestamp,
            datetime,
        ):

            continue

        if timestamp.tzinfo is None:

            timestamp = timestamp.replace(
                tzinfo=timezone.utc
            )

        day_key = (
            timestamp.date()
            .isoformat()
        )

        bucket = buckets.setdefault(
            day_key,
            {
                "mongodb": 0,
                "ollama": 0,
                "other": 0,
            },
        )

        source = doc.get(
            "source"
        )

        if source == "mongodb":

            bucket["mongodb"] += 1

        elif source == "ollama":

            bucket["ollama"] += 1

        else:

            bucket["other"] += 1

    result = []

    for i in range(
        days - 1,
        -1,
        -1,
    ):

        day = (
            datetime.now(
                timezone.utc
            )
            - timedelta(days=i)
        ).date().isoformat()

        bucket = buckets.get(
            day,
            {
                "mongodb": 0,
                "ollama": 0,
                "other": 0,
            },
        )

        total = (
            bucket["mongodb"]
            + bucket["ollama"]
            + bucket["other"]
        )

        result.append(
            {
                "date": day,
                "mongodb":
                    bucket["mongodb"],
                "ollama":
                    bucket["ollama"],
                "other":
                    bucket["other"],
                "total":
                    total,
            }
        )

    return jsonify(
        {
            "days": days,
            "activity": result,
            "has_timestamped_data":
                len(buckets) > 0,
        }
    )


# =========================================================
# ADMIN TOP QUESTIONS
# =========================================================

@app.route(
    "/admin/api/top-questions"
)
@admin_api_required
def admin_top_questions():

    limit = request.args.get(
        "limit",
        default=8,
        type=int,
    ) or 8

    limit = max(
        1,
        min(limit, 25)
    )

    counter = Counter()
    display_text = {}

    for doc in chat_collection.find(
        {},
        {
            "question": 1,
            "user": 1,
        },
    ):

        raw_question = (
            doc.get("question")
        )

        if raw_question is None:

            raw_question = (
                doc.get(
                    "user",
                    "",
                )
            )

        key = normalize_question(
            raw_question
        )

        if not key:

            continue

        counter[key] += 1

        display_text.setdefault(
            key,
            raw_question.strip()
        )

    top = counter.most_common(
        limit
    )

    return jsonify(
        [
            {
                "question":
                    display_text.get(
                        key,
                        key,
                    ),
                "count":
                    count,
            }
            for key, count in top
        ]
    )


# =========================================================
# ADMIN RECENT CHATS
# =========================================================

@app.route(
    "/admin/api/recent-chats"
)
@admin_api_required
def admin_recent_chats():

    limit = request.args.get(
        "limit",
        default=25,
        type=int,
    ) or 25

    limit = max(
        1,
        min(limit, 200)
    )

    cursor = (
        chat_collection.find(
            {},
            {
                "_id": 0
            },
        )
        .sort(
            [
                ("timestamp", -1)
            ]
        )
        .limit(limit)
    )

    normalized = []

    for doc in cursor:

        is_new_schema = (
            doc.get("question")
            is not None
        )

        question = (
            doc.get("question")
            if is_new_schema
            else doc.get("user", "")
        )

        answer = (
            doc.get("answer")
            if doc.get("answer")
            is not None
            else doc.get("bot", "")
        )

        timestamp = (
            doc.get("timestamp")
        )

        normalized.append(
            {
                "user": (
                    doc.get("user")
                    if is_new_schema
                    else "Legacy"
                ),
                "question":
                    question,
                "answer":
                    answer,
                "source":
                    doc.get(
                        "source",
                        "unclassified",
                    ),
                "timestamp": (
                    timestamp.isoformat()
                    if isinstance(
                        timestamp,
                        datetime,
                    )
                    else None
                ),
                "response_time":
                    doc.get(
                        "response_time"
                    ),
            }
        )

    return jsonify(
        normalized
    )


# =========================================================
# ERROR HANDLERS
# =========================================================

@app.errorhandler(404)
def not_found(_e):

    return render_template(
        "error.html",
        code=404,
        message=(
            "This page drifted off "
            "the placement track."
        ),
    ), 404


@app.errorhandler(500)
def server_error(_e):

    return render_template(
        "error.html",
        code=500,
        message=(
            "Something went wrong on our end. "
            "Please try again."
        ),
    ), 500


# =========================================================
# RUN APPLICATION
# =========================================================

if __name__ == "__main__":

    port = int(
        os.environ.get(
            "PORT",
            5000,
        )
    )

    app.run(
        debug=True,
        host="0.0.0.0",
        port=port,
        threaded=True,
    )