// static/js/chat.js

document.addEventListener("DOMContentLoaded", () => {
  const toggleBtn = document.getElementById("chatbot-toggle");
  const closeBtn = document.getElementById("chatbot-close");
  const windowEl = document.getElementById("chatbot-window");
  let chatHistory = [];
  const messagesEl = document.getElementById("chatbot-messages");
  const inputEl = document.getElementById("chatbot-input");
  const sendBtn = document.getElementById("chatbot-send");

  if (!toggleBtn) return; // Not logged in

  toggleBtn.addEventListener("click", () => {
    windowEl.classList.remove("hidden");
    toggleBtn.style.display = "none";
    inputEl.focus();
  });

  closeBtn.addEventListener("click", () => {
    windowEl.classList.add("hidden");
    toggleBtn.style.display = "flex";
  });

  function appendMessage(text, sender, isHtml=false) {
    const msgDiv = document.createElement("div");
    msgDiv.classList.add("message", sender);
    if (isHtml) {
      msgDiv.innerHTML = text;
    } else {
      msgDiv.textContent = text;
    }
    messagesEl.appendChild(msgDiv);
    messagesEl.scrollTop = messagesEl.scrollHeight;
  }

  function appendLoading() {
    const msgDiv = document.createElement("div");
    msgDiv.classList.add("message", "bot", "loading-msg");
    msgDiv.innerHTML = "<span class='loader'></span> Pensando...";
    messagesEl.appendChild(msgDiv);
    messagesEl.scrollTop = messagesEl.scrollHeight;
    return msgDiv;
  }

  async function sendMessage() {
    const text = inputEl.value.trim();
    if (!text) return;

    appendMessage(text, "user");
    inputEl.value = "";
    inputEl.disabled = true;
    sendBtn.disabled = true;

    const loadingMsg = appendLoading();

    chatHistory.push({ role: "user", parts: [{ text: text }] });

    try {
      const response = await axios.post("/api/chat", { history: chatHistory });
      loadingMsg.remove();
      appendMessage(response.data.response, "bot", response.data.is_html);
      chatHistory.push({ role: "model", parts: [{ text: response.data.raw_text }] });
    } catch (error) {
      console.error(error);
      loadingMsg.remove();
      const errorMsg = error.response && error.response.data && error.response.data.response 
                       ? error.response.data.response 
                       : (error.response && error.response.data && error.response.data.error ? error.response.data.error : "Hubo un error de conexión.");
      appendMessage(errorMsg, "error");
      // Revertir el historial si hay error
      chatHistory.pop();
    } finally {
      inputEl.disabled = false;
      sendBtn.disabled = false;
      inputEl.focus();
    }
  }

  sendBtn.addEventListener("click", sendMessage);
  inputEl.addEventListener("keypress", (e) => {
    if (e.key === "Enter") sendMessage();
  });
});
