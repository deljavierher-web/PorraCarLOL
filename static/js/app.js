/**
 * PorraCarLOL — Main Application JavaScript
 * Handles JWT auth, API calls, toasts, and shared utilities.
 */

// ============================================
// Auth & API Utilities
// ============================================

/**
 * Fetch wrapper that automatically adds JWT Authorization header.
 * Redirects to login on 401/422.
 */
async function apiFetch(url, options = {}) {
    const token = localStorage.getItem('porra_token');

    const headers = {
        'Content-Type': 'application/json',
        ...(options.headers || {}),
    };

    if (token) {
        headers['Authorization'] = `Bearer ${token}`;
    }

    const response = await fetch(url, {
        ...options,
        headers,
    });

    // Handle expired/invalid tokens
    if (response.status === 401 || response.status === 422) {
        localStorage.removeItem('porra_token');
        localStorage.removeItem('porra_user');
        window.location.href = '/';
        throw new Error('Sesión expirada.');
    }

    return response;
}

/**
 * Logout: invalidate token and redirect.
 */
async function handleLogout() {
    try {
        await apiFetch('/api/auth/logout', { method: 'POST' });
    } catch (e) {
        // Ignore errors on logout
    }
    localStorage.removeItem('porra_token');
    localStorage.removeItem('porra_user');
    window.location.href = '/';
}

// ============================================
// Toast Notifications
// ============================================

/**
 * Shows a toast notification.
 * @param {'success'|'error'|'info'} type
 * @param {string} message
 * @param {number} duration - ms before auto-dismiss (default 4000)
 */
function showToast(type, message, duration = 4000) {
    const container = document.getElementById('toast-container');
    if (!container) return;

    const toast = document.createElement('div');
    toast.className = `toast ${type} glass-strong px-5 py-3.5 shadow-2xl animate-toastIn flex items-start gap-3`;

    const icons = {
        success: '✅',
        error: '❌',
        info: 'ℹ️',
    };

    toast.innerHTML = `
        <span class="text-lg flex-shrink-0 mt-0.5">${icons[type] || 'ℹ️'}</span>
        <div class="flex-1 min-w-0">
            <p class="text-sm font-semibold text-white">${message}</p>
        </div>
        <button onclick="dismissToast(this.parentElement)" class="text-zinc-500 hover:text-white transition-colors flex-shrink-0 text-xs mt-0.5">✕</button>
    `;

    container.appendChild(toast);

    // Auto-dismiss
    setTimeout(() => dismissToast(toast), duration);
}

/**
 * Dismisses a toast with animation.
 */
function dismissToast(toastEl) {
    if (!toastEl || !toastEl.parentElement) return;
    toastEl.classList.remove('animate-toastIn');
    toastEl.classList.add('animate-toastOut');
    setTimeout(() => {
        if (toastEl.parentElement) {
            toastEl.parentElement.removeChild(toastEl);
        }
    }, 300);
}

// ============================================
// Utilities
// ============================================

/**
 * Format date to Spanish locale.
 */
function formatDate(isoString) {
    if (!isoString) return '—';
    const date = new Date(isoString);
    return date.toLocaleDateString('es-ES', {
        weekday: 'short',
        day: 'numeric',
        month: 'short',
        hour: '2-digit',
        minute: '2-digit',
    });
}

/**
 * Generate a deterministic color for a username.
 */
function getUserColor(name) {
    const colors = [
        '#84cc16', '#06b6d4', '#f59e0b', '#ef4444',
        '#8b5cf6', '#ec4899', '#14b8a6', '#f97316',
    ];
    let hash = 0;
    for (let i = 0; i < name.length; i++) {
        hash = name.charCodeAt(i) + ((hash << 5) - hash);
    }
    return colors[Math.abs(hash) % colors.length];
}

// ============================================
// Country Flag Emojis
// ============================================

const FLAG_EMOJIS = {
    'México': '🇲🇽', 'Sudáfrica': '🇿🇦', 'Corea del Sur': '🇰🇷',
    'República Checa': '🇨🇿', 'Canadá': '🇨🇦', 'Bosnia y Herzegovina': '🇧🇦',
    'Estados Unidos': '🇺🇸', 'Paraguay': '🇵🇾', 'Haití': '🇭🇹',
    'Escocia': '🏴󠁧󠁢󠁳󠁣󠁴󠁿', 'Australia': '🇦🇺', 'Turquía': '🇹🇷',
    'Brasil': '🇧🇷', 'Marruecos': '🇲🇦', 'Catar': '🇶🇦', 'Suiza': '🇨🇭',
    'Costa de Marfil': '🇨🇮', 'Alemania': '🇩🇪', 'Curazao': '🇨🇼',
    'Países Bajos': '🇳🇱', 'Japón': '🇯🇵', 'Suecia': '🇸🇪',
    'Túnez': '🇹🇳', 'Irán': '🇮🇷', 'Nueva Zelanda': '🇳🇿',
    'España': '🇪🇸', 'Cabo Verde': '🇨🇻', 'Bélgica': '🇧🇪',
    'Egipto': '🇪🇬', 'Arabia Saudí': '🇸🇦', 'Uruguay': '🇺🇾',
    'Francia': '🇫🇷', 'Senegal': '🇸🇳', 'Irak': '🇮🇶',
    'Noruega': '🇳🇴', 'Argentina': '🇦🇷', 'Argelia': '🇩🇿',
    'Austria': '🇦🇹', 'Jordania': '🇯🇴', 'Portugal': '🇵🇹',
    'Rep. Dem. Congo': '🇨🇩', 'Inglaterra': '🏴󠁧󠁢󠁥󠁮󠁧󠁿', 'Croacia': '🇭🇷',
    'Uzbekistán': '🇺🇿', 'Colombia': '🇨🇴', 'Ghana': '🇬🇭',
    'Panamá': '🇵🇦', 'Italia': '🇮🇹', 'Ecuador': '🇪🇨',
};

/**
 * Get flag emoji for a team name. Returns empty string if not found.
 */
function getFlag(teamName) {
    return FLAG_EMOJIS[teamName] || '';
}

/**
 * Returns team name with flag emoji prepended.
 */
function teamWithFlag(teamName) {
    const flag = getFlag(teamName);
    return flag ? `${flag} ${teamName}` : teamName;
}
