(function () {
  "use strict";

  const messagesEl = document.getElementById("messages");
  const emptyStateEl = document.getElementById("chat-empty");
  const composerForm = document.getElementById("composer-form");
  const inputEl = document.getElementById("composer-input");
  const sendBtn = document.getElementById("send-btn");

  let isSending = false;
  let resumeUploaded = false;
  let resumeFilename = "";

  // -----------------------------
  // QUICK QUESTIONS
  // -----------------------------

  const QUICK_QUESTIONS = [
    "Tell me about yourself",
    "Explain OOP concepts",
    "What is Cloud Computing?",
    "Explain TCP vs UDP",
    "Why should we hire you?",
    "Difference between process and thread"
  ];

  // -----------------------------
  // SCROLL
  // -----------------------------

  function scrollBottom() {
    if (messagesEl) {
      messagesEl.scrollTop = messagesEl.scrollHeight;
    }
  }

  // -----------------------------
  // START CHAT
  // -----------------------------

  function startChat() {
    if (emptyStateEl) {
      emptyStateEl.classList.add("is-hidden");
    }

    if (messagesEl) {
      messagesEl.classList.add("is-active");
    }
  }

  // -----------------------------
  // ADD USER MESSAGE
  // -----------------------------

  function addUserMessage(text) {

    if (!messagesEl) return;

    const row = document.createElement("div");

    row.className = "msg-row user";

    // Make sure user message is visible
    row.style.display = "flex";
    row.style.justifyContent = "flex-end";
    row.style.visibility = "visible";
    row.style.opacity = "1";

    const bubble = document.createElement("div");

    bubble.className = "msg-bubble user";

    bubble.textContent = text;

    // Make sure bubble is visible
    bubble.style.display = "block";
    bubble.style.visibility = "visible";
    bubble.style.opacity = "1";

    row.appendChild(bubble);

    messagesEl.appendChild(row);

    scrollBottom();
  }

  // -----------------------------
  // ADD BOT MESSAGE
  // -----------------------------

  function addBotMessage(text) {

    if (!messagesEl) return;

    const row = document.createElement("div");

    row.className = "msg-row bot";

    const bubble = document.createElement("div");

    bubble.className = "msg-bubble bot";

    bubble.innerHTML = `
      <p class="msg-text"></p>
    `;

    const msgText =
      bubble.querySelector(".msg-text");

    if (msgText) {
      msgText.textContent = text;
    }

    row.appendChild(bubble);

    messagesEl.appendChild(row);

    scrollBottom();
  }

  // -----------------------------
  // SENDING STATE
  // -----------------------------

  function setSending(state) {

    isSending = state;

    if (sendBtn) {
      sendBtn.disabled = state;
    }
  }

  // -----------------------------
  // PDF UPLOAD UI
  // -----------------------------

  function createUploadUI() {

    if (!composerForm) return;

    let fileInput =
      document.getElementById(
        "resume-file-input"
      );

    if (!fileInput) {

      fileInput =
        document.createElement("input");

      fileInput.type = "file";

      fileInput.id =
        "resume-file-input";

      fileInput.accept =
        ".pdf,application/pdf";

      fileInput.style.display =
        "none";

      composerForm.appendChild(
        fileInput
      );
    }

    let attachBtn =
      document.getElementById(
        "attach-resume-btn"
      );

    if (!attachBtn) {

      attachBtn =
        document.createElement("button");

      attachBtn.type = "button";

      attachBtn.id =
        "attach-resume-btn";

      attachBtn.className =
        "attach-btn";

      attachBtn.title =
        "Upload Resume PDF";

      attachBtn.textContent =
        "📎";

      composerForm.insertBefore(
        attachBtn,
        inputEl
      );
    }

    attachBtn.addEventListener(
      "click",
      function () {

        if (!isSending) {
          fileInput.click();
        }

      }
    );

    fileInput.addEventListener(
      "change",
      function () {

        if (this.files.length > 0) {

          uploadPDF(
            this.files[0]
          );

          this.value = "";
        }

      }
    );
  }

  // -----------------------------
  // UPLOAD PDF
  // -----------------------------

  function uploadPDF(file) {

    if (!file) return;

    // PDF check
    if (
      !file.name
        .toLowerCase()
        .endsWith(".pdf")
    ) {

      alert(
        "Only PDF files are allowed."
      );

      return;
    }

    // 10 MB check
    if (
      file.size >
      10 * 1024 * 1024
    ) {

      alert(
        "PDF must be smaller than 10 MB."
      );

      return;
    }

    const formData =
      new FormData();

    // IMPORTANT
    // Flask expects "file"
    formData.append(
      "file",
      file
    );

    setSending(true);

    fetch(
      "/upload-document",
      {
        method: "POST",
        body: formData
      }
    )

      .then(
        async response => {

          const data =
            await response.json()
              .catch(
                () => ({})
              );

          if (
            !response.ok ||
            !data.success
          ) {

            throw new Error(
              data.message ||
              "PDF upload failed."
            );
          }

          return data;
        }
      )

      .then(
        data => {

          resumeUploaded =
            true;

          resumeFilename =
            data.filename ||
            file.name;

          showUploadStatus(
            resumeFilename
          );

          console.log(
            "PDF uploaded:",
            resumeFilename
          );
        }
      )

      .catch(
        error => {

          console.error(
            "PDF ERROR:",
            error
          );

          alert(
            error.message ||
            "PDF upload failed."
          );
        }
      )

      .finally(
        () => {

          setSending(false);

          if (inputEl) {
            inputEl.focus();
          }

        }
      );
  }

  // -----------------------------
  // SHOW UPLOAD STATUS
  // -----------------------------

  function showUploadStatus(
    filename
  ) {

    const old =
      document.getElementById(
        "resume-upload-status"
      );

    if (old) {
      old.remove();
    }

    const status =
      document.createElement("div");

    status.id =
      "resume-upload-status";

    status.className =
      "resume-upload-status";

    status.textContent =
      "📄 " + filename;

    const composerWrap =
      document.querySelector(
        ".composer-wrap"
      );

    if (composerWrap) {

      composerWrap.insertBefore(
        status,
        composerWrap.firstChild
      );
    }
  }

  // -----------------------------
  // SEND MESSAGE
  // -----------------------------

  function sendMessage(text) {

    text =
      (text || "").trim();

    if (
      !text ||
      isSending
    ) {
      return;
    }

    startChat();

    // Show user's message immediately
    addUserMessage(text);

    if (inputEl) {
      inputEl.value = "";
    }

    setSending(true);

    // Thinking message
    const thinking =
      document.createElement("div");

    thinking.className =
      "msg-row bot";

    thinking.innerHTML = `
      <div class="msg-bubble bot">
        Thinking...
      </div>
    `;

    messagesEl.appendChild(
      thinking
    );

    scrollBottom();

    // -----------------------------
    // SEND TO FLASK
    // -----------------------------

    fetch(
      "/chat",
      {
        method: "POST",

        headers: {
          "Content-Type":
            "application/json"
        },

        body: JSON.stringify({

          message: text,

          resume_attached:
            resumeUploaded

        })
      }
    )

      .then(
        async response => {

          if (!response.ok) {

            const data =
              await response.json()
                .catch(
                  () => ({})
                );

            throw new Error(
              data.message ||
              data.reply ||
              "Chat request failed."
            );
          }

          return response;
        }
      )

      .then(
        response => {

          return response.text();
        }
      )

      .then(
        answer => {

          thinking.remove();

          addBotMessage(
            answer
          );
        }
      )

      .catch(
        error => {

          thinking.remove();

          addBotMessage(
            "Error: " +
            error.message
          );
        }
      )

      .finally(
        () => {

          setSending(false);

          if (inputEl) {
            inputEl.focus();
          }

        }
      );
  }

  // -----------------------------
  // FORM SUBMIT
  // -----------------------------

  if (composerForm) {

    composerForm.addEventListener(
      "submit",
      function (e) {

        e.preventDefault();

        if (inputEl) {
          sendMessage(
            inputEl.value
          );
        }

      }
    );
  }

  // -----------------------------
  // SEND BUTTON CLICK
  // -----------------------------

  if (sendBtn) {

    sendBtn.addEventListener(
      "click",
      function (e) {

        e.preventDefault();

        if (inputEl) {

          sendMessage(
            inputEl.value
          );
        }

      }
    );
  }

  // -----------------------------
  // ENTER KEY
  // -----------------------------

  if (inputEl) {

    inputEl.addEventListener(
      "keydown",
      function (e) {

        if (
          e.key === "Enter" &&
          !e.shiftKey
        ) {

          e.preventDefault();

          sendMessage(
            inputEl.value
          );
        }

      }
    );
  }

  // -----------------------------
  // QUICK QUESTIONS
  // -----------------------------

  const chips =
    document.getElementById(
      "quick-chips-empty"
    );

  if (chips) {

    chips.innerHTML = "";

    QUICK_QUESTIONS.forEach(
      question => {

        const button =
          document.createElement(
            "button"
          );

        button.className =
          "chip";

        button.type =
          "button";

        button.textContent =
          question;

        button.onclick =
          function () {

            sendMessage(
              question
            );

          };

        chips.appendChild(
          button
        );
      }
    );
  }

  // -----------------------------
  // START
  // -----------------------------

  createUploadUI();

})();
