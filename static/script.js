// Tab Switching
function switchTab(tabName) {
    document.querySelectorAll('.view').forEach(el => el.classList.remove('active'));
    document.querySelectorAll('.menu-btn').forEach(el => el.classList.remove('active'));
    document.getElementById(tabName + '-view').classList.add('active');
}

// File Upload
document.getElementById('file-upload').addEventListener('change', async function(e) {
    const file = e.target.files[0];
    if (!file) return;
    const statusDiv = document.getElementById('file-status');
    statusDiv.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Processing...';
    const formData = new FormData();
    formData.append('file', file);
    try {
        const response = await fetch('/upload', { method: 'POST', body: formData });
        const data = await response.json();
        if (response.ok) {
            statusDiv.innerHTML = `<i class="fa-solid fa-check"></i> ${data.filename} Ready`;
            addMessage('bot', "I have analyzed the file. What would you like to know?");
        } else {
            statusDiv.innerHTML = 'Error uploading.';
            alert(data.error);
        }
    } catch (error) { statusDiv.innerHTML = 'Error.'; }
});

// Chat Functionality
async function sendMessage() {
    const input = document.getElementById('user-input');
    const question = input.value.trim();
    const length = document.getElementById('length-selector').value;
    if (!question) return;
    addMessage('user', question);
    input.value = '';
    const loadingId = addMessage('bot', '<i class="fa-solid fa-spinner fa-spin"></i> Analyzing...');
    try {
        const response = await fetch('/ask', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ question: question, length: length })
        });
        const data = await response.json();
        document.getElementById(loadingId).remove();
        if (data.answer) {
            let content = data.answer.replace(/\*\*(.*?)\*\*/g, '<b>$1</b>').replace(/\n/g, '<br>');
            if (data.image) {
                content += `<div style="margin-top:15px;"><img src="${data.image}" style="max-width:100%; border-radius:8px; border:1px solid rgba(255,255,255,0.2);"></div>`;
            }
            addMessage('bot', content);
        }
    } catch (error) { document.getElementById(loadingId).innerText = "Error."; }
}

function addMessage(role, text) {
    const chatBox = document.getElementById('chat-box');
    const msgDiv = document.createElement('div');
    msgDiv.className = `message ${role}`;
    msgDiv.id = 'msg-' + Date.now();
    msgDiv.innerHTML = `<div class="avatar">${role==='bot'?'<i class="fa-solid fa-robot"></i>':'<i class="fa-solid fa-user"></i>'}</div><div class="text">${text}</div>`;
    chatBox.appendChild(msgDiv);
    chatBox.scrollTop = chatBox.scrollHeight;
    return msgDiv.id;
}

// --- UPDATED QUIZ LOGIC ---
async function generateQuiz() {
    const topic = document.getElementById('quiz-topic').value || 'the entire document';
    const difficulty = document.getElementById('quiz-difficulty').value;
    const type = document.getElementById('quiz-type').value;
    const count = document.getElementById('quiz-count').value;
    const container = document.getElementById('quiz-container');

    container.innerHTML = '<div class="empty-state"><i class="fa-solid fa-spinner fa-spin"></i> Generating custom quiz...</div>';

    try {
        const response = await fetch('/generate_quiz', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ topic, difficulty, type, count })
        });
        const data = await response.json();
        
        if(data.quiz_data) {
            renderQuiz(JSON.parse(data.quiz_data), data.type);
        }
    } catch (error) { container.innerHTML = '<p>Error generating quiz.</p>'; }
}

function renderQuiz(questions, type) {
    const container = document.getElementById('quiz-container');
    container.innerHTML = '';

    questions.forEach((q, index) => {
        const card = document.createElement('div');
        card.className = 'quiz-card';
        
        let contentHtml = '';
        
        if (type === 'multiple_choice' || type === 'true_false') {
            // MCQs and True/False Logic
            let optionsHtml = '';
            q.options.forEach(opt => {
                optionsHtml += `<button class="option-btn" onclick="checkAnswer(this, '${q.answer}')">${opt}</button>`;
            });
            contentHtml = `<div class="quiz-options">${optionsHtml}</div><div class="feedback" style="display:none; margin-top:10px; font-weight:bold;"></div>`;
        } else {
            // Short Answer / Fill in Blanks Logic (Reveal Button)
            contentHtml = `
                <button class="reveal-btn" onclick="this.nextElementSibling.style.display='block'; this.style.display='none'">Show Answer</button>
                <div class="feedback" style="display:none; margin-top:10px; color:#4ade80;"><b>Answer:</b> ${q.answer}</div>
            `;
        }

        card.innerHTML = `<h4>${index + 1}. ${q.question}</h4>${contentHtml}`;
        container.appendChild(card);
    });
}

function checkAnswer(btn, correctAnswer) {
    const parent = btn.parentElement;
    const feedback = parent.nextElementSibling;
    const selected = btn.innerText;
    parent.querySelectorAll('.option-btn').forEach(b => b.style.background = 'rgba(0,0,0,0.2)');

    if (selected.trim() === correctAnswer.trim() || selected.includes(correctAnswer)) {
        btn.style.background = 'rgba(34, 197, 94, 0.5)';
        feedback.innerText = "Correct!";
        feedback.style.color = "#4ade80";
    } else {
        btn.style.background = 'rgba(239, 68, 68, 0.5)';
        feedback.innerText = `Incorrect. Answer: ${correctAnswer}`;
        feedback.style.color = "#f87171";
    }
    feedback.style.display = 'block';
}