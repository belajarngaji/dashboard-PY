<!DOCTYPE html>
<html lang="id">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Kuis Murid</title>
  <style>
    body {
      font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
      background: linear-gradient(135deg, #e3f2fd 0%, #f8f9ff 100%);
      margin: 0;
      padding: 2rem;
      display: flex;
      justify-content: center;
      align-items: center;
      min-height: 100vh;
    }

    .quiz-card {
      background: white;
      border-radius: 12px;
      box-shadow: 0 6px 18px rgba(0,0,0,0.1);
      padding: 2rem;
      max-width: 600px;
      width: 100%;
      animation: fadeIn 0.6s ease-in-out;
    }

    .quiz-title {
      font-size: 1.6rem;
      font-weight: 600;
      color: #1565c0;
      margin-bottom: 1.5rem;
      text-align: center;
    }

    .form-input {
      width: 100%;
      padding: 12px;
      margin: 10px 0;
      border: 1px solid #ddd;
      border-radius: 8px;
      font-size: 1rem;
      transition: border-color 0.3s;
    }

    .form-input:focus {
      border-color: #42a5f5;
      outline: none;
      box-shadow: 0 0 5px rgba(66,165,245,0.4);
    }

    .submit-btn {
      width: 100%;
      padding: 12px;
      background: linear-gradient(135deg, #42a5f5, #1e88e5);
      color: white;
      font-size: 1rem;
      font-weight: 600;
      border: none;
      border-radius: 8px;
      cursor: pointer;
      transition: transform 0.2s, box-shadow 0.2s;
    }

    .submit-btn:hover {
      transform: translateY(-2px);
      box-shadow: 0 6px 15px rgba(66,165,245,0.3);
    }

    .message {
      margin-top: 1rem;
      padding: 10px;
      border-radius: 6px;
      font-size: 0.95rem;
      display: none;
    }

    .message.success {
      color: #2e7d32;
      background: #e8f5e9;
      border-left: 4px solid #43a047;
    }

    .message.error {
      color: #c62828;
      background: #ffebee;
      border-left: 4px solid #f44336;
    }

    @keyframes fadeIn {
      from { opacity: 0; transform: translateY(20px); }
      to { opacity: 1; transform: translateY(0); }
    }
  </style>
</head>
<body>
  <div class="quiz-card">
    <h2 class="quiz-title">📝 Kerjakan Kuis</h2>
    <form id="quizForm">
      <input type="text" id="quiz_name" class="form-input" placeholder="Nama Kuis (misalnya: Matematika Bab 1)" required />
      <input type="number" id="score" class="form-input" placeholder="Skor Anda (0-100)" min="0" max="100" required />
      <button type="submit" class="submit-btn">Submit Skor</button>
    </form>
    <div id="msg" class="message"></div>
  </div>

  <script>
    const form = document.getElementById("quizForm");
    const msgBox = document.getElementById("msg");

    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const formData = new FormData();
      formData.append("quiz_name", document.getElementById("quiz_name").value);
      formData.append("score", document.getElementById("score").value);

      try {
        const res = await fetch("/api/quiz/submit", {
          method: "POST",
          body: formData,
          credentials: "include"
        });
        if (!res.ok) {
          const err = await res.json();
          throw new Error(err.detail || "Gagal submit skor");
        }
        const data = await res.json();
        msgBox.textContent = "✅ " + data.message;
        msgBox.className = "message success";
        msgBox.style.display = "block";
        setTimeout(() => { window.location.href = "/dashboard.html"; }, 1500);
      } catch (err) {
        msgBox.textContent = "❌ " + err.message;
        msgBox.className = "message error";
        msgBox.style.display = "block";
      }
    });
  </script>
</body>
</html>
