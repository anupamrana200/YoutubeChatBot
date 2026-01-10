const askBtn = document.getElementById("askBtn");
const questionInput = document.getElementById("question");
const answerDiv = document.getElementById("answer");
const videoUrlDiv = document.getElementById("video-url");

let currentYoutubeUrl = null;

// Get YouTube URL from content script
chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
  chrome.tabs.sendMessage(
    tabs[0].id,
    { type: "GET_YOUTUBE_URL" },
    (response) => {
      if (response && response.url) {
        currentYoutubeUrl = response.url;
        videoUrlDiv.textContent = response.url;
      } else {
        videoUrlDiv.textContent = "Not a YouTube video";
      }
    }
  );
});

// Ask question
askBtn.addEventListener("click", async () => {
  const question = questionInput.value.trim();

  if (!currentYoutubeUrl || !question) {
    alert("Missing YouTube URL or question");
    return;
  }

  answerDiv.textContent = "Thinking...";

  try {
    const res = await fetch("http://localhost:8000/ask", {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        youtube_url: currentYoutubeUrl,
        question: question
      })
    });

    const data = await res.json();

    answerDiv.textContent = data.answer || "No answer received";

  } catch (err) {
    answerDiv.textContent = "Error connecting to backend";
    console.error(err);
  }
});
