// Runs automatically on YouTube pages
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.type === "GET_YOUTUBE_URL") {
    sendResponse({ url: window.location.href });
  }
});
