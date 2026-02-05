/**
 * Module 5: API Communicator
 * 
 * Sends individual field data to backend for validation
 * Receives Gemini validation results
 * 
 * Usage:
 *   const api = new APICommunicator('http://localhost:5000/validate-field');
 *   api.validateField('field1', 'John Doe').then(result => {
 *     console.log(result);
 *   });
 */

class APICommunicator {
  /**
   * Initialize API communicator
   * @param {string} backendUrl - Backend endpoint URL
   * @param {Object} options - Configuration
   *   - timeout: Request timeout in ms (default: 30000)
   *   - retries: Number of retries (default: 3)
   *   - debug: Enable logging (default: false)
   */
  constructor(backendUrl, options = {}) {
    this.backendUrl = backendUrl;
    this.timeout = options.timeout || 30000;
    this.retries = options.retries || 3;
    this.debug = options.debug || false;
    
    this.pendingRequests = new Map(); // fieldName -> AbortController
    this.requestHistory = [];
  }

  /**
   * Validate a single field
   * @param {string} fieldName - Field name
   * @param {string} fieldValue - Field value
   * @param {Object} ruleContext - Additional context
   * @returns {Promise} Result from backend
   */
  async validateField(fieldName, fieldValue, ruleContext = {}) {
    // Cancel previous request for this field
    if (this.pendingRequests.has(fieldName)) {
      this.pendingRequests.get(fieldName).abort();
    }

    const abortController = new AbortController();
    this.pendingRequests.set(fieldName, abortController);

    try {
      const payload = {
        field_name: fieldName,
        field_value: fieldValue,
        context: ruleContext,
        timestamp: new Date().toISOString(),
      };

      this.log('SEND', `Validating ${fieldName}: "${fieldValue}"`);

      const response = await Promise.race([
        this.sendRequest(payload, abortController.signal),
        this.createTimeout(this.timeout),
      ]);

      // Record successful request
      this.requestHistory.push({
        fieldName,
        fieldValue,
        status: 'success',
        timestamp: new Date(),
        result: response,
      });

      this.log('RESPONSE', `${fieldName}: ${response.status}`);

      return response;
    } catch (error) {
      if (error.name === 'AbortError') {
        this.log('CANCELLED', `Request for ${fieldName} was cancelled`);
        return { status: 'cancelled', error: 'Request cancelled' };
      }

      // Log failed request
      this.requestHistory.push({
        fieldName,
        fieldValue,
        status: 'error',
        timestamp: new Date(),
        error: error.message,
      });

      this.log('ERROR', `${fieldName}: ${error.message}`);

      // Retry logic
      if (this.retries > 0 && !error.message.includes('Network')) {
        this.log('RETRY', `Retrying ${fieldName}...`);
        await this.delay(1000);
        return this.validateField(fieldName, fieldValue, ruleContext);
      }

      throw error;
    } finally {
      this.pendingRequests.delete(fieldName);
    }
  }

  /**
   * Send HTTP request to backend
   * @private
   */
  async sendRequest(payload, signal) {
    const response = await fetch(this.backendUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Request-ID': `${Date.now()}-${Math.random()}`,
      },
      body: JSON.stringify(payload),
      signal,
    });

    if (!response.ok) {
      throw new Error(`Backend error: ${response.status} ${response.statusText}`);
    }

    return response.json();
  }

  /**
   * Create timeout promise
   * @private
   */
  createTimeout(ms) {
    return new Promise((_, reject) => {
      setTimeout(() => reject(new Error(`Request timeout after ${ms}ms`)), ms);
    });
  }

  /**
   * Delay helper
   * @private
   */
  delay(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
  }

  /**
   * Cancel pending request for a field
   * @param {string} fieldName
   */
  cancelValidation(fieldName) {
    if (this.pendingRequests.has(fieldName)) {
      this.pendingRequests.get(fieldName).abort();
      this.pendingRequests.delete(fieldName);
    }
  }

  /**
   * Cancel all pending requests
   */
  cancelAll() {
    this.pendingRequests.forEach(controller => controller.abort());
    this.pendingRequests.clear();
  }

  /**
   * Get request history
   * @returns {Array}
   */
  getHistory() {
    return [...this.requestHistory];
  }

  /**
   * Clear request history
   */
  clearHistory() {
    this.requestHistory = [];
  }

  /**
   * Logging
   * @private
   */
  log(level, message) {
    if (this.debug) {
      console.log(`[APICommunicator] [${level}] ${message}`);
    }
  }
}

// Export for Node.js/Jest
if (typeof module !== 'undefined' && module.exports) {
  module.exports = APICommunicator;
}
