function updateData(data) {
    const priceElem = document.getElementById('current-price');
    const sentimentElem = document.getElementById('sentiment');
    const divergenceElem = document.getElementById('divergence');
    const regimeElem = document.getElementById('market-regime');
    const volatilityElem = document.getElementById('volatility');
    const statusFooter = document.getElementById('status-footer');

    let lastPrice = parseFloat(priceElem.dataset.lastPrice) || 0;
    const currentPrice = data.current_price;
    priceElem.textContent = `$${currentPrice.toFixed(4)}`;
    priceElem.className = 'card-value';
    if (currentPrice > lastPrice) priceElem.classList.add('text-green');
    else if (currentPrice < lastPrice) priceElem.classList.add('text-red');
    priceElem.dataset.lastPrice = currentPrice;

    const sentiment = data.sentiment;
    sentimentElem.innerHTML = `${sentiment.description} <span class="card-subtitle">(${sentiment.score})</span>`;
    sentimentElem.className = 'card-value';
    if (sentiment.score > 0) sentimentElem.classList.add('text-green');
    if (sentiment.score < 0) sentimentElem.classList.add('text-red');

    const divergence = data.divergence_status;
    divergenceElem.textContent = divergence;
    divergenceElem.className = 'card-value';
    if (divergence.includes('Bullish')) divergenceElem.classList.add('text-green');
    if (divergence.includes('Bearish')) divergenceElem.classList.add('text-red');
    
    const regime = data.market_regime;
    regimeElem.textContent = regime;
    regimeElem.className = 'card-value';
    if (regime.includes('RANGING')) regimeElem.classList.add('text-green');
    if (regime.includes('TRENDING')) regimeElem.classList.add('text-red');
    volatilityElem.textContent = data.volatility;

    const zonesContainer = document.getElementById('zones-container');
    zonesContainer.innerHTML = ''; 
    data.potential_entries.forEach(entry => {
        const isLong = currentPrice > entry.price;
        const typeClass = isLong ? 'text-green' : 'text-red';
        const borderColor = isLong ? 'var(--green)' : 'var(--red)';
        
        const sources = {'Key Levels': [], 'S/R Zones': [], 'Daily': [], 'Hourly': [], '15m': [], '5m': []};
        entry.sources.forEach(s => {
            if (s.includes('S/R Zone')) sources['S/R Zones'].push(s);
            else if (s.includes('PDL') || s.includes('PDH') || s.includes('PWL') || s.includes('PWH') || s.includes('PML') || s.includes('PMH')) sources['Key Levels'].push(s);
            else if (s.startsWith('1d')) sources['Daily'].push(s.replace('1d ', ''));
            else if (s.startsWith('1h')) sources['Hourly'].push(s.replace('1h ', ''));
            else if (s.startsWith('15m')) sources['15m'].push(s.replace('15m ', ''));
            else if (s.startsWith('5m')) sources['5m'].push(s.replace('5m ', ''));
        });

        let sourcesHtml = '<ul>';
        for (const [category, items] of Object.entries(sources)) {
            if (items.length > 0) {
                sourcesHtml += `<li><strong>${category}:</strong> ${items.join(', ')}</li>`;
            }
        }
        sourcesHtml += '</ul>';

        let confirmationHtml = '';
        if (entry.confirmations && entry.confirmations.length > 0) {
            confirmationHtml = `<div class="confirmation-line">${entry.confirmations.join(' ')}</div>`;
        }

        const zoneCardHtml = `
            <div class="zone-card" style="border-left-color: ${borderColor};">
                <div class="zone-card-header">
                    <div class="metric-group">
                        <div class="zone-metric-value ${typeClass}">$${entry.price.toFixed(4)}</div>
                        <div class="zone-metric-label">${isLong ? 'Support Level' : 'Resistance Level'}</div>
                    </div>
                    <div class="metric-group score-group">
                        <div class="zone-metric-value">${entry.score}</div>
                        <div class="zone-metric-label">Confluence Score</div>
                    </div>
                </div>
                <div class="zone-card-body">
                    ${sourcesHtml}
                </div>
                ${confirmationHtml}
            </div>
        `;
        zonesContainer.innerHTML += zoneCardHtml;
    });

    statusFooter.textContent = data.status;
}

function showTab(tabName) {
    document.querySelectorAll('.tab-content').forEach(content => {
        content.classList.remove('active');
    });
    document.querySelectorAll('.tab-button').forEach(button => {
        button.classList.remove('active');
    });
    document.getElementById(tabName + '-content').classList.add('active');
    document.querySelector(`.tab-button[onclick="showTab('${tabName}')"]`).classList.add('active');
}