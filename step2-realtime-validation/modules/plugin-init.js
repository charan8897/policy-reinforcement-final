/**
 * Plugin Initializer
 * 
 * Auto-initializes FormInputListener + FormStateManager
 * No user interaction required - works as a silent background plugin
 * 
 * Usage:
 *   <script src="form-listener.js"></script>
 *   <script src="form-state-manager.js"></script>
 *   <script src="plugin-init.js"></script>
 */

class FormValidationPlugin {
  /**
   * Initialize plugin with auto-detection of form
   * @param {Object} options - Configuration
   *   - formSelector: CSS selector for form (default: auto-detect)
   *   - expectedFields: Number of expected fields (default: 8)
   *   - autoAttach: Auto-attach listeners (default: true)
   *   - autoSave: Auto-save state (default: true)
   *   - autoSaveDelay: Delay before saving (default: 1000ms)
   *   - debug: Enable console logs (default: false)
   */
  constructor(options = {}) {
    this.options = {
      formSelector: options.formSelector || this.findFormSelector(),
      expectedFields: options.expectedFields || 8,
      autoAttach: options.autoAttach !== false,
      autoSave: options.autoSave !== false,
      autoSaveDelay: options.autoSaveDelay || 1000,
      debug: options.debug || false,
    };

    this.listener = null;
    this.stateManager = null;
    this.isInitialized = false;

    // Auto-initialize on DOM ready
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', () => this.initialize());
    } else {
      this.initialize();
    }
  }

  /**
   * Auto-detect form selector
   * @private
   * @returns {string} CSS selector or null
   */
  findFormSelector() {
    // Look for common form selectors
    const selectors = [
      'form',
      'form[id]',
      'form[name]',
      '[role="form"]',
    ];

    for (const selector of selectors) {
      const form = document.querySelector(selector);
      if (form) {
        return selector;
      }
    }

    return 'form';
  }

  /**
   * Initialize the plugin
   */
  initialize() {
    if (this.isInitialized) {
      return;
    }

    try {
      // Check if required classes exist
      if (typeof FormInputListener === 'undefined') {
        this.log('ERROR', 'FormInputListener not found. Include form-listener.js first.');
        return;
      }

      if (typeof FormStateManager === 'undefined') {
        this.log('ERROR', 'FormStateManager not found. Include form-state-manager.js first.');
        return;
      }

      // Initialize state manager first (loads any existing state)
      this.stateManager = new FormStateManager(
        `policy-form-${this.options.formSelector}`,
        this.options.expectedFields,
        true,
        this.options.autoSave,
        this.options.autoSaveDelay
      );

      this.log('SUCCESS', `State Manager initialized (auto-save: ${this.options.autoSave})`);

      // Initialize listener
      this.listener = new FormInputListener(
        this.options.formSelector,
        this.options.expectedFields
      );

      // Connect listener to state manager
      this.listener.onFieldChange((fieldName, value, allFields) => {
        this.stateManager.updateState(fieldName, value);
      });

      // Auto-attach listeners
      if (this.options.autoAttach) {
        const success = this.listener.attach(true); // silent mode
        if (success) {
          this.log('SUCCESS', `Plugin initialized (${this.listener.getFieldCount()} fields detected)`);
        } else {
          this.log('WARN', 'Form not found. Plugin will wait for dynamic forms.');
          this.setupMutationObserver();
        }
      }

      this.isInitialized = true;
    } catch (error) {
      this.log('ERROR', `Plugin initialization failed: ${error.message}`);
    }
  }

  /**
   * Watch for dynamically added forms
   * @private
   */
  setupMutationObserver() {
    const observer = new MutationObserver((mutations) => {
      if (!this.listener.attached()) {
        const success = this.listener.attach(true);
        if (success) {
          this.log('SUCCESS', 'Dynamic form detected and listeners attached');
          observer.disconnect();
        }
      }
    });

    observer.observe(document.body, {
      childList: true,
      subtree: true,
    });
  }

  /**
   * Log messages (if debug enabled)
   * @private
   */
  log(level, message) {
    if (this.options.debug) {
      console.log(`[PolicyPlugin] [${level}] ${message}`);
    }
  }

  /**
   * Get current state (for external access)
   * @returns {Object} Current form state
   */
  getState() {
    return this.stateManager?.getState() || {};
  }

  /**
   * Manually save state
   */
  save() {
    return this.stateManager?.saveState();
  }

  /**
   * Get storage data (for debugging)
   * @returns {Object|null}
   */
  getStorageData() {
    return this.stateManager?.getStorageData();
  }

  /**
   * Clear storage
   */
  clearStorage() {
    return this.stateManager?.clearState();
  }
}

// Auto-initialize on script load
(function() {
  // Create global plugin instance
  if (typeof window !== 'undefined') {
    window.policyPlugin = new FormValidationPlugin({
      debug: false, // Set to true for console logs
    });
  }
})();

// Export for Node.js/Jest
if (typeof module !== 'undefined' && module.exports) {
  module.exports = FormValidationPlugin;
}
