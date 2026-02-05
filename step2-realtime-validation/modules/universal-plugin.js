/**
 * Universal Form Plugin
 * 
 * Works on ANY platform:
 * - Standard HTML forms
 * - React, Vue, Angular apps
 * - Dynamic forms loaded after page
 * - Complex nested structures
 * - Multiple forms on same page
 * 
 * Auto-initializes globally without configuration
 */

class UniversalFormPlugin {
  constructor() {
    this.plugins = new Map(); // formId -> plugin instance
    this.observer = null;
    this.initialized = false;

    // Auto-initialize on DOM ready
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', () => this.initialize());
    } else {
      this.initialize();
    }
  }

  /**
   * Initialize plugin - scan page for all forms
   */
  initialize() {
    if (this.initialized) return;

    try {
      // Scan for existing forms
      this.scanForForms();

      // Watch for new forms added dynamically
      this.watchForNewForms();

      this.initialized = true;
      this.log('Plugin initialized (universal mode)');
    } catch (error) {
      this.log(`Initialization failed: ${error.message}`, 'error');
    }
  }

  /**
   * Scan page for all forms and initialize plugins
   */
  scanForForms() {
    const forms = document.querySelectorAll('form, [role="form"], [data-form]');

    forms.forEach((form, index) => {
      const formId = form.id || form.name || `auto-form-${index}`;

      // Skip if already initialized
      if (this.plugins.has(formId)) {
        return;
      }

      // Count potential input fields
      const inputCount = this.countInputFields(form);

      if (inputCount === 0) {
        return; // No input fields, skip
      }

      // Create plugin for this form
      this.createPluginForForm(form, formId, inputCount);
    });
  }

  /**
   * Count input fields in a form
   * @param {HTMLElement} form
   * @returns {number}
   */
  countInputFields(form) {
    const selector = `
      input[type="text"],
      input[type="email"],
      input[type="number"],
      input[type="tel"],
      input[type="date"],
      input[type="password"],
      input[type="search"],
      input[type="url"],
      textarea,
      select,
      [contenteditable="true"],
      [role="textbox"],
      [role="combobox"],
      input:not([type])
    `;

    return form.querySelectorAll(selector).length;
  }

  /**
   * Create and initialize plugin for a specific form
   * @param {HTMLElement} form
   * @param {string} formId
   * @param {number} fieldCount
   */
  createPluginForForm(form, formId, fieldCount) {
    try {
      // Check if classes exist
      if (typeof FormInputListener === 'undefined' || typeof FormStateManager === 'undefined') {
        return;
      }

      // Create selector (by ID first, then fallback to form element itself)
      const selector = form.id ? `#${form.id}` : form;

      // Initialize state manager
      const stateManager = new FormStateManager(
        `universal-${formId}`,
        fieldCount,
        true,
        true,
        1000 // auto-save after 1 second
      );

      // Initialize listener
      const listener = new FormInputListener(selector, fieldCount);

      // Connect listener to state manager
      listener.onFieldChange((fieldName, value) => {
        stateManager.updateState(fieldName, value);
      });

      // Attach listeners silently
      const success = listener.attach(true);

      if (success) {
        this.plugins.set(formId, {
          form,
          formId,
          listener,
          stateManager,
          fieldCount,
        });

        this.log(`Form '${formId}' initialized (${fieldCount} fields)`);
      }
    } catch (error) {
      this.log(`Failed to initialize form '${formId}': ${error.message}`, 'error');
    }
  }

  /**
   * Watch for dynamically added forms
   */
  watchForNewForms() {
    this.observer = new MutationObserver((mutations) => {
      let foundNewForm = false;

      mutations.forEach((mutation) => {
        if (mutation.addedNodes.length) {
          mutation.addedNodes.forEach((node) => {
            if (node.nodeType === Node.ELEMENT_NODE) {
              // Check if added node is a form
              if (node.matches && (node.matches('form') || node.matches('[role="form"]'))) {
                foundNewForm = true;
              }
              // Check if added node contains forms
              if (node.querySelectorAll && node.querySelectorAll('form').length) {
                foundNewForm = true;
              }
            }
          });
        }
      });

      if (foundNewForm) {
        // Debounce form scanning
        clearTimeout(this.scanTimeout);
        this.scanTimeout = setTimeout(() => this.scanForForms(), 500);
      }
    });

    this.observer.observe(document.body, {
      childList: true,
      subtree: true,
    });
  }

  /**
   * Get all active plugins
   * @returns {Array}
   */
  getAllPlugins() {
    return Array.from(this.plugins.values());
  }

  /**
   * Get state for a specific form
   * @param {string} formId
   * @returns {Object}
   */
  getFormState(formId) {
    const plugin = this.plugins.get(formId);
    return plugin?.stateManager?.getState() || null;
  }

  /**
   * Get all states from all forms
   * @returns {Object}
   */
  getAllStates() {
    const allStates = {};
    this.plugins.forEach((plugin, formId) => {
      allStates[formId] = plugin.stateManager.getState();
    });
    return allStates;
  }

  /**
   * Get storage data for a form
   * @param {string} formId
   * @returns {Object|null}
   */
  getFormStorageData(formId) {
    const plugin = this.plugins.get(formId);
    return plugin?.stateManager?.getStorageData() || null;
  }

  /**
   * Save a specific form
   * @param {string} formId
   */
  saveForm(formId) {
    const plugin = this.plugins.get(formId);
    if (plugin) {
      return plugin.stateManager.saveState();
    }
    return false;
  }

  /**
   * Save all forms
   */
  saveAll() {
    let savedCount = 0;
    this.plugins.forEach((plugin) => {
      if (plugin.stateManager.saveState()) {
        savedCount++;
      }
    });
    return savedCount;
  }

  /**
   * Clear storage for a form
   * @param {string} formId
   */
  clearForm(formId) {
    const plugin = this.plugins.get(formId);
    if (plugin) {
      plugin.stateManager.clearState();
    }
  }

  /**
   * Clear all stored data
   */
  clearAll() {
    this.plugins.forEach((plugin) => {
      plugin.stateManager.clearState();
    });
  }

  /**
   * Get plugin stats
   * @returns {Object}
   */
  getStats() {
    return {
      pluginCount: this.plugins.size,
      totalFields: Array.from(this.plugins.values()).reduce(
        (sum, p) => sum + p.fieldCount,
        0
      ),
      plugins: Array.from(this.plugins.values()).map((p) => ({
        formId: p.formId,
        fieldCount: p.fieldCount,
        hasStoredData: p.stateManager.hasStoredState(),
      })),
    };
  }

  /**
   * Internal logging
   * @private
   */
  log(message, level = 'info') {
    if (typeof console !== 'undefined' && console[level]) {
      console[level](`[UniversalPlugin] ${message}`);
    }
  }
}

// Auto-initialize globally
if (typeof window !== 'undefined') {
  window.universalPlugin = new UniversalFormPlugin();
}

// Export for Node.js/Jest
if (typeof module !== 'undefined' && module.exports) {
  module.exports = UniversalFormPlugin;
}
