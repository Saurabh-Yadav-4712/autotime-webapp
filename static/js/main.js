// Global Theme Toggle Logic (Event Delegation for Turbo safety)
function getCsrfToken() {
    const tokenElement = document.querySelector('meta[name="csrf-token"]');
    return tokenElement ? tokenElement.content : '';
}

function addCsrfTokensToForms() {
    const token = getCsrfToken();
    if (!token) return;

    document.querySelectorAll('form').forEach(form => {
        const method = (form.getAttribute('method') || 'GET').toUpperCase();
        if (method === 'GET' || form.querySelector('input[name="csrf_token"]')) return;

        const input = document.createElement('input');
        input.type = 'hidden';
        input.name = 'csrf_token';
        input.value = token;
        form.appendChild(input);
    });
}

document.addEventListener('DOMContentLoaded', addCsrfTokensToForms);
document.addEventListener('turbo:load', addCsrfTokensToForms);

document.addEventListener('change', function(e) {
    if (e.target && e.target.classList.contains('theme-toggle-input')) {
        const newTheme = e.target.checked ? 'dark' : 'light';
        document.documentElement.setAttribute('data-bs-theme', newTheme);
        localStorage.setItem('autotime_theme', newTheme);

        document.querySelectorAll('.theme-toggle-input').forEach(input => {
            if (input !== e.target) input.checked = e.target.checked;
        });
    }
});

function syncThemeToggle() {
    const savedTheme = localStorage.getItem('autotime_theme') || 'light';
    document.documentElement.setAttribute('data-bs-theme', savedTheme);

    document.querySelectorAll('.theme-toggle-input').forEach(toggleInput => {
        toggleInput.checked = (savedTheme === 'dark');
    });
}

document.addEventListener('DOMContentLoaded', syncThemeToggle);
document.addEventListener('turbo:load', syncThemeToggle);

function initSearchableSelects() {
    if (typeof TomSelect !== 'undefined') {
        document.querySelectorAll('.searchable-select').forEach(el => {
            if (!el.tomselect) {
                new TomSelect(el, {
                    create: false,
                    sortField: {field: "text", direction: "asc"}
                });
            }
        });
    }
}
document.addEventListener('DOMContentLoaded', initSearchableSelects);
document.addEventListener('turbo:load', initSearchableSelects);

// Global Loader Logic
window.addEventListener('turbo:before-visit', () => {
    const loader = document.getElementById('global-loader');
    if (loader) loader.classList.add('active');
});

window.addEventListener('turbo:load', () => {
    const loader = document.getElementById('global-loader');
    if (loader) loader.classList.remove('active');
});

// Button Inline Loader Logic
if (!window.loaderInitialized) {
    window.loaderInitialized = true;

    document.addEventListener('submit', function(e) {
        const form = e.target;
        let submitter = e.submitter || form.querySelector('button[type="submit"], input[type="submit"]');

        if (submitter && !submitter.hasAttribute('data-loading')) {
            if (submitter.tagName.toLowerCase() === 'button') {
                const width = submitter.offsetWidth;
                submitter.style.width = width + 'px';
                submitter.setAttribute('data-original-html', submitter.innerHTML);
                submitter.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span>';
            } else {
                submitter.setAttribute('data-original-value', submitter.value || '');
                submitter.value = '...';
            }
            submitter.classList.add('disabled');
            setTimeout(() => {
                submitter.disabled = true;
            }, 10);
            submitter.setAttribute('data-loading', 'true');
        }
    });

    document.addEventListener('turbo:submit-end', function(e) {
        document.querySelectorAll('[data-loading="true"]').forEach(btn => {
            if (btn.tagName.toLowerCase() === 'button' && btn.hasAttribute('data-original-html')) {
                btn.innerHTML = btn.getAttribute('data-original-html');
            } else if (btn.hasAttribute('data-original-value')) {
                btn.value = btn.getAttribute('data-original-value');
            }
            btn.classList.remove('disabled');
            btn.disabled = false;
            btn.removeAttribute('data-loading');
            btn.style.width = '';
        });
    });
}

// Toast Initialization Logic
function initToasts() {
    var toastElList = [].slice.call(document.querySelectorAll('.toast'));
    var toastList = toastElList.map(function(toastEl) {
        return bootstrap.Toast.getInstance(toastEl) || new bootstrap.Toast(toastEl, { autohide: true, delay: 4000 });
    });
    toastList.forEach(toast => toast.show());
}

document.addEventListener('DOMContentLoaded', initToasts);
document.addEventListener('turbo:load', initToasts);
