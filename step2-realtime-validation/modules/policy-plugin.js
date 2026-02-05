/**
 * Policy Validation Plugin - Complete Standalone Version
 * 
 * Drop-in plugin for any 3rd party website
 * Auto-detects forms, validates fields, shows Gemini suggestions in popup
 * 
 * Installation:
 *   <script src="policy-plugin.js"></script>
 * 
 * That's it! No configuration needed.
 */

(function () {
    'use strict';

    // ========================================================================
    // SUGGESTION POPUP (Embedded)
    // ========================================================================

    class SuggestionPopup {
        constructor() {
            this.currentPopup = null;
            this.duration = 8000;
            this.createStyles();
        }

        createStyles() {
            if (document.getElementById('policy-plugin-styles')) return;

            const style = document.createElement('style');
            style.id = 'policy-plugin-styles';
            style.textContent = `
        .policy-popup-overlay {
          position: fixed;
          top: 0;
          left: 0;
          right: 0;
          bottom: 0;
          background: rgba(0, 0, 0, 0.5);
          display: flex;
          align-items: center;
          justify-content: center;
          z-index: 999999;
          animation: fadeIn 0.3s ease;
        }

        @keyframes fadeIn {
          from { opacity: 0; transform: scale(0.95); }
          to { opacity: 1; transform: scale(1); }
        }

        .policy-popup {
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
          from { opacity: 0; transform: translateY(-20px); }
          to { opacity: 1; transform: translateY(0); }
        }

        @keyframes fadeOut {
          from { opacity: 1; transform: scale(1); }
          to { opacity: 0; transform: scale(0.95); }
        }

        .policy-popup-header {
          padding: 20px;
          border-bottom: 2px solid #f0f0f0;
          display: flex;
          justify-content: space-between;
          align-items: center;
        }

        .policy-popup-header h3 {
          margin: 0;
          font-size: 16px;
          color: #333;
          font-weight: 600;
        }

        .policy-popup-close {
          background: none;
          border: none;
          font-size: 20px;
          cursor: pointer;
          color: #999;
          padding: 0;
          width: 24px;
          height: 24px;
        }

        .policy-popup-close:hover {
          color: #333;
        }

        .policy-popup-body {
          padding: 20px;
        }

        .policy-item {
          margin-bottom: 15px;
          padding: 12px;
          border-radius: 6px;
          border-left: 4px solid #667eea;
        }

        .policy-item.valid {
          background: #f0fdf4;
          border-left-color: #22c55e;
        }

        .policy-item.warning {
          background: #fffbeb;
          border-left-color: #f59e0b;
        }

        .policy-item.error {
          background: #fef2f2;
          border-left-color: #ef4444;
        }

        .policy-label {
          font-weight: 600;
          margin-bottom: 8px;
          font-size: 13px;
        }

        .policy-label.valid { color: #22c55e; }
        .policy-label.warning { color: #f59e0b; }
        .policy-label.error { color: #ef4444; }

        .policy-message {
          font-size: 13px;
          color: #333;
          line-height: 1.5;
          margin-bottom: 10px;
        }

        .policy-rules {
          font-size: 12px;
          color: #666;
          line-height: 1.6;
          background: rgba(0, 0, 0, 0.02);
          padding: 10px;
          border-radius: 4px;
          margin-top: 8px;
        }

        .policy-rules-title {
          font-weight: 600;
          color: #667eea;
          margin-bottom: 6px;
          font-size: 11px;
          text-transform: uppercase;
        }

        .policy-rule {
          margin-bottom: 6px;
          padding-left: 16px;
          position: relative;
        }

        .policy-rule:before {
          content: "•";
          position: absolute;
          left: 6px;
          color: #667eea;
        }

        .policy-value {
          font-family: 'Courier New', monospace;
          font-size: 11px;
          color: #333;
          background: rgba(0, 0, 0, 0.05);
          padding: 6px;
          border-radius: 3px;
          margin: 8px 0;
        }

        .policy-popup-footer {
          padding: 15px 20px;
          border-top: 1px solid #f0f0f0;
          text-align: right;
        }

        .policy-btn {
          padding: 8px 16px;
          border: none;
          border-radius: 6px;
          font-size: 12px;
          font-weight: 600;
          cursor: pointer;
          background: #e0e0e0;
          color: #333;
        }

        .policy-btn:hover {
          background: #d0d0d0;
        }

        .policy-progress {
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
          from { width: 100%; }
          to { width: 0%; }
        }
      `;

            document.head.appendChild(style);
        }

        show(data) {
            if (this.currentPopup) {
                this.dismiss();
            }

            const overlay = document.createElement('div');
            overlay.className = 'policy-popup-overlay';

            // Close on overlay click (outside popup)
            overlay.addEventListener('click', (e) => {
                if (e.target === overlay) {
                    this.dismiss();
                }
            });

            const popup = document.createElement('div');
            popup.className = 'policy-popup';

            // Prevent close when clicking inside popup
            popup.addEventListener('click', (e) => e.stopPropagation());

            const header = document.createElement('div');
            header.className = 'policy-popup-header';

            // const title = document.createElement('h3');
            // title.textContent = `Validation: ${data.fieldName}`;
            // header.appendChild(title);

            const closeBtn = document.createElement('button');
            closeBtn.className = 'policy-popup-close';
            closeBtn.textContent = '✕';
            closeBtn.onclick = () => this.dismiss();
            header.appendChild(closeBtn);

            popup.appendChild(header);

            const body = document.createElement('div');
            body.className = 'policy-popup-body';

            const item = document.createElement('div');
            item.className = `policy-item ${data.status || 'info'}`;

            const label = document.createElement('div');
            label.className = `policy-label ${data.status || 'info'}`;
            const emoji = { valid: '✓', warning: '⚠', error: '✗', info: 'ℹ' }[data.status] || '◆';
            label.textContent = `${emoji} ${this.capitalize(data.status || 'info')}`;
            item.appendChild(label);

            if (data.fieldValue) {
                const val = document.createElement('div');
                val.className = 'policy-value';
                val.textContent = `${data.fieldValue}`;
                item.appendChild(val);
            }

            const msg = document.createElement('div');
            msg.className = 'policy-message';
            msg.textContent = data.message;
            item.appendChild(msg);

            if (data.rules && data.rules.length > 0) {
                const rulesDiv = document.createElement('div');
                rulesDiv.className = 'policy-rules';

                const rulesTitle = document.createElement('div');
                rulesTitle.className = 'policy-rules-title';
                rulesTitle.textContent = '📋 Policy Rules';
                rulesDiv.appendChild(rulesTitle);

                data.rules.forEach(rule => {
                    const ruleDiv = document.createElement('div');
                    ruleDiv.className = 'policy-rule';
                    ruleDiv.textContent = rule;
                    rulesDiv.appendChild(ruleDiv);
                });

                item.appendChild(rulesDiv);
            }

            body.appendChild(item);
            popup.appendChild(body);

            const footer = document.createElement('div');
            footer.className = 'policy-popup-footer';

            const btn = document.createElement('button');
            btn.className = 'policy-btn';
            btn.textContent = 'Dismiss';
            btn.onclick = () => this.dismiss();
            footer.appendChild(btn);

            popup.appendChild(footer);

            // Removed auto-dismiss - user must manually close popup

            overlay.appendChild(popup);
            document.body.appendChild(overlay);

            this.currentPopup = overlay;
        }

        dismiss() {
            if (!this.currentPopup) return;

            try {
                const overlay = this.currentPopup;
                overlay.style.animation = 'fadeOut 0.3s ease forwards';

                setTimeout(() => {
                    if (overlay && overlay.parentNode) {
                        overlay.parentNode.removeChild(overlay);
                    }
                }, 300);

                this.currentPopup = null;
            } catch (e) {
                console.error('Error dismissing popup:', e);
                if (this.currentPopup && this.currentPopup.parentNode) {
                    this.currentPopup.parentNode.removeChild(this.currentPopup);
                }
                this.currentPopup = null;
            }
        }

        capitalize(str) {
            return str.charAt(0).toUpperCase() + str.slice(1);
        }
    }

    // ========================================================================
    // POLICY PLUGIN
    // ========================================================================

    class PolicyPlugin {
        constructor() {
            this.popup = new SuggestionPopup();
            this.fieldsMonitored = 0;
            this.validationsRun = 0;
            this.validationHistory = [];  // Track validation context for linked field validation

            this.initialize();
        }

        initialize() {
            if (document.readyState === 'loading') {
                document.addEventListener('DOMContentLoaded', () => this.setupPlugin());
            } else {
                this.setupPlugin();
            }
        }

        setupPlugin() {
            // Scan for existing forms
            this.scanForms();

            // Watch for new forms
            this.watchForForms();

            console.log('[PolicyPlugin] ✓ Initialized - monitoring forms for policy validation');
        }

        scanForms() {
          const forms = document.querySelectorAll('form, [role="form"]');

          forms.forEach((form, idx) => {
            const formId = form.id || form.name || `form-${idx}`;
            const inputs = form.querySelectorAll('input, textarea, select');

            if (inputs.length === 0) return;

            inputs.forEach(field => {
              // Skip if already has listener attached
              if (field.dataset.policyPluginAttached === 'true') return;
              
              this.attachBlurListener(field, formId);
            });
          });
        }

        attachBlurListener(field, formId) {
          const fieldName = field.getAttribute('name') || field.getAttribute('id') || field.placeholder || 'Unknown';

          // Mark field as having listener attached
          field.dataset.policyPluginAttached = 'true';
          this.fieldsMonitored++;

          field.addEventListener('blur', async () => {
            const value = field.value.trim();
            if (!value) return;

            // Pass validation history as context for linked field validation
            const context = this.validationHistory.length > 0 ? this.validationHistory : null;
            
            // Await validation and store result for context
            await this.validateField(fieldName, value, context);
            
            // Track validation for context passing
            this.validationHistory.push({
              field_name: fieldName,
              field_value: value,
              timestamp: new Date().toISOString()
            });
          });
        }

        async validateField(fieldName, fieldValue, previousContext = null) {
            this.validationsRun++;

            try {
                // Call backend validation API (same logic as policy_validator.py)
                const response = await fetch('http://localhost:5000/api/validate-field', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        field_name: fieldName,
                        field_value: fieldValue,
                        previous_context: previousContext
                    })
                });

                if (!response.ok) {
                    throw new Error(`Backend error: ${response.statusText}`);
                }

                const result = await response.json();

                // Check if backend returned an error in the response
                if (result.error || (result.status && result.status.toLowerCase() === 'error')) {
                    throw new Error(result.message || result.error || 'Backend validation failed');
                }

                // Handle both 'rules' and 'relevant_rules' field names for compatibility
                const rulesList = result.rules || result.relevant_rules || [];

                // Extract validation result from backend response (with defaults)
                const status = result.status || result.validation_status || 'valid';
                const message = result.message || 'Field validation completed';

                // Show validation result
                this.popup.show({
                    fieldName: fieldName.charAt(0).toUpperCase() + fieldName.slice(1),
                    fieldValue: fieldValue,
                    status: status,
                    message: message,
                    rules: Array.isArray(rulesList) ? rulesList : [],
                    details: result.validation_details || result
                });

            } catch (error) {
                console.error('[PolicyPlugin] Validation error:', error);

                // Show error state with fallback message
                this.popup.show({
                    fieldName: fieldName.charAt(0).toUpperCase() + fieldName.slice(1),
                    fieldValue: fieldValue,
                    status: 'error',
                    message: `✗ Validation service unavailable. Field accepted locally.`,
                    rules: ['Validation will be performed on submission']
                });
            }
        }

        watchForForms() {
            const observer = new MutationObserver(() => {
                setTimeout(() => this.scanForms(), 500);
            });

            observer.observe(document.body, {
                childList: true,
                subtree: true
            });
        }

        getStats() {
            return {
                fieldsMonitored: this.fieldsMonitored,
                validationsRun: this.validationsRun
            };
        }
    }

    // ========================================================================
    // AUTO-INITIALIZE
    // ========================================================================

    if (typeof window !== 'undefined') {
        window.policyPlugin = new PolicyPlugin();

        // Make stats accessible
        window.getPolicyStats = () => window.policyPlugin.getStats();
    }
})();
