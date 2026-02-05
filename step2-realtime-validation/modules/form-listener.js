/**
 * Module 1: Input Listener
 * 
 * Detects user input on form fields and notifies listeners.
 * This is a standalone, framework-agnostic module.
 * 
 * Usage:
 *   const listener = new FormInputListener('#form-container', 8);
 *   listener.onFieldChange((fieldName, value, allFields) => {
 *     console.log(`${fieldName} changed to: ${value}`);
 *     console.log('All fields:', allFields);
 *   });
 *   listener.attach();
 */

class FormInputListener {
  /**
   * Initialize the form listener
   * @param {string} formSelector - CSS selector for form or container
   * @param {number} expectedFieldCount - Expected number of input fields
   */
  constructor(formSelector, expectedFieldCount = 8) {
    this.formSelector = formSelector;
    this.expectedFieldCount = expectedFieldCount;
    this.formElement = null;
    this.fields = [];
    this.callbacks = [];
    this.isAttached = false;
  }

  /**
   * Register a callback to be called when any field changes
   * @param {Function} callback - Called with (fieldName, value, allFields)
   */
  onFieldChange(callback) {
    if (typeof callback !== 'function') {
      throw new Error('Callback must be a function');
    }
    this.callbacks.push(callback);
  }

  /**
   * Find all input fields within the form
   * Supports multiple input types and frameworks
   * @returns {Array} Array of input field elements
   */
  findInputFields() {
    if (!this.formElement) {
      return [];
    }

    // Extended selector to capture more input types
    const selector = `
      input[type="text"],
      input[type="email"],
      input[type="number"],
      input[type="tel"],
      input[type="date"],
      input[type="password"],
      input[type="search"],
      input[type="url"],
      input[type="time"],
      input[type="datetime-local"],
      input[type="month"],
      input[type="week"],
      input[type="color"],
      input:not([type]),
      textarea,
      select,
      [contenteditable="true"],
      [role="textbox"],
      [role="combobox"],
      input[type="checkbox"],
      input[type="radio"]
    `;

    const inputs = Array.from(this.formElement.querySelectorAll(selector));

    return inputs;
  }

  /**
   * Get current values of all fields
   * @returns {Object} Object with fieldName: value pairs
   */
  getFieldValues() {
    const values = {};
    this.fields.forEach((field) => {
      const name = field.getAttribute('name') || field.getAttribute('id') || field.placeholder || `field_${this.fields.indexOf(field)}`;
      values[name] = field.value;
    });
    return values;
  }

  /**
   * Get field metadata
   * @returns {Array} Array of field information
   */
  getFieldMetadata() {
    return this.fields.map((field, index) => ({
      index: index + 1,
      name: field.getAttribute('name') || field.getAttribute('id') || field.placeholder || `field_${index + 1}`,
      type: field.getAttribute('type') || field.tagName.toLowerCase(),
      placeholder: field.getAttribute('placeholder') || '',
      value: field.value,
    }));
  }

  /**
   * Handle input event on a field
   * @param {HTMLElement} field - The input field
   * @param {Event} event - The input event
   */
  handleFieldInput = (field, event) => {
    const fieldName = field.getAttribute('name') || field.getAttribute('id') || field.placeholder || `field_${this.fields.indexOf(field) + 1}`;
    const value = field.value;
    const allValues = this.getFieldValues();

    // Call all registered callbacks
    this.callbacks.forEach((callback) => {
      try {
        callback(fieldName, value, allValues, event);
      } catch (error) {
        console.error(`Callback error for field ${fieldName}:`, error);
      }
    });
  };

  /**
   * Attach listeners to all input fields (auto-called on init if autoAttach=true)
   * @returns {boolean} True if successful, false otherwise
   */
  attach(silent = false) {
    try {
      // Find form element
      this.formElement = document.querySelector(this.formSelector);
      
      if (!this.formElement) {
        console.error(`Form selector "${this.formSelector}" not found in DOM`);
        return false;
      }

      // Find all input fields
      this.fields = this.findInputFields();

      if (this.fields.length === 0) {
        console.warn(`No input fields found in "${this.formSelector}"`);
        return false;
      }

      // Log discovery (silent mode for plugin auto-attach)
      if (!silent) {
        console.log(`✓ FormInputListener: Found ${this.fields.length} fields (expected: ${this.expectedFieldCount})`);
        const metadata = this.getFieldMetadata();
        console.log('  Fields discovered:', metadata);
      }

      // Attach listeners to each field
      this.fields.forEach((field) => {
        field.addEventListener('input', (event) => this.handleFieldInput(field, event));
      });

      this.isAttached = true;
      if (!silent) {
        console.log('✓ Input listeners attached to all fields');
      }
      return true;
    } catch (error) {
      console.error('Error attaching listeners:', error);
      return false;
    }
  }

  /**
   * Detach all listeners
   */
  detach() {
    if (this.fields.length === 0) return;

    this.fields.forEach((field) => {
      // Remove all event listeners by cloning and replacing
      const newField = field.cloneNode(true);
      field.parentNode.replaceChild(newField, field);
    });

    this.isAttached = false;
    console.log('✓ Input listeners detached');
  }

  /**
   * Check if listeners are currently attached
   * @returns {boolean}
   */
  attached() {
    return this.isAttached;
  }

  /**
   * Get number of fields being monitored
   * @returns {number}
   */
  getFieldCount() {
    return this.fields.length;
  }

  /**
   * Simulate input event on a specific field (for testing)
   * @param {number} fieldIndex - Index of field (0-based)
   * @param {string} value - Value to simulate
   */
  simulateInput(fieldIndex, value) {
    if (fieldIndex < 0 || fieldIndex >= this.fields.length) {
      throw new Error(`Invalid field index: ${fieldIndex}`);
    }

    const field = this.fields[fieldIndex];
    field.value = value;

    // Create and dispatch input event
    const event = new Event('input', { bubbles: true });
    field.dispatchEvent(event);
  }

  /**
   * Reset all field values to empty
   */
  resetFields() {
    this.fields.forEach((field) => {
      field.value = '';
    });
  }
}

// Export for use in Node.js/Jest environments
if (typeof module !== 'undefined' && module.exports) {
  module.exports = FormInputListener;
}
