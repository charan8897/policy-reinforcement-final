/**
 * Policy Field Validator - Content Script
 * Loads the policy plugin to monitor form fields and trigger validation
 */

// Load the actual policy plugin instead of reimplementing
function loadPolicyPlugin() {
  try {
    const script = document.createElement('script');
    script.src = 'http://localhost:5000/modules/policy-plugin-generic.js';
    script.onload = () => {
      console.log('✓ Policy Plugin loaded from content script');
    };
    script.onerror = () => {
      console.error('Failed to load policy plugin - fallback validation enabled');
    };
    
    if (document.head) {
      document.head.appendChild(script);
    } else if (document.documentElement) {
      document.documentElement.appendChild(script);
    } else {
      // Wait for DOM to be ready
      setTimeout(loadPolicyPlugin, 100);
      return;
    }
  } catch (error) {
    console.error('Error loading policy plugin:', error);
  }
}

// Load plugin when DOM is ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', loadPolicyPlugin);
} else {
  loadPolicyPlugin();
}

// NOTE: policy-plugin-generic.js handles all validation API calls
// Do not duplicate validation here - it's already loaded above

/**
 * Non-policy fields that don't need validation (general form fields)
 */
const GENERAL_FIELDS = new Set([
  'name', 'email', 'phone', 'address', 'city', 'state', 'zip',
  'first_name', 'last_name', 'full_name', 'employee_id', 'username',
  'password', 'confirm_password', 'message', 'comments', 'notes',
  'description', 'remarks', 'timestamp', 'date', 'created_at',
  'updated_at', 'status', 'id', 'submit', 'cancel', 'reset'
]);

/**
 * Policy-specific fields that should be validated
 */
const POLICY_FIELDS = new Set([
  'group_size', 'flight_hours', 'class_of_service', 'room_type',
  'booking_advance', 'booking_channel', 'destination', 'travel_purpose',
  'manager_approval', 'employee_name'
]);

// REMOVED: validateField() function - policy-plugin-generic.js handles all API calls

/**
 * Show validation result as badge near field
 */
function showValidationResult(element, result) {
  // Remove existing badge
  const existing = element.parentElement.querySelector('.policy-badge');
  if (existing) existing.remove();

  if (!result) return;

  // Create badge
  const badge = document.createElement('span');
  badge.className = `policy-badge policy-${result.status}`;
  badge.title = result.message;
  badge.innerHTML = result.status === 'valid' ? '✓' : '✗';

  // Style badge
  Object.assign(badge.style, {
    display: 'inline-block',
    marginLeft: '8px',
    padding: '4px 8px',
    borderRadius: '4px',
    fontSize: '12px',
    fontWeight: 'bold',
    cursor: 'pointer',
    backgroundColor: result.status === 'valid' ? '#22c55e' : '#ef4444',
    color: 'white',
    position: 'relative'
  });

  element.parentElement.appendChild(badge);

  // Show detailed popup on click
  badge.addEventListener('click', (e) => {
    e.stopPropagation();
    showDetailedValidation(element, result);
  });
}

/**
 * Show detailed validation popup
 */
function showDetailedValidation(element, result) {
  // Remove existing popup
  const existing = document.querySelector('.policy-validation-popup');
  if (existing) existing.remove();

  const popup = document.createElement('div');
  popup.className = 'policy-validation-popup';

  const rulesHtml = result.rules.length > 0
    ? `<div class="rules-section">
         <h4>📋 Applicable Rules:</h4>
         <ul>${result.rules.slice(0, 3).map(r => `<li>${r}</li>`).join('')}</ul>
       </div>`
    : '';

  const topMatchesHtml = result.validation_details?.top_matches?.length > 0
    ? `<div class="matches-section">
         <h4>🔍 Top Matches:</h4>
         <ul>${result.validation_details.top_matches.map(m =>
           `<li><small>Score: ${(m.similarity_score * 100).toFixed(0)}%</small><br>${m.rule.substring(0, 80)}...</li>`
         ).join('')}</ul>
       </div>`
    : '';

  popup.innerHTML = `
    <div class="popup-content">
      <div class="popup-header" style="background: ${result.status === 'valid' ? '#22c55e' : '#ef4444'}">
        <strong>${result.status.toUpperCase()}</strong>
      </div>
      <div class="popup-body">
        <p><strong>Field:</strong> ${result.field_name}</p>
        <p><strong>Value:</strong> <code>${result.field_value}</code></p>
        <p><strong>Message:</strong> ${result.message}</p>
        ${rulesHtml}
        ${topMatchesHtml}
        <p style="font-size: 11px; color: #999; margin-top: 10px;">
          <strong>Search Method:</strong> ${result.validation_details?.search_method || 'N/A'}
        </p>
      </div>
      <div class="popup-footer">
        <button class="popup-close">Close</button>
      </div>
    </div>
  `;

  // Style popup
  Object.assign(popup.style, {
    position: 'fixed',
    top: '50%',
    left: '50%',
    transform: 'translate(-50%, -50%)',
    zIndex: '10000',
    backgroundColor: 'white',
    borderRadius: '8px',
    boxShadow: '0 10px 40px rgba(0,0,0,0.3)',
    border: `3px solid ${result.status === 'valid' ? '#22c55e' : '#ef4444'}`,
    maxWidth: '500px',
    maxHeight: '80vh',
    overflowY: 'auto',
    fontFamily: 'system-ui, -apple-system, sans-serif',
    fontSize: '13px'
  });

  // Style content
  const style = document.createElement('style');
  style.textContent = `
    .policy-validation-popup .popup-content {
      padding: 0;
    }
    .policy-validation-popup .popup-header {
      padding: 15px;
      color: white;
      font-weight: bold;
      border-radius: 8px 8px 0 0;
    }
    .policy-validation-popup .popup-body {
      padding: 20px;
    }
    .policy-validation-popup .popup-body p {
      margin: 10px 0;
      line-height: 1.6;
    }
    .policy-validation-popup .popup-body code {
      background: #f0f0f0;
      padding: 2px 6px;
      border-radius: 3px;
      font-family: monospace;
    }
    .policy-validation-popup .rules-section,
    .policy-validation-popup .matches-section {
      margin-top: 15px;
      padding-top: 15px;
      border-top: 1px solid #f0f0f0;
    }
    .policy-validation-popup h4 {
      margin: 0 0 10px 0;
      font-size: 12px;
      color: #667eea;
    }
    .policy-validation-popup ul {
      list-style: none;
      padding: 0;
      margin: 0;
    }
    .policy-validation-popup li {
      padding: 8px;
      margin: 4px 0;
      background: #f9f9f9;
      border-left: 3px solid #667eea;
      border-radius: 3px;
      font-size: 12px;
      line-height: 1.4;
    }
    .policy-validation-popup .popup-footer {
      padding: 15px;
      border-top: 1px solid #f0f0f0;
      text-align: right;
    }
    .policy-validation-popup .popup-close {
      padding: 8px 16px;
      background: #667eea;
      color: white;
      border: none;
      border-radius: 4px;
      cursor: pointer;
      font-size: 12px;
      font-weight: bold;
    }
    .policy-validation-popup .popup-close:hover {
      background: #5568d3;
    }
  `;
  document.head.appendChild(style);
  document.body.appendChild(popup);

  popup.querySelector('.popup-close').addEventListener('click', () => {
    popup.remove();
  });

  // Close on escape
  const closeHandler = (e) => {
    if (e.key === 'Escape') {
      popup.remove();
      document.removeEventListener('keydown', closeHandler);
    }
  };
  document.addEventListener('keydown', closeHandler);
}

// REMOVED: monitorFormFields() - policy-plugin-generic.js handles field monitoring

/**
 * Start monitoring on page load
 */
function initMonitoring() {
  try {
    // policy-plugin-generic.js is already loaded and handles all field monitoring
    console.log('%c✓ Policy Field Validator Content Script Loaded', 'color: #667eea; font-size: 14px; font-weight: bold;');
    console.log('%c✓ Policy Plugin is active and monitoring form fields...', 'color: #22c55e;');
  } catch (error) {
    console.error('Error initializing monitoring:', error);
  }
}

// Wait for DOM to be ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initMonitoring);
} else if (document.readyState === 'interactive' || document.readyState === 'complete') {
  // DOM is ready, initialize immediately
  if (document.body) {
    initMonitoring();
  } else {
    // Body not ready yet, wait a bit
    setTimeout(initMonitoring, 100);
  }
}
