/**
 * Module 4: Event Handler - Blur Detection
 * 
 * Detects when user leaves a field (blur event)
 * Triggers validation for that specific field
 * 
 * Usage:
 *   const blurHandler = new BlurHandler(formElement);
 *   blurHandler.onFieldBlur((fieldName, value) => {
 *     console.log(`User left ${fieldName} with value: ${value}`);
 *   });
 *   blurHandler.attach();
 */

class BlurHandler {
  /**
   * Initialize blur handler
   * @param {HTMLElement|string} formSelector - Form element or CSS selector
   */
  constructor(formSelector) {
    this.formSelector = formSelector;
    this.formElement = null;
    this.fields = [];
    this.callbacks = [];
    this.isAttached = false;
    this.lastFocusedField = null;
  }

  /**
   * Register callback for blur events
   * @param {Function} callback - Called with (fieldName, value, fieldElement)
   */
  onFieldBlur(callback) {
    if (typeof callback !== 'function') {
      throw new Error('Callback must be a function');
    }
    this.callbacks.push(callback);
  }

  /**
   * Find all input fields in the form
   * @returns {Array}
   */
  findInputFields() {
    if (!this.formElement) {
      return [];
    }

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
      select
    `;

    return Array.from(this.formElement.querySelectorAll(selector));
  }

  /**
   * Handle blur event
   * @param {HTMLElement} field - The field element
   * @param {Event} event - The blur event
   */
  handleFieldBlur = (field, event) => {
    const fieldName = field.getAttribute('name') || field.getAttribute('id') || field.placeholder || `field_${this.fields.indexOf(field)}`;
    const value = field.value;

    // Trigger callbacks
    this.callbacks.forEach(callback => {
      try {
        callback(fieldName, value, field, event);
      } catch (error) {
        console.error(`Blur callback error for ${fieldName}:`, error);
      }
    });
  };

  /**
   * Attach blur listeners to all fields
   * @returns {boolean}
   */
  attach() {
    try {
      // Find form element
      if (typeof this.formSelector === 'string') {
        this.formElement = document.querySelector(this.formSelector);
      } else {
        this.formElement = this.formSelector;
      }

      if (!this.formElement) {
        console.error(`Form selector "${this.formSelector}" not found`);
        return false;
      }

      // Find all fields
      this.fields = this.findInputFields();

      if (this.fields.length === 0) {
        console.warn(`No input fields found in form`);
        return false;
      }

      // Attach blur listeners
      this.fields.forEach(field => {
        field.addEventListener('blur', (event) => this.handleFieldBlur(field, event));
      });

      this.isAttached = true;
      console.log(`✓ Blur handler attached to ${this.fields.length} fields`);
      return true;
    } catch (error) {
      console.error('Error attaching blur handler:', error);
      return false;
    }
  }

  /**
   * Detach all blur listeners
   */
  detach() {
    if (this.fields.length === 0) return;

    this.fields.forEach(field => {
      const newField = field.cloneNode(true);
      field.parentNode.replaceChild(newField, field);
    });

    this.isAttached = false;
    console.log('✓ Blur handler detached');
  }

  /**
   * Check if handler is attached
   * @returns {boolean}
   */
  attached() {
    return this.isAttached;
  }

  /**
   * Get field count
   * @returns {number}
   */
  getFieldCount() {
    return this.fields.length;
  }
}

// Export for Node.js/Jest
if (typeof module !== 'undefined' && module.exports) {
  module.exports = BlurHandler;
}
