/**
 * Policy Validator - Popup Script
 * Displays validation results and extension status
 */

const API_ENDPOINT = 'http://localhost:5000/api/health';

/**
 * Check API status
 */
async function checkAPIStatus() {
  try {
    const response = await fetch(API_ENDPOINT, { timeout: 2000 });
    const isOnline = response.ok;

    const statusEl = document.getElementById('api-status');
    const statusText = document.getElementById('api-status-text');

    if (isOnline) {
      statusEl.classList.add('online');
      statusText.textContent = 'Online';
      statusText.style.color = '#22c55e';
    } else {
      statusEl.classList.remove('online');
      statusText.textContent = 'Offline';
      statusText.style.color = '#ef4444';
    }
  } catch (error) {
    document.getElementById('api-status').classList.remove('online');
    document.getElementById('api-status-text').textContent = 'Offline';
    document.getElementById('api-status-text').style.color = '#ef4444';
  }
}

/**
 * Load and display recent validations from storage
 */
async function loadValidations() {
  const storage = await chrome.storage.session.get();
  const validationList = document.getElementById('validation-list');
  const validations = [];

  // Extract validations from storage
  for (const [key, value] of Object.entries(storage)) {
    if (key.startsWith('validation_') && value) {
      validations.push({
        field: key.replace('validation_', ''),
        result: value
      });
    }
  }

  if (validations.length === 0) {
    validationList.parentElement.querySelector('.empty-state').style.display = 'block';
    return;
  }

  validationList.parentElement.querySelector('.empty-state').style.display = 'none';
  validationList.innerHTML = '';

  let violationCount = 0;
  validations.forEach(({ field, result }) => {
    if (result.status === 'error' || result.status === 'warning') {
      violationCount++;
    }

    const item = document.createElement('div');
    item.className = 'field-item';
    item.innerHTML = `
      <span class="field-name">${field}</span>
      <span class="field-status ${result.status}">${result.status.toUpperCase()}</span>
      <div style="font-size: 11px; color: #666; margin-top: 4px;">${result.message}</div>
    `;
    validationList.appendChild(item);
  });

  // Update stats
  document.getElementById('fields-validated').textContent = validations.length;
  document.getElementById('violations-found').textContent = violationCount;
}

/**
 * Initialize popup
 */
async function init() {
  // Check API status
  checkAPIStatus();
  setInterval(checkAPIStatus, 3000);

  // Load validations
  loadValidations();
  setInterval(loadValidations, 1000);

  // Toggle validation
  document.getElementById('toggle-validation').addEventListener('change', (e) => {
    chrome.storage.session.set({
      validationEnabled: e.target.checked
    });

    // Notify content script
    chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
      chrome.tabs.sendMessage(tabs[0].id, {
        type: 'TOGGLE_VALIDATION',
        enabled: e.target.checked
      }).catch(() => {
        // Content script not ready, ignore
      });
    });
  });

  // Load toggle state
  const { validationEnabled } = await chrome.storage.session.get('validationEnabled');
  if (validationEnabled !== undefined) {
    document.getElementById('toggle-validation').checked = validationEnabled;
  }

  // Refresh button
  document.getElementById('refresh-btn').addEventListener('click', () => {
    chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
      chrome.tabs.reload(tabs[0].id);
      window.close();
    });
  });

  // Settings button
  document.getElementById('settings-btn').addEventListener('click', () => {
    chrome.runtime.openOptionsPage();
  });
}

// Initialize when popup opens
document.addEventListener('DOMContentLoaded', init);
