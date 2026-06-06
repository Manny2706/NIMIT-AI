const transcriptEl = document.getElementById('transcript');
const submitBtn = document.getElementById('submit');
const statusEl = document.getElementById('status');
const resultsEl = document.getElementById('results');
function renderCards(signals) {
  resultsEl.innerHTML = '';

  if (!signals.length) {
    resultsEl.innerHTML = '<div class="empty">No signals found.</div>';
    return;
  }

  signals.forEach((signal) => {
    const card = document.createElement('article');
    card.className = 'card';
    card.innerHTML = `
      <div class="card-top">
        <span class="type">${signal.type}</span>
      </div>
      <blockquote>“${signal.quote}”</blockquote>
      <p class="tip">${signal.tip}</p>
    `;
    resultsEl.appendChild(card);
  });
}

async function analyseTranscript() {
  const transcript = transcriptEl.value.trim();
  if (!transcript) {
    statusEl.textContent = 'Paste a transcript first.';
    return;
  }

  statusEl.textContent = 'Analyzing...';
  submitBtn.disabled = true;

  try {
    const response = await fetch('api/analyse', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ transcript }),
    });

    const contentType = response.headers.get('content-type') || '';
    const rawBody = await response.text();
    let data = {};

    if (rawBody && contentType.includes('application/json')) {
      data = JSON.parse(rawBody);
    } else if (rawBody) {
      data = { error: rawBody };
    }

    if (!response.ok) {
      throw new Error(data.error || 'Request failed');
    }

    renderCards(Array.isArray(data.signals) ? data.signals : []);
    statusEl.textContent = 'Done.';
  } catch (error) {
    statusEl.textContent = error.message;
    resultsEl.innerHTML = '';
  } finally {
    submitBtn.disabled = false;
  }
}

submitBtn.addEventListener('click', analyseTranscript);
renderCards([]);
