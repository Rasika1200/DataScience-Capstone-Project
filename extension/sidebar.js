const API_URL = "http://localhost:8000/api";

document.addEventListener('DOMContentLoaded', () => {
    // Top Level
    const scanBtn = document.getElementById('scan-btn');
    const statusMsg = document.getElementById('status-msg');
    const actionArea = document.getElementById('action-area');
    const dashboard = document.getElementById('dashboard');
    const closeBtn = document.getElementById('close-btn');
    
    // UI Elements
    const execSummary = document.getElementById('executive-summary');
    const riskLevel = document.getElementById('risk-level');
    const riskDot = document.getElementById('risk-dot');
    const riskDesc = document.getElementById('risk-desc');
    const fairnessVal = document.getElementById('fairness-val');
    
    // Toggles
    const fairnessToggle = document.getElementById('fairness-toggle');
    const fairnessDetails = document.getElementById('fairness-details');
    const qaToggle = document.getElementById('qa-toggle');
    const qaContainer = document.getElementById('qa-container');

    // Q&A
    const qaBtn = document.getElementById('qa-btn');
    const qaInput = document.getElementById('qa-input');
    const qaAnswer = document.getElementById('qa-answer');
    const suggestionsContainer = document.getElementById('suggestions');

    let currentUrl = "Webpage";

    // --- Event Listeners ---

    closeBtn.addEventListener('click', async () => {
        let [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
        if(tab) chrome.tabs.sendMessage(tab.id, { action: "close_sidebar" });
    });

    fairnessToggle.addEventListener('click', () => {
        if (fairnessDetails.classList.contains('hidden')) {
            fairnessDetails.classList.remove('hidden');
            fairnessToggle.innerText = "Hide details ↑";
        } else {
            fairnessDetails.classList.add('hidden');
            fairnessToggle.innerText = "View details ↓";
        }
    });

    qaToggle.addEventListener('click', () => {
        if (qaContainer.classList.contains('hidden')) {
            qaContainer.classList.remove('hidden');
            qaToggle.innerText = "⌃ Minimize Chat";
        } else {
            qaContainer.classList.add('hidden');
            qaToggle.innerText = "⌄ Quick Questions";
        }
    });

    // --- Main Logic ---

    scanBtn.addEventListener('click', async () => {
        scanBtn.classList.add('hidden');
        statusMsg.classList.remove('hidden');
        statusMsg.innerText = "Extracting text from page...";

        try {
            let [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
            
            chrome.tabs.sendMessage(tab.id, { action: "extract_text" }, async (response) => {
                if (!response || !response.text) {
                    statusMsg.innerText = "Could not extract text. Is this a restricted page?";
                    scanBtn.classList.remove('hidden');
                    return;
                }
                
                currentUrl = response.url;
                statusMsg.innerText = "Analyzing contract via AI (this may take a minute)...";
                
                try {
                    const apiRes = await fetch(`${API_URL}/analyze`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ text: response.text, source_url: currentUrl })
                    });
                        
                    if (!apiRes.ok) {
                        const errText = await apiRes.text();
                        try {
                            const errJson = JSON.parse(errText);
                            throw new Error(errJson.detail || "API Request Failed");
                        } catch(e) {
                            throw new Error(errText || "API Request Failed");
                        }
                    }
                    const data = await apiRes.json();
                    
                    // --- Update UI ---
                    actionArea.classList.add('hidden');
                    dashboard.classList.remove('hidden');
                    
                    if (!data.is_contract) {
                        execSummary.innerText = "WARNING: This doesn't look like a contract. " + data.verification_reason;
                        execSummary.style.color = "#ef4444";
                    } else {
                        execSummary.innerText = data.analysis.executive_summary;
                    }
                    
                    // Risk Setup
                    const rLevel = data.analysis.overall_risk_level.toLowerCase();
                    const dynamicRisk = data.analysis.risk_assessment || "";
                    riskDot.className = 'status-dot';
                    riskLevel.className = 'status-text';
                    
                    if (rLevel === 'high') {
                        riskDot.classList.add('bg-high');
                        riskLevel.classList.add('color-high');
                        riskLevel.innerText = "HIGH Risk Detected";
                    } else if (rLevel === 'low') {
                        riskDot.classList.add('bg-low');
                        riskLevel.classList.add('color-low');
                        riskLevel.innerText = "LOW Risk Detected";
                    } else {
                        riskDot.classList.add('bg-med');
                        riskLevel.classList.add('color-med');
                        riskLevel.innerText = "MODERATE Risk";
                    }
                    riskDesc.innerText = "Reason: " + (dynamicRisk || "Standard terms require review.");
                    
                    const riskSources = data.analysis.risk_sources || [];
                    renderSourceChips('risk-sources', riskSources);
                    
                    // Fairness Setup
                    const fSummary = data.analysis.fairness_summary || "Balanced";
                    const fDetails = data.analysis.fairness_details || "Balanced obligations.";
                    fairnessVal.innerText = fSummary; // Short title
                    document.getElementById('fairness-reason').innerText = fDetails; // Full description
                    
                    const fairnessSources = data.analysis.fairness_sources || [];
                    renderSourceChips('fairness-sources', fairnessSources);
                    
                    // --- Dynamic Questions ---
                    suggestionsContainer.innerHTML = ""; // Clear any placeholders
                    const dynamicQs = data.dynamic_questions || [];
                    if (dynamicQs.length > 0) {
                        dynamicQs.forEach(q => {
                            const pill = document.createElement("span");
                            pill.className = "suggestion-pill";
                            pill.innerText = q;
                            pill.addEventListener('click', () => {
                                qaInput.value = pill.innerText;
                                qaBtn.click();
                            });
                            suggestionsContainer.appendChild(pill);
                        });
                    } else {
                        // Fallback
                        const fallbackPill = document.createElement("span");
                        fallbackPill.className = "suggestion-pill";
                        fallbackPill.innerText = "What are the key risks?";
                        fallbackPill.addEventListener('click', () => {
                            qaInput.value = fallbackPill.innerText;
                            qaBtn.click();
                        });
                        suggestionsContainer.appendChild(fallbackPill);
                    }
                    
                    // --- Send Highlight Message ---
                    // Try to grab some risky phrases to highlight based on the AI assessment
                    // For now, we will extract some key words from the executive summary to demonstrate the feature
                    const summaryWords = execSummary.innerText.split(' ');
                    const riskyPhrases = [
                        "termination", "liability", "indemnification", "warranties", 
                        "governing law", "exclusive", "penalty"
                    ].filter(phrase => execSummary.innerText.toLowerCase().includes(phrase));
                    
                    // Also pass the full text just in case we want to use the actual clauses
                    chrome.tabs.sendMessage(tab.id, { 
                        action: "highlight_phrases", 
                        phrases: riskyPhrases.length > 0 ? riskyPhrases : ["liability", "termination"] 
                    });
                    
                } catch (err) {
                    console.error(err);
                    let msg = err.message;
                    if (msg === "Failed to fetch") msg = "Cannot connect to localhost:8000. Is the API running?";
                    statusMsg.innerText = "Error: " + msg;
                    scanBtn.classList.remove('hidden');
                }
            });
            
        } catch (err) {
            console.error(err);
            statusMsg.innerText = "Error accessing tab.";
            scanBtn.classList.remove('hidden');
        }
    });

    // --- Q&A Logic ---
    qaBtn.addEventListener('click', async () => {
        const q = qaInput.value.trim();
        if (!q) return;
        
        qaAnswer.classList.remove('hidden');
        qaAnswer.innerHTML = `<div class="answer-box pulsing">⏳ Analyzing contract...</div>`;
        
        try {
            const apiRes = await fetch(`${API_URL}/qa`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ question: q, source_url: currentUrl })
            });
            
            if (!apiRes.ok) throw new Error("API Error");
            const data = await apiRes.json();
            
            let answerText = data.answer;
            const isLong = answerText.length > 150;
            let displayHtml = `<div class="answer-box"><strong>A:</strong> `;
            
            const formattedAnswer = answerText.replace(/\n/g, '<br>');
            
            if (isLong) {
                const shortText = answerText.substring(0, 150).replace(/\n/g, '<br>') + "...";
                displayHtml += `<span id="qa-short-text">${shortText}</span>`;
                displayHtml += `<span id="qa-full-text" class="hidden">${formattedAnswer}</span>`;
                displayHtml += `<br><button id="qa-show-more" class="toggle-btn" style="margin-top: 8px;">⌄ Show full answer</button>`;
            } else {
                displayHtml += formattedAnswer;
            }
            
            // Append sources
            if (data.sources && data.sources.length > 0) {
                let confText = "Low";
                if (data.confidence > 0.7) confText = "High";
                else if (data.confidence > 0.4) confText = "Moderate";
                
                displayHtml += `
                <div style="margin-top: 12px; padding-top: 10px; border-top: 1px dashed rgba(255,255,255,0.1);">
                    <div class="source-text" style="color: #94a3b8; font-size: 11px; margin-bottom: 6px;">📄 Sources:</div>
                    <div id="qa-sources-container" class="source-chips-container"></div>
                    <div class="source-text" style="color: #94a3b8; font-size: 11px; margin-top: 8px;">🎯 Confidence: ${confText}</div>
                </div>`;
            }
            
            displayHtml += `</div>`;
            qaAnswer.innerHTML = displayHtml;

            // Render chips for QA
            if (data.sources && data.sources.length > 0) {
                renderSourceChips('qa-sources-container', data.sources);
            }
            
            
            // Wire up show more
            if (isLong) {
                document.getElementById('qa-show-more').addEventListener('click', (e) => {
                    const btn = e.target;
                    const shortEl = document.getElementById('qa-short-text');
                    const fullEl = document.getElementById('qa-full-text');
                    
                    if (fullEl.classList.contains('hidden')) {
                        fullEl.classList.remove('hidden');
                        shortEl.classList.add('hidden');
                        btn.innerText = "⌃ Show less";
                    } else {
                        fullEl.classList.add('hidden');
                        shortEl.classList.remove('hidden');
                        btn.innerText = "⌄ Show full answer";
                    }
                });
            }
            
        } catch (err) {
            qaAnswer.innerHTML = `<div class="answer-box" style="border-color: #ef4444;"><strong style="color: #ef4444;">Failed to get an answer.</strong> Check if the local API server is running.</div>`;
        }
    });
});

/**
 * Helper to render clickable source chips
 */
function renderSourceChips(containerId, sources) {
    const container = document.getElementById(containerId);
    if (!container) return;
    
    container.innerHTML = "";
    container.classList.add('source-chips-container');
    
    sources.forEach(src => {
        const chip = document.createElement("span");
        chip.className = "source-chip";
        chip.innerText = src;
        chip.title = "Jump to section";
        
        chip.addEventListener('click', async () => {
            let [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
            if (tab) {
                chrome.tabs.sendMessage(tab.id, { 
                    action: "scrollToSection", 
                    sectionText: src 
                });
            }
        });
        
        container.appendChild(chip);
    });
}
