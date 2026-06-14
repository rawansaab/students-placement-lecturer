document.addEventListener('DOMContentLoaded', function () {
    initExplanationPager();
    initManualOverrides();
    initCockpitFilters();
});

function initExplanationPager() {
    const dataScript = document.getElementById('expl-data');
    if (!dataScript) return;

    let data = [];

    try {
        data = JSON.parse(dataScript.textContent || '[]');
    } catch (error) {
        console.error('שגיאה בקריאת נתוני הסבר הציון:', error);
        return;
    }

    if (!Array.isArray(data) || data.length === 0) return;

    let i = 0;

    const elStu = document.getElementById('expl-stu');
    const elSite = document.getElementById('expl-site');
    const elScore = document.getElementById('expl-score');
    const elPos = document.getElementById('expl-pos');
    const elTBody = document.getElementById('expl-tbody');
    const elTotal = document.getElementById('expl-total');

    if (!elStu || !elSite || !elScore || !elPos || !elTBody || !elTotal) return;

    function render() {
        const row = data[i] || {};

        elStu.textContent = row.student || '';
        elSite.textContent = row.site || '';
        elScore.textContent = row.score !== undefined && row.score !== null ? row.score : '';
        elPos.textContent = `(${i + 1} מתוך ${data.length})`;

        elTBody.innerHTML = '';

        let sum = 0;
        const parts = row.parts || {};

        Object.entries(parts).forEach(([key, value]) => {
            const tr = document.createElement('tr');

            const tdKey = document.createElement('td');
            tdKey.textContent = key;

            const tdValue = document.createElement('td');
            tdValue.textContent = value;

            tr.appendChild(tdKey);
            tr.appendChild(tdValue);

            elTBody.appendChild(tr);

            const numericValue = Number(value);
            if (!Number.isNaN(numericValue)) {
                sum += numericValue;
            }
        });

        elTotal.textContent = sum;
    }

    function next() {
        i = (i + 1) % data.length;
        render();
    }

    function prev() {
        i = (i - 1 + data.length) % data.length;
        render();
    }

    const nextBtn = document.getElementById('btn-next');
    const prevBtn = document.getElementById('btn-prev');

    if (nextBtn) nextBtn.addEventListener('click', next);
    if (prevBtn) prevBtn.addEventListener('click', prev);

    window.addEventListener('keydown', function (event) {
        if (event.key === 'ArrowRight') next();
        if (event.key === 'ArrowLeft') prev();
    });

    render();
}

function initManualOverrides() {
    document.querySelectorAll('[data-override-button]').forEach(button => {
        button.addEventListener('click', async function () {
            const item = button.closest('.cockpit-item');
            if (!item) return;

            const studentId = button.dataset.studentId;
            const select = item.querySelector('[data-override-select]');
            const status = item.querySelector('[data-override-status]');

            if (!studentId || !select) return;

            const siteName = select.value;

            if (!siteName) {
                if (status) {
                    status.textContent = 'יש לבחור מקום התמחות.';
                    status.className = 'override-status error';
                }
                return;
            }

            const originalText = button.textContent;

            button.disabled = true;
            button.textContent = 'מעדכן...';

            if (status) {
                status.textContent = '';
                status.className = 'override-status';
            }

            try {
                const response = await fetch('/api/override', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        student_id: studentId,
                        site_name: siteName
                    })
                });

                const result = await response.json();

                if (!response.ok || !result.ok) {
                    throw new Error(result.message || 'שגיאה בעדכון השיבוץ.');
                }

                if (status) {
                    status.textContent = result.message || 'השיבוץ עודכן בהצלחה.';
                    status.className = 'override-status success';
                }

                setTimeout(() => {
                    window.location.reload();
                }, 700);

            } catch (error) {
                if (status) {
                    status.textContent = error.message;
                    status.className = 'override-status error';
                }
            } finally {
                button.disabled = false;
                button.textContent = originalText || 'עדכן שיבוץ';
            }
        });
    });
}

function initCockpitFilters() {
    const searchInput = document.getElementById('cockpit-search');
    const filterType = document.getElementById('cockpit-filter-type');
    const clearBtn = document.getElementById('cockpit-clear');
    const countEl = document.getElementById('cockpit-count');
    const items = Array.from(document.querySelectorAll('[data-cockpit-item]'));

    if (!searchInput || !filterType || items.length === 0) return;

    function scoreMatches(score, query) {
        const raw = query.replace('%', '').trim();
        const numberOnly = raw.replace(/[<>=]/g, '').trim();
        const num = Number(numberOnly);

        if (Number.isNaN(num)) {
            return String(score).includes(raw);
        }

        if (raw.startsWith('>=')) return score >= num;
        if (raw.startsWith('<=')) return score <= num;
        if (raw.startsWith('>')) return score > num;
        if (raw.startsWith('<')) return score < num;

        return String(score).includes(String(num));
    }

    function applyFilter() {
        const query = searchInput.value.trim().toLowerCase();
        const type = filterType.value;
        let visible = 0;

        items.forEach(item => {
            const student = (item.dataset.student || '').toLowerCase();
            const site = (item.dataset.site || '').toLowerCase();
            const all = (item.dataset.searchAll || '').toLowerCase();
            const score = Number(item.dataset.score || 0);

            let match = true;

            if (query) {
                if (type === 'student') {
                    match = student.includes(query);
                } else if (type === 'site') {
                    match = site.includes(query);
                } else if (type === 'score') {
                    match = scoreMatches(score, query);
                } else {
                    match = all.includes(query);
                }
            }

            item.classList.toggle('is-hidden', !match);

            if (match) visible += 1;
        });

        if (countEl) {
            countEl.textContent = `מוצגים ${visible} מתוך ${items.length}`;
        }
    }

    searchInput.addEventListener('input', applyFilter);
    filterType.addEventListener('change', applyFilter);

    if (clearBtn) {
        clearBtn.addEventListener('click', function () {
            searchInput.value = '';
            filterType.value = 'all';
            applyFilter();
            searchInput.focus();
        });
    }

    applyFilter();
}
