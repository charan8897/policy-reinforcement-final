/**
 * Policy Validator - Background Service Worker
 * Handles event coordination and storage
 */

console.log('Policy Validator Background Worker loaded');

// Initialize extension on install
chrome.runtime.onInstalled.addListener(() => {
  console.log('✓ Policy Validator extension installed');
  
  // Set default settings
  chrome.storage.sync.set({
    apiEndpoint: 'http://localhost:5000',
    enableValidation: true,
    showBadges: true,
    autoValidate: true
  }, () => {
    console.log('✓ Default settings saved');
  });
});

// Listen for messages from content script and popup
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.type === 'VALIDATION_RESULT') {
    chrome.storage.session.set({
      [`validation_${request.fieldName}`]: request.result,
      lastValidation: new Date().toISOString()
    });
    sendResponse({ status: 'stored' });
  } else if (request.type === 'GET_SETTINGS') {
    chrome.storage.sync.get(null, (items) => {
      sendResponse(items);
    });
  } else {
    sendResponse({ status: 'unknown' });
  }
  
  return true; // Keep channel open for async response
});
