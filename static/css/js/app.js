document.addEventListener('DOMContentLoaded', function () {
    initExplanationPager();
    initManualOverrides();
});

function initExplanationPager() {
    const dataScript = document.getElementById('expl-data');
    if (!dataScript) return;

    const data = JSON.parse(dataScript.textContent || '[]');
    if (!Array.isArray(data) || data.length === 0) return;

    let i = 0;

    const elStu = document.getElementById('expl-stu');
    const elSite = document.getElementById('expl-site');
    const elScore = document.getElementById('expl-score');
    const elPos = document.getElementById('expl-pos');
    const elTBody = document.getElementById('expl-tbody');
    const elTotal = document.getElementById('expl-total');

    function render() {
        const row = data[i];

        elStu.textContent = row.student || '';
        elSite.textContent = row.site || '';
        elScore.textContent = row.score ?? '';
        elPos.textContent = `(${i + 1} מתוך ${data.length})`;

        elTBody.innerHTML = '';

        let sum = 0;

        Object.entries(row.parts || {}).forEach(([key, value]) => {
            const tr = document.createElement('tr');

            const tdKey = document.createElement('td');
            tdKey.textContent = key;

            const tdValue = document.createElement('td');
            tdValue.textContent = value;

            tr.appendChild(tdKey);
            tr.appendChild(tdValue);

            elTBody.appendChild(tr);

            if (typeof value === 'number') {
                sum += value;
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
                    status.classList.add('success');
                }

                setTimeout(() => {
                    window.location.reload();
                }, 700);

            } catch (error) {
                if (status) {
                    status.textContent = error.message;
                    status.classList.add('error');
                }
            } finally {
                button.disabled = false;
                button.textContent = 'עדכן שיבוץ';
            }
        });
    });
}
