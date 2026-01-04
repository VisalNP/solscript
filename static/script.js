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
    
    // Flash Animation
    priceElem.classList.remove('flash-green', 'flash-red');
    if (price > previousPrice) priceElem.classList.add('flash-green');
    else if (price < previousPrice) priceElem.classList.add('flash-red');
    else priceElem.style.color = 'var(--text-primary)'; 
    
    previousPrice = price;

    // --- Sentiment ---
    const sentimentElem = document.getElementById('sentiment-val');
    const sentData = data.sentiment;
    sentimentElem.textContent = sentData.description;
    sentimentElem.className = 'metric-value ' + (sentData.score > 0 ? 'text-green' : sentData.score < 0 ? 'text-red' : '');
    document.getElementById('sentiment-sub').textContent = `Score: ${sentData.score}`;

    // --- Regime & Global Warnings ---
    const regimeElem = document.getElementById('regime-val');
    if (data.market_warnings && data.market_warnings.length > 0) {
        regimeElem.innerHTML = `<span class="flash-red" style="font-size:0.9rem">${data.market_warnings[0]}</span>`;
    } else {
        regimeElem.textContent = data.market_regime;
    }
    document.getElementById('volatility-val').textContent = data.volatility;

    // --- Divergence ---
    const divElem = document.getElementById('divergence-val');
    divElem.textContent = data.divergence_status;
    divElem.className = 'metric-value';
    if(data.divergence_status.includes('Bullish')) divElem.classList.add('text-green');
    if(data.divergence_status.includes('Bearish')) divElem.classList.add('text-red');
}

function getConfidenceBadge(level) {
    if (level === 'High') return '<span style="background:#0ecb81; color:#000; padding:2px 6px; border-radius:4px; font-weight:bold; font-size:0.7rem; margin-left:8px;">SAFE</span>';
    if (level === 'Medium') return '<span style="background:#f0b90b; color:#000; padding:2px 6px; border-radius:4px; font-weight:bold; font-size:0.7rem; margin-left:8px;">CAUTION</span>';
    return '<span style="background:#f6465d; color:#fff; padding:2px 6px; border-radius:4px; font-weight:bold; font-size:0.7rem; margin-left:8px;">RISKY</span>';
}

function updateZones(entries, containerId, currentPrice) {
    const container = document.getElementById(containerId);
    
    if (!entries || entries.length === 0) {
        container.innerHTML = '<div class="no-zones">Scanning for levels... No high confluence zones nearby.</div>';
        return;
    }

    let html = '';
    
    entries.forEach(entry => {
        const isLong = currentPrice > entry.price;
        const colorClass = isLong ? 'text-green' : 'text-red';
        const borderColor = isLong ? 'var(--accent-green)' : 'var(--accent-red)';
        const typeLabel = isLong ? 'SUPPORT' : 'RESISTANCE';
        
        const scorePct = Math.min((entry.score / 25) * 100, 100);
        const simplifiedSources = entry.sources.map(s => `<span class="zone-source-tag">${s}</span>`).join('');
        
        const confBadge = getConfidenceBadge(entry.confidence || 'High');

        let warningHtml = '';
        if (entry.warnings && entry.warnings.length > 0) {
            warningHtml = `<div style="margin-top:5px; color:#f6465d; font-size:0.75rem; font-weight:bold; border-top:1px dashed #333; padding-top:5px;">⚠️ ${entry.warnings.join(' + ')}</div>`;
        }
        
        let confirmHtml = '';
        if (entry.confirmations && entry.confirmations.length > 0) {
            confirmHtml = `<div class="confirmation-box">${entry.confirmations.join(' • ')}</div>`;
        }

        html += `
        <div class="zone-card" style="border-left-color: ${borderColor}">
            <div class="zone-header">
                <div>
                    <div class="zone-price ${colorClass}">$${entry.price.toFixed(4)}</div>
                    <div class="zone-type" style="color: ${borderColor}">${typeLabel} ${confBadge}</div>
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
            ${warningHtml}
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