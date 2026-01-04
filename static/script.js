let previousPrice = 0;

function updateData(data) {
    updateDashboard(data);
    updateZones(data.potential_entries, 'zones-container', data.current_price);
    updateZones(data.scalper_entries, 'scalper-zones-container', data.current_price);
    
    document.getElementById('last-updated').textContent = data.status;
}

function updateDashboard(data) {
    // --- Price ---
    const priceElem = document.getElementById('current-price');
    const price = data.current_price;
    priceElem.textContent = `$${price.toFixed(4)}`;
    
    // Remove old flash classes to restart animation
    priceElem.classList.remove('flash-green', 'flash-red', 'text-green', 'text-red');
    
    // Logic for color & flash
    if (price > previousPrice) {
        priceElem.classList.add('flash-green');
    } else if (price < previousPrice) {
        priceElem.classList.add('flash-red');
    } else {
        // Maintain color state if unchanged, default to white/primary
        priceElem.style.color = 'var(--text-primary)'; 
    }
    previousPrice = price;

    // --- Sentiment ---
    const sentimentElem = document.getElementById('sentiment-val');
    const sentimentSub = document.getElementById('sentiment-sub');
    const sentData = data.sentiment;
    sentimentElem.textContent = sentData.description;
    sentimentElem.className = 'metric-value ' + (sentData.score > 0 ? 'text-green' : sentData.score < 0 ? 'text-red' : '');
    sentimentSub.textContent = `Score: ${sentData.score}`;

    // --- Regime ---
    document.getElementById('regime-val').textContent = data.market_regime;
    document.getElementById('volatility-val').textContent = data.volatility;

    // --- Divergence ---
    const divElem = document.getElementById('divergence-val');
    divElem.textContent = data.divergence_status;
    divElem.className = 'metric-value'; // Reset
    if(data.divergence_status.includes('Bullish')) divElem.classList.add('text-green');
    if(data.divergence_status.includes('Bearish')) divElem.classList.add('text-red');
}

function updateZones(entries, containerId, currentPrice) {
    const container = document.getElementById(containerId);
    
    if (entries.length === 0) {
        container.innerHTML = '<div class="no-zones">Scanning for levels... No high confluence zones nearby.</div>';
        return;
    }

    // We rebuild the HTML string. 
    // Optimization: In a larger app, we would diff the DOM, but for <50 items, innerHTML is fine.
    let html = '';
    
    entries.forEach(entry => {
        const isLong = currentPrice > entry.price;
        const colorClass = isLong ? 'text-green' : 'text-red';
        const borderColor = isLong ? 'var(--accent-green)' : 'var(--accent-red)';
        const typeLabel = isLong ? 'SUPPORT' : 'RESISTANCE';
        
        // Calculate Bar Width (Max score assumed ~25 for visual scaling)
        const scorePct = Math.min((entry.score / 25) * 100, 100);

        // Group sources
        const simplifiedSources = entry.sources.map(s => `<span class="zone-source-tag">${s}</span>`).join('');
        
        // Confirmations
        let confirmHtml = '';
        if (entry.confirmations && entry.confirmations.length > 0) {
            confirmHtml = `<div class="confirmation-box">${entry.confirmations.join(' • ')}</div>`;
        }

        html += `
        <div class="zone-card" style="border-left-color: ${borderColor}">
            <div class="zone-header">
                <div>
                    <div class="zone-price ${colorClass}">$${entry.price.toFixed(4)}</div>
                    <div class="zone-type" style="color: ${borderColor}">${typeLabel}</div>
                </div>
                <div class="confluence-container">
                    <div class="score-badge">${entry.score}</div>
                    <div class="score-bar-bg">
                        <div class="score-bar-fill" style="width: ${scorePct}%; background-color: ${borderColor}"></div>
                    </div>
                </div>
            </div>
            <div class="zone-details">
                ${simplifiedSources}
            </div>
            ${confirmHtml}
        </div>`;
    });

    container.innerHTML = html;
}

function showTab(tabName) {
    document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
    document.querySelectorAll('.tab-button').forEach(b => b.classList.remove('active'));
    
    document.getElementById(tabName + '-content').classList.add('active');
    document.querySelector(`button[onclick="showTab('${tabName}')"]`).classList.add('active');
}