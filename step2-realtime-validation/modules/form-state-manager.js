/**
 * Module 2: Form State Manager
 * 
 * Manages form state persistence across browser sessions.
 * Stores state in memory AND localStorage.
 * Syncs with Module 1 (FormInputListener) callbacks.
 * 
 * Usage:
 *   const stateManager = new FormStateManager('my-form', 8);
 *   listener.onFieldChange((name, value, allFields) => {
 *     stateManager.updateState(name, value);
 *   });
 *   
 *   // Later:
 *   const state = stateManager.getState();
 *   const saved = stateManager.loadState();
 */

class FormStateManager {
  /**
   * Initialize state manager
   * @param {string} formName - Form identifier (for localStorage key)
   * @param {number} fieldCount - Number of fields to track
   * @param {boolean} useLocalStorage - Save to localStorage (default: true)
   * @param {boolean} autoSave - Automatically save after changes (default: true)
   * @param {number} autoSaveDelay - Delay in ms before auto-saving (default: 1000)
   */
  constructor(formName, fieldCount = 8, useLocalStorage = true, autoSave = true, autoSaveDelay = 1000) {
    this.formName = formName;
    this.fieldCount = fieldCount;
    this.useLocalStorage = useLocalStorage;
    this.autoSave = autoSave;
    this.autoSaveDelay = autoSaveDelay;
    this.storageKey = `form_state_${formName}`;
    
    // In-memory state
    this.state = {};
    this.history = [];
    this.lastModified = null;
    this.isDirty = false;
    
    // Auto-save timer
    this.autoSaveTimer = null;
    
    // Callbacks
    this.stateChangeCallbacks = [];
    this.saveCallbacks = [];
    
    // Initialize with empty values
    this.initializeState();
    
    // Load existing state
    this.loadState();
  }

  /**
   * Initialize empty state object
   */
  initializeState() {
    this.state = {};
    for (let i = 1; i <= this.fieldCount; i++) {
      this.state[`field${i}`] = '';
    }
    this.lastModified = new Date();
  }

  /**
   * Update a single field value
   * @param {string} fieldName - Field name
   * @param {string} value - Field value
   */
  updateState(fieldName, value) {
    const oldValue = this.state[fieldName];
    
    if (oldValue !== value) {
      this.state[fieldName] = value;
      this.lastModified = new Date();
      this.isDirty = true;
      
      // Add to history
      this.history.push({
        timestamp: this.lastModified,
        field: fieldName,
        oldValue,
        newValue: value,
      });
      
      // Trigger callbacks
      this.stateChangeCallbacks.forEach(callback => {
        try {
          callback(fieldName, value, this.state);
        } catch (error) {
          console.error(`State change callback error: ${error.message}`);
        }
      });

      // Auto-save with debouncing
      if (this.autoSave) {
        this.scheduleAutoSave();
      }
    }
  }

  /**
   * Schedule auto-save with debouncing
   * @private
   */
  scheduleAutoSave() {
    // Clear existing timer
    if (this.autoSaveTimer) {
      clearTimeout(this.autoSaveTimer);
    }

    // Set new timer
    this.autoSaveTimer = setTimeout(() => {
      this.saveState();
      this.autoSaveTimer = null;
    }, this.autoSaveDelay);
  }

  /**
   * Update multiple fields at once
   * @param {Object} updates - { field1: 'value', field2: 'value', ... }
   */
  updateMultiple(updates) {
    Object.entries(updates).forEach(([field, value]) => {
      this.updateState(field, value);
    });
  }

  /**
   * Get current state (copy)
   * @returns {Object} Copy of current state
   */
  getState() {
    return { ...this.state };
  }

  /**
   * Get specific field value
   * @param {string} fieldName - Field name
   * @returns {string} Field value
   */
  getFieldValue(fieldName) {
    return this.state[fieldName] || '';
  }

  /**
   * Save state to localStorage
   * @returns {boolean} True if successful
   */
  saveState() {
    if (!this.useLocalStorage) {
      return false;
    }

    try {
      const data = {
        formName: this.formName,
        state: this.state,
        timestamp: this.lastModified.toISOString(),
        version: 1,
      };

      localStorage.setItem(this.storageKey, JSON.stringify(data));
      this.isDirty = false;

      // Trigger save callbacks
      this.saveCallbacks.forEach(callback => {
        try {
          callback(true, this.storageKey);
        } catch (error) {
          console.error(`Save callback error: ${error.message}`);
        }
      });

      return true;
    } catch (error) {
      console.error(`Failed to save state: ${error.message}`);
      
      // Trigger save callbacks with error
      this.saveCallbacks.forEach(callback => {
        try {
          callback(false, error.message);
        } catch (cbError) {
          console.error(`Save callback error: ${cbError.message}`);
        }
      });

      return false;
    }
  }

  /**
   * Load state from localStorage
   * @returns {Object|null} Loaded state or null if not found
   */
  loadState() {
    if (!this.useLocalStorage) {
      return null;
    }

    try {
      const data = localStorage.getItem(this.storageKey);
      if (!data) {
        return null;
      }

      const parsed = JSON.parse(data);
      
      // Validate structure
      if (!parsed.state || typeof parsed.state !== 'object') {
        return null;
      }

      // Load state
      this.state = parsed.state;
      this.lastModified = new Date(parsed.timestamp);
      this.isDirty = false;

      return this.state;
    } catch (error) {
      console.error(`Failed to load state: ${error.message}`);
      return null;
    }
  }

  /**
   * Check if state exists in localStorage
   * @returns {boolean}
   */
  hasStoredState() {
    if (!this.useLocalStorage) {
      return false;
    }
    return localStorage.getItem(this.storageKey) !== null;
  }

  /**
   * Clear state from memory and storage
   */
  clearState() {
    this.initializeState();
    this.history = [];
    this.isDirty = false;

    if (this.useLocalStorage) {
      try {
        localStorage.removeItem(this.storageKey);
      } catch (error) {
        console.error(`Failed to clear storage: ${error.message}`);
      }
    }
  }

  /**
   * Get state change history
   * @returns {Array} Array of state changes
   */
  getHistory() {
    return [...this.history];
  }

  /**
   * Get state as JSON string
   * @returns {string} JSON representation of state
   */
  toJSON() {
    return JSON.stringify({
      formName: this.formName,
      state: this.state,
      timestamp: this.lastModified?.toISOString(),
      isDirty: this.isDirty,
      historyCount: this.history.length,
    }, null, 2);
  }

  /**
   * Get localStorage data (for debugging)
   * @returns {Object|null} Raw localStorage data
   */
  getStorageData() {
    if (!this.useLocalStorage) {
      return null;
    }

    try {
      const data = localStorage.getItem(this.storageKey);
      return data ? JSON.parse(data) : null;
    } catch (error) {
      return null;
    }
  }

  /**
   * Register callback for state changes
   * @param {Function} callback - Called with (fieldName, value, allState)
   */
  onStateChange(callback) {
    if (typeof callback !== 'function') {
      throw new Error('Callback must be a function');
    }
    this.stateChangeCallbacks.push(callback);
  }

  /**
   * Register callback for save events
   * @param {Function} callback - Called with (success, message)
   */
  onSave(callback) {
    if (typeof callback !== 'function') {
      throw new Error('Callback must be a function');
    }
    this.saveCallbacks.push(callback);
  }

  /**
   * Get metadata about state
   * @returns {Object}
   */
  getMetadata() {
    return {
      formName: this.formName,
      fieldCount: this.fieldCount,
      lastModified: this.lastModified?.toISOString(),
      isDirty: this.isDirty,
      hasStoredState: this.hasStoredState(),
      historyCount: this.history.length,
      storageKey: this.storageKey,
    };
  }

  /**
   * Check if state matches expected field count
   * @returns {boolean}
   */
  isValid() {
    return Object.keys(this.state).length === this.fieldCount;
  }

  /**
   * Get all fields that have values
   * @returns {Array} Array of field names with non-empty values
   */
  getFilledFields() {
    return Object.entries(this.state)
      .filter(([, value]) => value && value.trim() !== '')
      .map(([field]) => field);
  }

  /**
   * Get field count (filled/total)
   * @returns {Object} { filled: number, total: number }
   */
  getFieldCountStats() {
    const filled = this.getFilledFields().length;
    return {
      filled,
      total: this.fieldCount,
      percentage: Math.round((filled / this.fieldCount) * 100),
    };
  }
}

// Export for Node.js/Jest
if (typeof module !== 'undefined' && module.exports) {
  module.exports = FormStateManager;
}
