# Module 1: Testing Guide

Complete guide to test Module 1 (Input Listener) using both interactive and automated approaches.

---

## Table of Contents

1. [Interactive Testing (Browser)](#interactive-testing-browser)
2. [Automated Testing (Jest)](#automated-testing-jest)
3. [Manual Testing Checklist](#manual-testing-checklist)
4. [Debugging Tips](#debugging-tips)

---

## Interactive Testing (Browser)

### Setup

1. Navigate to the directory:
   ```bash
   cd /home/hutech/Documents/docupolicy/step2-realtime-validation
   ```

2. Open `test-page.html` in your browser:
   ```bash
   # On macOS
   open test-page.html
   
   # On Linux
   firefox test-page.html
   # or
   google-chrome test-page.html
   
   # On Windows
   start test-page.html
   ```

### Test Page Features

The test page (`test-page.html`) includes:

- **8 Form Fields** with different input types
- **Real-time Console** showing event logs
- **Field Values Display** showing current state
- **Statistics Dashboard** (fields detected, events fired, callbacks executed)
- **Control Buttons** (Attach, Detach, Reset, Clear Log)

### Interactive Test Steps

#### Test 1: Listener Attachment ✓

1. Page loads → Status shows "Pending"
2. Click **"Attach Listeners"** button
3. **Expected:**
   - Status changes to "Listening"
   - "Fields Detected" shows "8"
   - Console shows:
     ```
     ✓ FormInputListener: Found 8 fields
       Fields discovered: [...]
     ✓ Input listeners attached to all fields
     ✓ Field 1: field1 (text)
     ✓ Field 2: field2 (email)
     ... (6 more fields)
     ```

#### Test 2: Field Change Detection ✓

1. Listener is attached
2. Click in **Field 1 (Name)** and type: `John Doe`
3. **Expected:**
   - Console shows: `✓ field1 = "John Doe"`
   - "Events Fired" counter increases
   - "Callbacks Executed" counter increases
   - Field 1 in the values grid shows "John Doe"

#### Test 3: Multiple Fields ✓

1. Listener is attached
2. Fill multiple fields:
   - Field 1: `John Doe`
   - Field 2: `john@example.com`
   - Field 3: `30`
   - Field 7 (Comments): `This is a test`
3. **Expected:**
   - Each field shows in console as it's filled
   - Field Values grid updates in real-time
   - Each field shows its current value

#### Test 4: Different Input Types ✓

1. Listener is attached
2. Test each field type:
   - Text: Type `hello`
   - Email: Type `test@test.com` (browser may show validation)
   - Number: Type `42`
   - Tel: Type `123-456-7890`
   - Date: Click and select a date
   - Textarea: Type `multi\nline\ntext`
3. **Expected:**
   - All field types work correctly
   - Values update in grid and console
   - No errors in browser console (F12)

#### Test 5: Fast Typing ✓

1. Listener is attached
2. In Field 1, type rapidly: `abcdefghijklmnop`
3. **Expected:**
   - Events fire for each character (15+ events)
   - Console shows each character
   - "Events Fired" shows high number
   - No dropped events
   - No lag in UI

#### Test 6: Copy/Paste ✓

1. Listener is attached
2. Copy text: `Hello World 🌍`
3. Paste into Field 1
4. **Expected:**
   - Single input event fires
   - Console shows: `✓ field1 = "Hello World 🌍"`
   - Full pasted text appears

#### Test 7: Special Characters ✓

1. Listener is attached
2. In Field 6, type: `@#$%^&*()_+=-[]{}|;:,.<>?`
3. **Expected:**
   - All characters captured correctly
   - No errors in browser console
   - Value displays correctly

#### Test 8: Emoji & Unicode ✓

1. Listener is attached
2. In Field 1, type: `你好 🚀 مرحبا 🎉`
3. **Expected:**
   - All characters captured
   - Field values grid shows correctly
   - No character corruption

#### Test 9: Reset Functionality ✓

1. Fill in several fields
2. Click **"Reset Form"** button
3. **Expected:**
   - All field values clear
   - Field values grid shows all "(empty)"
   - Console shows: `✓ Form reset. All fields cleared.`

#### Test 10: Listener Detachment ✓

1. Listener is attached and listening
2. Type in a field (events fire)
3. Click **"Detach Listeners"** button
4. Try typing again - **no new events should appear**
5. **Expected:**
   - Status changes to "Detached"
   - No new console entries
   - Console shows: `✓ Listener detached`
   - "Attach Listeners" button is enabled again

#### Test 11: Re-attachment ✓

1. Listener is detached
2. Click **"Attach Listeners"** again
3. Type in a field
4. **Expected:**
   - Events fire again
   - Console shows new entries
   - All statistics reset and recount

---

## Automated Testing (Jest)

### Setup

1. Install dependencies:
   ```bash
   cd /home/hutech/Documents/docupolicy/step2-realtime-validation
   npm install
   ```

2. Verify installation:
   ```bash
   npm list jest
   # Should show: jest@29.x.x
   ```

### Running Tests

#### Basic Test Run
```bash
npm test
```

**Expected Output:**
```
PASS  __tests__/form-listener.test.js
  FormInputListener - Module 1: Input Listener
    Initialization
      ✓ should create instance with correct parameters (5ms)
      ✓ should use default field count (2ms)
    Field Discovery
      ✓ should find all 8 input fields (8ms)
      ... [30 tests total]

Tests:       30 passed, 30 total
Suites:      1 passed, 1 total
Time:        2.543s
```

#### Watch Mode (Recommended for Development)
```bash
npm run test:watch
```

This re-runs tests when you modify code. Type `q` to quit.

#### Coverage Report
```bash
npm run test:coverage
```

**Expected:**
```
File                  | % Stmts | % Branch | % Funcs | % Lines
All files             |   95.2% |   92.1%  |   97.3% |   95.0%
 form-listener.js     |   95.2% |   92.1%  |   97.3% |   95.0%
```

### Test Organization

Tests are organized into 7 suites:

#### Suite 1: Initialization (2 tests)
Tests instance creation and default values.
```bash
npm test -- --testNamePattern="Initialization"
```

#### Suite 2: Field Discovery (5 tests)
Tests finding and identifying form fields.
```bash
npm test -- --testNamePattern="Field Discovery"
```

#### Suite 3: Listener Attachment (3 tests)
Tests attaching/detaching listeners.
```bash
npm test -- --testNamePattern="Listener Attachment"
```

#### Suite 4: Callback Execution (6 tests)
Tests callback registration and execution.
```bash
npm test -- --testNamePattern="Callback Execution"
```

#### Suite 5: Field Value Tracking (3 tests)
Tests getting field values and metadata.
```bash
npm test -- --testNamePattern="Field Value Tracking"
```

#### Suite 6: Simulation Methods (3 tests)
Tests helper methods for testing.
```bash
npm test -- --testNamePattern="Simulation Methods"
```

#### Suite 7: Edge Cases (5 tests)
Tests special scenarios (unicode, long text, etc).
```bash
npm test -- --testNamePattern="Edge Cases"
```

### Understanding Test Output

Each test shows:
```
✓ should create instance with correct parameters (5ms)
└─ Passed in 5 milliseconds
```

If a test fails:
```
✗ should find all 8 input fields
└─ Expected 8, got 5
  at Listener.test.js:45:10
```

---

## Manual Testing Checklist

Print and use this checklist:

### Pre-Test Checklist
- [ ] Browser is Chrome/Firefox/Safari (not IE11)
- [ ] File paths are correct
- [ ] `test-page.html` opens without errors
- [ ] Console is open (F12) for debugging

### Interactive Test Checklist

#### Listener Attachment
- [ ] "Attach Listeners" button works
- [ ] Status shows "Listening"
- [ ] "Fields Detected" shows 8
- [ ] No errors in browser console (F12)
- [ ] Console shows field metadata

#### Field Input
- [ ] Typing in Field 1 appears in console
- [ ] Typing in Field 2 appears in console
- [ ] All 8 fields work individually
- [ ] Field values grid updates in real-time

#### Event Firing
- [ ] Events increment counter (one per keystroke)
- [ ] Callbacks increment counter
- [ ] Rapid typing (10+ chars) fires all events
- [ ] Pasting fires exactly 1 event

#### Different Input Types
- [ ] Text input works
- [ ] Email input works
- [ ] Number input works
- [ ] Tel input works
- [ ] Date input works
- [ ] Textarea works

#### Edge Cases
- [ ] Special chars (@#$%...) work
- [ ] Unicode (你好) works
- [ ] Emoji (🌍 🚀) work
- [ ] Long text (1000+ chars) works
- [ ] Empty fields work

#### Reset & Detach
- [ ] Reset button clears all fields
- [ ] Detach button stops listening
- [ ] Events don't fire after detach
- [ ] Can re-attach and listen again

### Automated Test Checklist

- [ ] `npm install` completes without errors
- [ ] `npm test` runs all 30 tests
- [ ] All 30 tests pass
- [ ] No console warnings/errors during test
- [ ] Coverage report shows > 90%
- [ ] Watch mode works (`npm run test:watch`)

---

## Debugging Tips

### Interactive Debugging

1. **Open Developer Tools:**
   ```
   Chrome/Firefox: F12 or Ctrl+Shift+I
   Safari: Cmd+Option+I
   ```

2. **Console Logs (in addition to page console):**
   ```javascript
   // Paste this in browser console:
   console.log('Listener:', window.testPage.listener);
   console.log('Field count:', window.testPage.listener?.getFieldCount());
   console.log('Field values:', window.testPage.listener?.getFieldValues());
   ```

3. **Check Listener State:**
   ```javascript
   // In browser console:
   window.testPage.listener.attached()  // Should be true/false
   window.testPage.listener.getFieldMetadata()  // Shows all fields
   ```

4. **Manually Trigger Event:**
   ```javascript
   // In browser console:
   window.testPage.listener.simulateInput(0, 'Test Value');
   // Should show in console and increment counters
   ```

### Automated Test Debugging

1. **Run Single Test Suite:**
   ```bash
   npm test -- --testNamePattern="Callback Execution"
   ```

2. **Run Single Test:**
   ```bash
   npm test -- --testNamePattern="should execute callback"
   ```

3. **Verbose Output:**
   ```bash
   npm test -- --verbose
   ```

4. **No Coverage (faster):**
   ```bash
   npm test -- --no-coverage
   ```

5. **Update Snapshots (if needed):**
   ```bash
   npm test -- -u
   ```

### Common Issues

**Issue: Tests won't run**
```bash
# Solution: Make sure Jest is installed
npm install --save-dev jest jest-environment-jsdom
```

**Issue: Browser can't find test-page.html**
```bash
# Solution: Check file exists
ls -la test-page.html
# Or open with full path:
open /home/hutech/Documents/docupolicy/step2-realtime-validation/test-page.html
```

**Issue: Callbacks not firing**
```javascript
// Make sure you attach AFTER registering callback
listener.onFieldChange(callback);  // Register first
listener.attach();                 // Then attach
```

**Issue: Detach doesn't work**
```javascript
// Make sure listener was attached first
if (listener.attached()) {
  listener.detach();  // Only works if attached
}
```

---

## Test Success Criteria

### ✓ Module 1 is Working If:

1. **Interactive Test Page:**
   - [x] All 8 fields are detected
   - [x] Events fire as user types
   - [x] Callbacks execute correctly
   - [x] Field values update in real-time
   - [x] Reset works
   - [x] Detach stops listening

2. **Jest Tests:**
   - [x] All 30 tests pass
   - [x] No console errors during test
   - [x] Coverage > 90%

3. **Browser Console (F12):**
   - [x] No JavaScript errors
   - [x] No warnings
   - [x] Custom logs appear correctly

---

## Next: Module 2

Once Module 1 tests pass completely:

1. Mark this module as ✓ **COMPLETE**
2. Proceed to **Module 2: Form State Manager**
3. Module 2 will use Module 1's output
4. Follow the same testing approach

---

## Getting Help

If tests fail:

1. **Check the error message carefully** - usually tells you what's wrong
2. **Run test with verbose flag** - shows more details
3. **Check browser console (F12)** - may show JavaScript errors
4. **Review README.md** - common issues section
5. **Check that form structure matches** - 8 fields with correct IDs

---

## Summary

**Module 1: Input Listener - Testing Summary**

| Test Type | Method | Effort | Confidence |
|-----------|--------|--------|------------|
| Interactive | Browser manual | 20 min | Very High |
| Automated | Jest `npm test` | 5 min | Very High |
| Debugging | Console logs | 10 min | High |
| **Total** | **Both** | **35 min** | **Very High** |

Once all tests pass → Module 1 ✓ **COMPLETE**
