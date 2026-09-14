// Small Chart.js factory shared by every chart in the app (win trend, advanced
// stat trends, point differential, ...). Chart.js is already loaded from a CDN
// in index.html -- this just centralizes dark-theme-aware defaults so no chart
// call site has to repeat axis/tooltip styling.
const Charts = (() => {
    if (window.Chart) {
        Chart.defaults.font.family = "'Inter', -apple-system, sans-serif";
        Chart.defaults.color = '#9aa0a8';
        Chart.defaults.borderColor = '#262b33';
    }

    function createLineChart(canvas, { labels, values, color = '#5b8cff', yLabel = '', compact = true }) {
        return new Chart(canvas, {
            type: 'line',
            data: {
                labels,
                datasets: [{
                    data: values,
                    borderColor: color,
                    backgroundColor: color,
                    pointBackgroundColor: color,
                    pointRadius: compact ? 0 : 3,
                    pointHoverRadius: 4,
                    borderWidth: 2,
                    tension: 0.3,
                    fill: false,
                }],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        backgroundColor: '#1c2027',
                        titleColor: '#e8eaed',
                        bodyColor: '#e8eaed',
                        borderColor: '#33393f',
                        borderWidth: 1,
                        padding: 8,
                        displayColors: false,
                    },
                },
                scales: {
                    x: {
                        grid: { display: false },
                        ticks: { maxRotation: 0, autoSkip: true, font: { size: 10 } },
                    },
                    y: {
                        grid: { color: '#1c2027' },
                        title: yLabel ? { display: true, text: yLabel, font: { size: 10 } } : undefined,
                        ticks: { font: { size: 10 } },
                    },
                },
            },
        });
    }

    function rollingAverage(values, window) {
        return values.map((_, i) => {
            const start = Math.max(0, i - window + 1);
            const slice = values.slice(start, i + 1);
            return slice.reduce((sum, v) => sum + v, 0) / slice.length;
        });
    }

    function createScoringTrendChart(canvas, { labels, scored, allowed, rollingWindow = 5 }) {
        const scoredAvg = rollingAverage(scored, rollingWindow);
        const allowedAvg = rollingAverage(allowed, rollingWindow);
        return new Chart(canvas, {
            type: 'line',
            data: {
                labels,
                datasets: [
                    { label: 'Scored', data: scored, borderColor: '#f0a63a', backgroundColor: '#f0a63a', borderWidth: 1.5, pointRadius: 0, tension: 0.25 },
                    { label: `Scored (${rollingWindow}-game avg)`, data: scoredAvg, borderColor: '#f0a63a', borderDash: [5, 3], borderWidth: 2, pointRadius: 0, tension: 0.3 },
                    { label: 'Allowed', data: allowed, borderColor: '#7f9bb8', backgroundColor: '#7f9bb8', borderWidth: 1.5, pointRadius: 0, tension: 0.25 },
                    { label: `Allowed (${rollingWindow}-game avg)`, data: allowedAvg, borderColor: '#7f9bb8', borderDash: [5, 3], borderWidth: 2, pointRadius: 0, tension: 0.3 },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: { mode: 'index', intersect: false },
                plugins: {
                    legend: { display: true, position: 'bottom', labels: { boxWidth: 10, font: { size: 11 }, filter: (item) => !item.text.includes('avg') } },
                    tooltip: { backgroundColor: '#1c2027', titleColor: '#e8eaed', bodyColor: '#e8eaed', borderColor: '#33393f', borderWidth: 1, padding: 8 },
                },
                scales: {
                    x: { grid: { display: false }, ticks: { maxRotation: 0, autoSkip: true, maxTicksLimit: 8, font: { size: 10 } } },
                    y: { grid: { color: '#1c2027' }, ticks: { font: { size: 10 } } },
                },
            },
        });
    }

    function createDiffBarChart(canvas, { labels, values }) {
        const colors = values.map((v) => (v >= 0 ? '#3fb56f' : '#e5626a'));
        return new Chart(canvas, {
            type: 'bar',
            data: {
                labels,
                datasets: [{ data: values, backgroundColor: colors, borderRadius: 2, barPercentage: 0.7 }],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: { backgroundColor: '#1c2027', titleColor: '#e8eaed', bodyColor: '#e8eaed', borderColor: '#33393f', borderWidth: 1, padding: 8 },
                },
                scales: {
                    x: { grid: { display: false }, ticks: { maxRotation: 0, autoSkip: true, maxTicksLimit: 8, font: { size: 10 } } },
                    y: { grid: { color: '#1c2027' }, ticks: { font: { size: 10 } } },
                },
            },
        });
    }

    function createComparisonBarChart(canvas, { labels, seriesA, seriesB }) {
        return new Chart(canvas, {
            type: 'bar',
            data: {
                labels,
                datasets: [
                    { label: seriesA.label, data: seriesA.values, backgroundColor: seriesA.color, borderRadius: 3 },
                    { label: seriesB.label, data: seriesB.values, backgroundColor: seriesB.color, borderRadius: 3 },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: true, position: 'bottom', labels: { boxWidth: 10, font: { size: 11 } } },
                    tooltip: { backgroundColor: '#1c2027', titleColor: '#e8eaed', bodyColor: '#e8eaed', borderColor: '#33393f', borderWidth: 1, padding: 8 },
                },
                scales: {
                    x: { grid: { display: false }, ticks: { font: { size: 11 } } },
                    y: { grid: { color: '#1c2027' }, ticks: { font: { size: 10 } } },
                },
            },
        });
    }

    return { createLineChart, createScoringTrendChart, createDiffBarChart, createComparisonBarChart, rollingAverage };
})();
