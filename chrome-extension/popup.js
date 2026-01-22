const chatContainer = document.getElementById("chat-container");
const questionInput = document.getElementById("question");
const sendBtn = document.getElementById("sendBtn");
const closeBtn = document.getElementById("closeBtn");
const themeToggle = document.getElementById("themeToggle");
const infoMessage = document.getElementById("info-message");
const summaryBtn = document.getElementById("summaryBtn");


let currentYoutubeUrl = null;
let chatHistory = [];
let isThinking = false;

//This function helps to store chat on the localstorage by extracting videoID but not reliable to send this id to the backend.
function extractVideoId(youtubeUrl) {
  try {
    const url = new URL(youtubeUrl);

    if (url.hostname.includes("youtube.com")) {
      return url.searchParams.get("v");
    }

    if (url.hostname === "youtu.be") {
      return url.pathname.slice(1);
    }

    return null;
  } catch {
    return null;
  }
}

function saveChat() {
  if (!currentYoutubeUrl) return;

  const videoId = extractVideoId(currentYoutubeUrl);
  if (!videoId) return;

  localStorage.setItem(
    `chat_${videoId}`,
    JSON.stringify(chatHistory)
  );
}




// Theme management
function initTheme() {
  const savedTheme = localStorage.getItem('theme') || 'light';
  document.documentElement.setAttribute('data-theme', savedTheme);
}

themeToggle.addEventListener("click", () => {
  const currentTheme = document.documentElement.getAttribute('data-theme');
  const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
  document.documentElement.setAttribute('data-theme', newTheme);
  localStorage.setItem('theme', newTheme);
});

initTheme();

// Close popup manually
closeBtn.addEventListener("click", () => {
  window.close();
});



// Detect active tab URL
chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
  const url = tabs[0].url || "";

  if (!url.includes("youtube.com/watch")) {
    infoMessage.textContent = "This plugin works only on YouTube Video.";
    disableInput();
    return;
  }

  chrome.tabs.sendMessage(
    tabs[0].id,
    { type: "GET_YOUTUBE_URL" },
    (response) => {
      // if (response && response.url) {
      //     currentYoutubeUrl = response.url;
      //     chatHistory = [];
      //     renderChat();
      //     infoMessage.textContent = "";
      // }

      if (response && response.url) {
        currentYoutubeUrl = response.url;

        const videoId = extractVideoId(currentYoutubeUrl);
        const savedChat = localStorage.getItem(`chat_${videoId}`);

        chatHistory = savedChat ? JSON.parse(savedChat) : [];

        renderChat();
        infoMessage.textContent = "";
      }

    }
  );
});

function disableInput() {
  questionInput.disabled = true;
  sendBtn.disabled = true;
  summaryBtn.disabled = true;
}

// Hide empty state when chat has messages
function updateEmptyState() {
  const emptyState = chatContainer.querySelector('.empty-state');
  if (emptyState) {
    if (chatHistory.length > 0) {
      emptyState.style.display = 'none';
    } else {
      emptyState.style.display = 'flex';
    }
  }
}

// Render chat
function renderChat() {
  // Remove all messages but keep empty state
  const messages = chatContainer.querySelectorAll('.message');
  messages.forEach(msg => msg.remove());

  chatHistory.forEach(msg => {
    const div = document.createElement("div");
    div.className = `message ${msg.role}`;
    
    // Add typing indicator for "Thinking..." messages
    if (msg.role === "bot" && msg.text === "Thinking...") {
      div.innerHTML = '<div class="typing-indicator"><span></span><span></span><span></span></div>';
    } else {
      div.textContent = msg.text;
    }
    
    chatContainer.appendChild(div);
  });

  updateEmptyState();
  chatContainer.scrollTop = chatContainer.scrollHeight;

}

// Send message
sendBtn.addEventListener("click", async () => {
  if (isThinking) return;

  const question = questionInput.value.trim();
  if (!question || !currentYoutubeUrl) return;

  isThinking = true;
  sendBtn.disabled = true;
  summaryBtn.disabled = true;

  chatHistory.push({ role: "user", text: question });
  saveChat();
  renderChat();
  questionInput.value = "";

  const thinkingIndex = chatHistory.push({
    role: "bot",
    text: "Thinking..."
  }) - 1;
  renderChat();

  try {
    const res = await fetch("https://youtube-chatbot-backend-j2wf.onrender.com/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        youtube_url: currentYoutubeUrl,
        question: question,
        chat_history: chatHistory.slice(-6)
      })
    });

    const data = await res.json();
    if (data.status === "NO_ENGLISH_TRANSCRIPT") {
        chatHistory[thinkingIndex].text = data.message;
    } else {
        chatHistory[thinkingIndex].text = data.answer || "No answer received";
    }

    saveChat();

  } catch (err) {
    chatHistory[thinkingIndex].text = "Error connecting to backend";
  }

  isThinking = false;
  sendBtn.disabled = false;
  summaryBtn.disabled = false;
  renderChat();
});


//summary 
summaryBtn.addEventListener("click", async () => {
  if (isThinking || !currentYoutubeUrl) return;

  isThinking = true;
  sendBtn.disabled = true;
  summaryBtn.disabled = true;

  chatHistory.push({
    role: "user",
    text: "Summarize this video"
  });
  renderChat();

  const thinkingIndex = chatHistory.push({
    role: "bot",
    text: "Thinking..."
  }) - 1;
  renderChat();

  try {
    const res = await fetch("https://youtube-chatbot-backend-j2wf.onrender.com/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        youtube_url: currentYoutubeUrl,
        question: "__SUMMARY__"
      })
    });

    const data = await res.json();
    if (data.status === "NO_ENGLISH_TRANSCRIPT") {
      chatHistory[thinkingIndex].text = data.message;
    } else {
      chatHistory[thinkingIndex].text = data.answer;
    }

    saveChat();

  } catch (err) {
    chatHistory[thinkingIndex].text = "Error generating summary";
  }

  isThinking = false;
  sendBtn.disabled = false;
  summaryBtn.disabled = false;
  renderChat();
});


// Enter key support
questionInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    sendBtn.click();
  }
});

// Auto-focus input on load
setTimeout(() => {
  questionInput.focus();
}, 300);