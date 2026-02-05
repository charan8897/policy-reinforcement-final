/**
 * Module 6: UI Enforcer - Suggestion Popup
 * 
 * Shows Gemini validation suggestions in a centered popup
 * Auto-dismisses after timeout
 * 
 * Usage:
 *   const popup = new SuggestionPopup();
 *   popup.show({
 *     fieldName: 'email',
 *     status: 'valid',
 *     message: '✓ Valid email format',
 *     suggestion: 'Consider adding a verification step'
 *   });
 */

class SuggestionPopup {
  constructor(options = {}) {
    this.duration = options.duration || 5000; // 5 seconds
    this.maxWidth = options.maxWidth || 500;
    this.autoClose = options.autoClose !== false;
    this.position = options.position || 'center'; // center, top, bottom
    
    this.currentPopup = null;
    this.dismissTimeout = null;

    this.createStyles();
  }

  /**
   * Create and inject CSS styles
   * @private
   */
  createStyles() {
    if (document.getElementById('suggestion-popup-styles')) {
      return; // Already injected
    }

    const style = document.createElement('style');
    style.id = 'suggestion-popup-styles';
    style.textContent = `
      .suggestion-popup-overlay {
        position: fixed;
        top: 0;
        left: 0;
        right: 0;
        bottom: 0;
        background: rgba(0, 0, 0, 0.5);
        display: flex;
        align-items: center;
        justify-content: center;
        z-index: 10000;
        animation: fadeIn 0.3s ease;
      }

      @keyframes fadeIn {
        from {
          opacity: 0;
          transform: scale(0.95);
        }
        to {
          opacity: 1;
          transform: scale(1);
        }
      }

      @keyframes slideOut {
        from {
          opacity: 1;
          transform: translateY(0);
        }
        to {
          opacity: 0;
          transform: translateY(-20px);
        }
      }

      .suggestion-popup-overlay.closing {
        animation: slideOut 0.3s ease forwards;
      }

      .suggestion-popup {
        background: white;
        border-radius: 12px;
        box-shadow: 0 10px 40px rgba(0, 0, 0, 0.3);
        max-width: 500px;
        width: 90%;
        max-height: 80vh;
        overflow-y: auto;
        animation: popupIn 0.3s ease;
      }

      @keyframes popupIn {
        from {
          opacity: 0;
          transform: translateY(-20px);
        }
        to {
          opacity: 1;
          transform: translateY(0);
        }
      }

      .suggestion-popup-header {
        padding: 20px;
        border-bottom: 2px solid #f0f0f0;
        display: flex;
        justify-content: space-between;
        align-items: center;
      }

      .suggestion-popup-header h3 {
        margin: 0;
        font-size: 16px;
        color: #333;
        font-weight: 600;
      }

      .suggestion-popup-close {
        background: none;
        border: none;
        font-size: 20px;
        cursor: pointer;
        color: #999;
        padding: 0;
        width: 24px;
        height: 24px;
        display: flex;
        align-items: center;
        justify-content: center;
        transition: color 0.2s;
      }

      .suggestion-popup-close:hover {
        color: #333;
      }

      .suggestion-popup-body {
        padding: 20px;
      }

      .suggestion-item {
        margin-bottom: 15px;
        padding: 12px;
        border-radius: 6px;
        border-left: 4px solid #667eea;
      }

      .suggestion-item.valid {
        background: #f0fdf4;
        border-left-color: #22c55e;
      }

      .suggestion-item.warning {
        background: #fffbeb;
        border-left-color: #f59e0b;
      }

      .suggestion-item.error {
        background: #fef2f2;
        border-left-color: #ef4444;
      }

      .suggestion-item.info {
        background: #f0f7ff;
        border-left-color: #667eea;
      }

      .suggestion-label {
        font-weight: 600;
        margin-bottom: 6px;
        font-size: 13px;
      }

      .suggestion-label.valid {
        color: #22c55e;
      }

      .suggestion-label.warning {
        color: #f59e0b;
      }

      .suggestion-label.error {
        color: #ef4444;
      }

      .suggestion-label.info {
        color: #667eea;
      }

      .suggestion-field-name {
        font-family: 'Courier New', monospace;
        font-size: 12px;
        color: #666;
        background: rgba(0, 0, 0, 0.05);
        padding: 2px 6px;
        border-radius: 3px;
        display: inline-block;
      }

      .suggestion-value {
        font-family: 'Courier New', monospace;
        font-size: 12px;
        color: #333;
        background: rgba(0, 0, 0, 0.03);
        padding: 8px;
        border-radius: 4px;
        margin: 8px 0;
        word-break: break-all;
      }

      .suggestion-message {
        font-size: 13px;
        color: #333;
        line-height: 1.5;
        margin-bottom: 8px;
      }

      .suggestion-advice {
        font-size: 12px;
        color: #666;
        line-height: 1.5;
        font-style: italic;
      }

      .suggestion-timestamp {
        font-size: 11px;
        color: #999;
        margin-top: 10px;
      }

      .suggestion-popup-footer {
        padding: 15px 20px;
        border-top: 1px solid #f0f0f0;
        display: flex;
        gap: 10px;
        justify-content: flex-end;
      }

      .suggestion-btn {
        padding: 8px 16px;
        border: none;
        border-radius: 6px;
        font-size: 12px;
        font-weight: 600;
        cursor: pointer;
        transition: all 0.2s;
      }

      .suggestion-btn-dismiss {
        background: #e0e0e0;
        color: #333;
      }

      .suggestion-btn-dismiss:hover {
        background: #d0d0d0;
      }

      .suggestion-progress {
        position: absolute;
        bottom: 0;
        left: 0;
        right: 0;
        height: 3px;
        background: #667eea;
        border-radius: 0 0 12px 12px;
        animation: shrink linear;
      }

      @keyframes shrink {
        from {
          width: 100%;
        }
        to {
          width: 0%;
        }
      }
    `;

    document.head.appendChild(style);
  }

  /**
   * Show suggestion popup
   * @param {Object} data - Suggestion data
   *   - fieldName: Field name
   *   - fieldValue: Field value (optional)
   *   - status: 'valid', 'warning', 'error', 'info'
   *   - message: Main message from Gemini
   *   - suggestion: Additional suggestion
   *   - timestamp: When validation occurred
   */
  show(data) {
    // Close existing popup
    if (this.currentPopup) {
      this.dismiss();
    }

    // Create overlay
    const overlay = document.createElement('div');
    overlay.className = 'suggestion-popup-overlay';

    // Create popup
    const popup = document.createElement('div');
    popup.className = 'suggestion-popup';

    // Create header
    const header = document.createElement('div');
    header.className = 'suggestion-popup-header';

    const title = document.createElement('h3');
    title.textContent = `Validation: ${data.fieldName}`;
    header.appendChild(title);

    const closeBtn = document.createElement('button');
    closeBtn.className = 'suggestion-popup-close';
    closeBtn.textContent = '✕';
    closeBtn.onclick = () => this.dismiss();
    header.appendChild(closeBtn);

    popup.appendChild(header);

    // Create body
    const body = document.createElement('div');
    body.className = 'suggestion-popup-body';

    // Suggestion item
    const item = document.createElement('div');
    item.className = `suggestion-item ${data.status || 'info'}`;

    // Status label
    const label = document.createElement('div');
    label.className = `suggestion-label ${data.status || 'info'}`;
    const statusEmoji = {
      valid: '✓',
      warning: '⚠',
      error: '✗',
      info: 'ℹ',
    }[data.status] || '◆';
    label.textContent = `${statusEmoji} ${this.capitalize(data.status || 'info')}`;
    item.appendChild(label);

    // Field value
    if (data.fieldValue !== undefined) {
      const valueDiv = document.createElement('div');
      valueDiv.className = 'suggestion-value';
      valueDiv.textContent = data.fieldValue || '(empty)';
      item.appendChild(valueDiv);
    }

    // Main message
    if (data.message) {
      const msg = document.createElement('div');
      msg.className = 'suggestion-message';
      msg.textContent = data.message;
      item.appendChild(msg);
    }

    // Suggestion/advice
    if (data.suggestion) {
      const advice = document.createElement('div');
      advice.className = 'suggestion-advice';
      advice.textContent = data.suggestion;
      item.appendChild(advice);
    }

    // Timestamp
    const ts = document.createElement('div');
    ts.className = 'suggestion-timestamp';
    ts.textContent = data.timestamp || new Date().toLocaleTimeString();
    item.appendChild(ts);

    body.appendChild(item);
    popup.appendChild(body);

    // Create footer
    const footer = document.createElement('div');
    footer.className = 'suggestion-popup-footer';

    const dismissBtn = document.createElement('button');
    dismissBtn.className = 'suggestion-btn suggestion-btn-dismiss';
    dismissBtn.textContent = 'Dismiss';
    dismissBtn.onclick = () => this.dismiss();
    footer.appendChild(dismissBtn);

    popup.appendChild(footer);

    // Create progress bar
    const progress = document.createElement('div');
    progress.className = 'suggestion-progress';
    progress.style.animation = `shrink ${this.duration}ms linear forwards`;
    popup.appendChild(progress);

    // Append to overlay and DOM
    overlay.appendChild(popup);
    document.body.appendChild(overlay);

    this.currentPopup = overlay;

    // Auto-close
    if (this.autoClose) {
      this.dismissTimeout = setTimeout(() => this.dismiss(), this.duration);
    }
  }

  /**
   * Dismiss the popup
   */
  dismiss() {
    if (!this.currentPopup) return;

    clearTimeout(this.dismissTimeout);

    this.currentPopup.classList.add('closing');

    setTimeout(() => {
      if (this.currentPopup && this.currentPopup.parentNode) {
        this.currentPopup.parentNode.removeChild(this.currentPopup);
      }
      this.currentPopup = null;
    }, 300);
  }

  /**
   * Capitalize string
   * @private
   */
  capitalize(str) {
    return str.charAt(0).toUpperCase() + str.slice(1);
  }
}

// Export for Node.js/Jest
if (typeof module !== 'undefined' && module.exports) {
  module.exports = SuggestionPopup;
}
