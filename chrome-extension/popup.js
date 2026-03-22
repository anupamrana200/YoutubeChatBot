const chatContainer = document.getElementById("chat-container");
const questionInput  = document.getElementById("question");
const sendBtn        = document.getElementById("sendBtn");
const closeBtn       = document.getElementById("closeBtn");
const themeToggle    = document.getElementById("themeToggle");
const infoMessage    = document.getElementById("info-message");
const summaryBtn     = document.getElementById("summaryBtn");
const scrollBtn      = document.getElementById("scrollBtn");

let currentYoutubeUrl = null;
let chatHistory       = [];
let isThinking        = false;

// ─── Built-in Markdown parser ─────────────────────────────────────────────────

function parseMarkdown(text) {
  // Step 1 — escape raw HTML
  let escaped = text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");

  // Step 2 — process line by line, grouping list blocks
  const lines  = escaped.split("\n");
  const output = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];

    // ── Headings
    if (/^### (.+)/.test(line)) {
      output.push(`<h3>${line.replace(/^### /, "")}</h3>`);
      i++; continue;
    }
    if (/^## (.+)/.test(line)) {
      output.push(`<h2>${line.replace(/^## /, "")}</h2>`);
      i++; continue;
    }
    if (/^# (.+)/.test(line)) {
      output.push(`<h1>${line.replace(/^# /, "")}</h1>`);
      i++; continue;
    }

    // ── Blockquote
    if (/^&gt; (.+)/.test(line)) {
      output.push(`<blockquote>${line.replace(/^&gt; /, "")}</blockquote>`);
      i++; continue;
    }

    // ── Horizontal rule
    if (/^(\-{3,}|\*{3,})$/.test(line.trim())) {
      output.push("<hr>");
      i++; continue;
    }

    // ── Unordered list — collect all consecutive bullet lines
    if (/^[\*\-] /.test(line)) {
      const items = [];
      while (i < lines.length && /^[\*\-] /.test(lines[i])) {
        items.push(`<li>${inlineFormat(lines[i].replace(/^[\*\-] /, ""))}</li>`);
        i++;
      }
      output.push(`<ul>${items.join("")}</ul>`);
      continue;
    }

    // ── Ordered list — collect all consecutive numbered lines, renumber them
    if (/^\d+\. /.test(line)) {
      const items = [];
      while (i < lines.length && /^\d+\. /.test(lines[i])) {
        items.push(`<li>${inlineFormat(lines[i].replace(/^\d+\. /, ""))}</li>`);
        i++;
      }
      // Use <ol> — browser handles sequential numbering (1, 2, 3...)
      output.push(`<ol>${items.join("")}</ol>`);
      continue;
    }

    // ── Blank line — paragraph break
    if (line.trim() === "") {
      output.push("<br>");
      i++; continue;
    }

    // ── Regular paragraph line
    output.push(`<p>${inlineFormat(line)}</p>`);
    i++;
  }

  return output.join("\n");
}

// Applies inline formatting: bold, italic, inline code
function inlineFormat(text) {
  // Bold: **text** or __text__
  text = text.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  text = text.replace(/__(.+?)__/g,     "<strong>$1</strong>");
  // Italic: *text* or _text_  (but not inside words)
  text = text.replace(/\*(.+?)\*/g, "<em>$1</em>");
  text = text.replace(/(?<![a-zA-Z])_(.+?)_(?![a-zA-Z])/g, "<em>$1</em>");
  // Inline code: `code`
  text = text.replace(/`([^`]+)`/g, "<code>$1</code>");
  return text;
}

// ─── Timestamp chip highlighter ───────────────────────────────────────────────

function highlightTimestamps(html) {
  return html.replace(
    /\[(\d{1,2}:\d{2}(?:\s*[–\-]\s*\d{1,2}:\d{2})?)\]/g,
    '<span class="ts-chip">[$1]</span>'
  );
}

function renderMarkdown(text) {
  return highlightTimestamps(parseMarkdown(text));
}

// ─── Other helpers ────────────────────────────────────────────────────────────

function extractVideoId(youtubeUrl) {
  try {
    const url = new URL(youtubeUrl);
    if (url.hostname.includes("youtube.com")) return url.searchParams.get("v");
    if (url.hostname === "youtu.be") return url.pathname.slice(1);
    return null;
  } catch { return null; }
}

function saveChat() {
  if (!currentYoutubeUrl) return;
  const videoId = extractVideoId(currentYoutubeUrl);
  if (!videoId) return;
  localStorage.setItem(`chat_${videoId}`, JSON.stringify(chatHistory));
}

function formatMsgTime(ts) {
  const diff = Math.floor((Date.now() - ts) / 1000);
  if (diff < 60)   return "just now";
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  return `${Math.floor(diff / 3600)}h ago`;
}

function isErrorMessage(text) {
  return (
    text === "Error connecting to backend" ||
    text === "Error generating summary"
  );
}

// ─── Theme ────────────────────────────────────────────────────────────────────

function initTheme() {
  const saved = localStorage.getItem("theme") || "light";
  document.documentElement.setAttribute("data-theme", saved);
}

themeToggle.addEventListener("click", () => {
  const curr = document.documentElement.getAttribute("data-theme");
  const next  = curr === "dark" ? "light" : "dark";
  document.documentElement.setAttribute("data-theme", next);
  localStorage.setItem("theme", next);
});

initTheme();

// ─── Close ────────────────────────────────────────────────────────────────────

closeBtn.addEventListener("click", () => window.close());

// ─── Scroll-to-bottom button ──────────────────────────────────────────────────

chatContainer.addEventListener("scroll", () => {
  const distFromBottom =
    chatContainer.scrollHeight - chatContainer.scrollTop - chatContainer.clientHeight;
  scrollBtn.classList.toggle("visible", distFromBottom > 120);
});

scrollBtn.addEventListener("click", () => {
  chatContainer.scrollTop = chatContainer.scrollHeight;
});

// ─── URL Detection ────────────────────────────────────────────────────────────

chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
  const url = tabs[0].url || "";

  if (!url.includes("youtube.com/watch")) {
    infoMessage.textContent   = "This plugin works only on YouTube Video.";
    infoMessage.style.display = "block";
    disableInput();
    return;
  }

  chrome.tabs.sendMessage(tabs[0].id, { type: "GET_YOUTUBE_URL" }, (response) => {
    if (response && response.url) {
      currentYoutubeUrl = response.url;

      const videoId   = extractVideoId(currentYoutubeUrl);
      const savedChat = localStorage.getItem(`chat_${videoId}`);
      chatHistory     = savedChat ? JSON.parse(savedChat) : [];

      infoMessage.textContent   = "";
      infoMessage.style.display = "none";

      renderChat();
    }
  });
});

function disableInput() {
  questionInput.disabled  = true;
  sendBtn.disabled        = true;
  summaryBtn.disabled     = true;
}

// ─── Empty State ──────────────────────────────────────────────────────────────

function updateEmptyState() {
  const emptyState = chatContainer.querySelector(".empty-state");
  if (!emptyState) return;
  emptyState.style.display = chatHistory.length > 0 ? "none" : "flex";
}

// ─── Render Chat ──────────────────────────────────────────────────────────────

function renderChat() {
  chatContainer.querySelectorAll(".message-wrap").forEach(el => el.remove());

  chatHistory.forEach((msg) => {
    const wrap     = document.createElement("div");
    wrap.className = `message-wrap ${msg.role}`;

    const bubble     = document.createElement("div");
    bubble.className = "message";

    if (msg.role === "bot" && msg.text === "Thinking...") {
      bubble.classList.add("thinking");
      bubble.innerHTML = '<div class="typing-indicator"><span></span><span></span><span></span></div>';

    } else if (msg.role === "bot") {
      if (isErrorMessage(msg.text)) {
        bubble.classList.add("error-msg");
        bubble.textContent = msg.text;
      } else {
        bubble.innerHTML = renderMarkdown(msg.text);
      }

    } else {
      bubble.textContent = msg.text;
    }

    wrap.appendChild(bubble);

    if (msg.text !== "Thinking..." && msg.ts) {
      const timeEl       = document.createElement("div");
      timeEl.className   = "msg-time";
      timeEl.textContent = formatMsgTime(msg.ts);
      wrap.appendChild(timeEl);
    }

    chatContainer.appendChild(wrap);
  });

  updateEmptyState();
  chatContainer.scrollTop = chatContainer.scrollHeight;
}

// ─── Send Question ────────────────────────────────────────────────────────────

sendBtn.addEventListener("click", async () => {
  if (isThinking) return;

  const question = questionInput.value.trim();
  if (!question || !currentYoutubeUrl) return;

  isThinking          = true;
  sendBtn.disabled    = true;
  summaryBtn.disabled = true;

  chatHistory.push({ role: "user", text: question, ts: Date.now() });
  saveChat();
  renderChat();
  questionInput.value = "";

  const thinkingIndex = chatHistory.push({ role: "bot", text: "Thinking..." }) - 1;
  renderChat();

  try {
    const res  = await fetch("https://youtube-chatbot-backend-xbub.onrender.com/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        youtube_url:  currentYoutubeUrl,
        question:     question,
        chat_history: chatHistory.slice(-6)
      })
    });

    const data = await res.json();
    chatHistory[thinkingIndex].text =
      data.status === "NO_ENGLISH_TRANSCRIPT"
        ? data.message
        : data.answer || "No answer received";
    chatHistory[thinkingIndex].ts = Date.now();
    saveChat();

  } catch {
    chatHistory[thinkingIndex].text = "Error connecting to backend";
    chatHistory[thinkingIndex].ts   = Date.now();
  }

  isThinking          = false;
  sendBtn.disabled    = false;
  summaryBtn.disabled = false;
  renderChat();
});

// ─── Summarize ────────────────────────────────────────────────────────────────

summaryBtn.addEventListener("click", async () => {
  if (isThinking || !currentYoutubeUrl) return;

  isThinking          = true;
  sendBtn.disabled    = true;
  summaryBtn.disabled = true;

  chatHistory.push({ role: "user", text: "Summarize this video", ts: Date.now() });
  renderChat();

  const thinkingIndex = chatHistory.push({ role: "bot", text: "Thinking..." }) - 1;
  renderChat();

  try {
    const res  = await fetch("https://youtube-chatbot-backend-xbub.onrender.com/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        youtube_url: currentYoutubeUrl,
        question:    "__SUMMARY__"
      })
    });

    const data = await res.json();
    chatHistory[thinkingIndex].text =
      data.status === "NO_ENGLISH_TRANSCRIPT" ? data.message : data.answer;
    chatHistory[thinkingIndex].ts = Date.now();
    saveChat();

  } catch {
    chatHistory[thinkingIndex].text = "Error generating summary";
    chatHistory[thinkingIndex].ts   = Date.now();
  }

  isThinking          = false;
  sendBtn.disabled    = false;
  summaryBtn.disabled = false;
  renderChat();
});

// ─── Enter key ────────────────────────────────────────────────────────────────

questionInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    sendBtn.click();
  }
});

// ─── Auto-focus ───────────────────────────────────────────────────────────────

setTimeout(() => questionInput.focus(), 300);