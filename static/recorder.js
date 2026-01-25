/**
 * Audio Recorder Module
 * Handles browser-based audio recording for interview responses
 */

async function setupRecorder(block) {
  const startBtn = block.querySelector(".startBtn");
  const stopBtn = block.querySelector(".stopBtn");
  const status = block.querySelector(".status");
  const audioInput = block.querySelector(".audioInput");
  const preview = block.querySelector(".preview");

  let mediaRecorder = null;
  let chunks = [];
  let stream = null;

  // Start recording
  async function startRecording() {
    try {
      chunks = [];

      // Request microphone access
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });

      // Use WebM format for better browser support
      const mimeType = MediaRecorder.isTypeSupported("audio/webm")
        ? "audio/webm"
        : "audio/mp4";

      mediaRecorder = new MediaRecorder(stream, { mimeType });

      mediaRecorder.ondataavailable = (e) => {
        if (e.data && e.data.size > 0) {
          chunks.push(e.data);
        }
      };

      mediaRecorder.onstop = async () => {
        const blob = new Blob(chunks, { type: mimeType });
        const audioURL = URL.createObjectURL(blob);

        preview.src = audioURL;
        preview.style.display = "block";

        status.textContent = "🎙️ Recorded ✅";
        status.style.background = "rgba(16, 185, 129, 0.2)";
        status.style.color = "var(--success-color)";

        // Convert blob to File and attach to hidden input
        const filename = mimeType === "audio/webm" ? "response.webm" : "response.mp4";
        const file = new File([blob], filename, { type: mimeType });
        const dataTransfer = new DataTransfer();
        dataTransfer.items.add(file);
        audioInput.files = dataTransfer.files;
      };

      mediaRecorder.start();
      startBtn.disabled = true;
      stopBtn.disabled = false;
      status.textContent = "🔴 Recording...";
      status.style.background = "rgba(239, 68, 68, 0.2)";
      status.style.color = "var(--danger-color)";
    } catch (error) {
      alert(
        "Microphone access denied. Please check your browser permissions and try again."
      );
      console.error("Microphone error:", error);
    }
  }

  // Stop recording
  function stopRecording() {
    if (mediaRecorder && mediaRecorder.state !== "inactive") {
      mediaRecorder.stop();
    }
    if (stream) {
      stream.getTracks().forEach((track) => track.stop());
    }
    startBtn.disabled = false;
    stopBtn.disabled = true;
  }

  // Event listeners
  startBtn.addEventListener("click", startRecording);
  stopBtn.addEventListener("click", stopRecording);
}

// Initialize all recorders when DOM is ready
window.addEventListener("DOMContentLoaded", () => {
  const recorders = document.querySelectorAll(".recorder");
  recorders.forEach((recorder) => setupRecorder(recorder));
});