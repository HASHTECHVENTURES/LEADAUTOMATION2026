/**
 * Production-Grade Frontend Utilities
 * Error handling, retry logic, and user feedback
 */

// Global error handler
window.addEventListener('error', function(e) {
    console.error('Global error:', e.error);
    showUserFriendlyError('An unexpected error occurred. Please refresh the page.');
});

// Unhandled promise rejection handler
window.addEventListener('unhandledrejection', function(e) {
    console.error('Unhandled promise rejection:', e.reason);
    showUserFriendlyError('A network error occurred. Please check your connection and try again.');
});

/**
 * Production-ready fetch with retry logic
 */
async function fetchWithRetry(url, options = {}, maxRetries = 3, retryDelay = 1000) {
    let lastError;
    
    for (let attempt = 1; attempt <= maxRetries; attempt++) {
        try {
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), 30000); // 30 second timeout
            
            const response = await fetch(url, {
                ...options,
                signal: controller.signal
            });
            
            clearTimeout(timeoutId);
            
            if (!response.ok) {
                const errorData = await response.json().catch(() => ({}));
                throw new Error(errorData.error || `HTTP ${response.status}: ${response.statusText}`);
            }
            
            return response;
        } catch (error) {
            lastError = error;
            
            // Don't retry on abort (timeout) or 4xx errors (client errors)
            if (error.name === 'AbortError' || (error.message && error.message.includes('HTTP 4'))) {
                throw error;
            }
            
            // Wait before retrying (exponential backoff)
            if (attempt < maxRetries) {
                const delay = retryDelay * Math.pow(2, attempt - 1);
                await new Promise(resolve => setTimeout(resolve, delay));
            }
        }
    }
    
    throw lastError;
}

/**
 * User-friendly error messages
 */
function showUserFriendlyError(message, duration = 5000) {
    // Remove existing error notifications
    const existing = document.querySelector('.error-notification');
    if (existing) {
        existing.remove();
    }
    
    const errorDiv = document.createElement('div');
    errorDiv.className = 'error-notification';
    errorDiv.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        background: #ef4444;
        color: white;
        padding: 16px 24px;
        border-radius: 12px;
        box-shadow: 0 10px 25px rgba(0,0,0,0.2);
        z-index: 10000;
        max-width: 400px;
        animation: slideInRight 0.3s ease-out;
        display: flex;
        align-items: center;
        gap: 12px;
    `;
    
    errorDiv.innerHTML = `
        <i class="fas fa-exclamation-circle" style="font-size: 1.2em;"></i>
        <div>
            <strong>Error</strong>
            <div style="margin-top: 4px; font-size: 0.9em;">${escapeHtml(message)}</div>
        </div>
        <button onclick="this.parentElement.remove()" style="
            background: none;
            border: none;
            color: white;
            cursor: pointer;
            padding: 4px 8px;
            margin-left: auto;
            opacity: 0.8;
        ">×</button>
    `;
    
    document.body.appendChild(errorDiv);
    
    setTimeout(() => {
        errorDiv.style.animation = 'slideOutRight 0.3s ease-out';
        setTimeout(() => errorDiv.remove(), 300);
    }, duration);
}

/**
 * Success notification
 */
function showSuccess(message, duration = 3000) {
    const existing = document.querySelector('.success-notification');
    if (existing) {
        existing.remove();
    }
    
    const successDiv = document.createElement('div');
    successDiv.className = 'success-notification';
    successDiv.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        background: #10b981;
        color: white;
        padding: 16px 24px;
        border-radius: 12px;
        box-shadow: 0 10px 25px rgba(0,0,0,0.2);
        z-index: 10000;
        max-width: 400px;
        animation: slideInRight 0.3s ease-out;
        display: flex;
        align-items: center;
        gap: 12px;
    `;
    
    successDiv.innerHTML = `
        <i class="fas fa-check-circle" style="font-size: 1.2em;"></i>
        <div>
            <strong>Success</strong>
            <div style="margin-top: 4px; font-size: 0.9em;">${escapeHtml(message)}</div>
        </div>
        <button onclick="this.parentElement.remove()" style="
            background: none;
            border: none;
            color: white;
            cursor: pointer;
            padding: 4px 8px;
            margin-left: auto;
            opacity: 0.8;
        ">×</button>
    `;
    
    document.body.appendChild(successDiv);
    
    setTimeout(() => {
        successDiv.style.animation = 'slideOutRight 0.3s ease-out';
        setTimeout(() => successDiv.remove(), 300);
    }, duration);
}

/**
 * Loading state manager
 */
function setLoadingState(element, isLoading, loadingText = 'Loading...') {
    if (!element) return;
    
    if (isLoading) {
        element.disabled = true;
        element.dataset.originalText = element.innerHTML;
        element.innerHTML = `<i class="fas fa-spinner spinner"></i> ${loadingText}`;
    } else {
        element.disabled = false;
        if (element.dataset.originalText) {
            element.innerHTML = element.dataset.originalText;
            delete element.dataset.originalText;
        }
    }
}

/**
 * Validate project name
 */
function validateProjectName(name) {
    if (!name || name.trim().length === 0) {
        return { valid: false, error: 'Project name is required' };
    }
    
    if (name.length < 3) {
        return { valid: false, error: 'Project name must be at least 3 characters' };
    }
    
    if (name.length > 100) {
        return { valid: false, error: 'Project name must be less than 100 characters' };
    }
    
    if (!/^[a-zA-Z0-9\s\-_]+$/.test(name)) {
        return { valid: false, error: 'Project name can only contain letters, numbers, spaces, hyphens, and underscores' };
    }
    
    return { valid: true };
}

/**
 * Validate PIN code
 */
function validatePinCode(pin) {
    if (!pin || pin.trim().length === 0) {
        return { valid: false, error: 'PIN code is required' };
    }
    
    const pins = pin.split(',').map(p => p.trim()).filter(p => p);
    
    if (pins.length === 0) {
        return { valid: false, error: 'At least one PIN code is required' };
    }
    
    const invalidPins = pins.filter(p => !/^\d{6}$/.test(p));
    
    if (invalidPins.length > 0) {
        return { valid: false, error: `Invalid PIN codes: ${invalidPins.join(', ')}. PIN codes must be 6 digits.` };
    }
    
    return { valid: true };
}

/**
 * Escape HTML to prevent XSS
 */
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text || '';
    return div.innerHTML;
}

/**
 * Debounce function for performance
 */
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

/**
 * Check if user is online
 */
function isOnline() {
    return navigator.onLine;
}

/**
 * Network status monitor
 */
window.addEventListener('online', function() {
    showSuccess('Connection restored', 2000);
});

window.addEventListener('offline', function() {
    showUserFriendlyError('You are offline. Please check your internet connection.', 0);
});

/**
 * Safe JSON parse with error handling
 */
function safeJsonParse(jsonString, defaultValue = null) {
    try {
        return JSON.parse(jsonString);
    } catch (e) {
        console.error('JSON parse error:', e);
        return defaultValue;
    }
}

/**
 * Format error message for user
 */
function formatErrorMessage(error) {
    if (typeof error === 'string') {
        return error;
    }
    
    if (error.message) {
        // User-friendly error messages
        if (error.message.includes('Failed to fetch') || error.message.includes('NetworkError')) {
            return 'Network error. Please check your internet connection and try again.';
        }
        
        if (error.message.includes('timeout') || error.message.includes('aborted')) {
            return 'Request timed out. Please try again.';
        }
        
        if (error.message.includes('HTTP 500')) {
            return 'Server error. Please try again later or contact support.';
        }
        
        if (error.message.includes('HTTP 404')) {
            return 'Resource not found. Please refresh the page.';
        }
        
        if (error.message.includes('HTTP 403') || error.message.includes('HTTP 401')) {
            return 'Access denied. Please log in again.';
        }
        
        return error.message;
    }
    
    return 'An unexpected error occurred. Please try again.';
}

// Add CSS animations
const style = document.createElement('style');
style.textContent = `
    @keyframes slideInRight {
        from {
            transform: translateX(100%);
            opacity: 0;
        }
        to {
            transform: translateX(0);
            opacity: 1;
        }
    }
    
    @keyframes slideOutRight {
        from {
            transform: translateX(0);
            opacity: 1;
        }
        to {
            transform: translateX(100%);
            opacity: 0;
        }
    }
`;
document.head.appendChild(style);

