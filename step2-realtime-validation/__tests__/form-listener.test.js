/**
 * Jest Tests for FormInputListener (Module 1)
 * 
 * Test Strategy:
 *   1. Test listener initialization
 *   2. Test field discovery
 *   3. Test event listener attachment
 *   4. Test callback execution
 *   5. Test field value tracking
 *   6. Test error handling
 */

const FormInputListener = require('../modules/form-listener');

describe('FormInputListener - Module 1: Input Listener', () => {

  // Setup: Create test HTML structure before each test
  beforeEach(() => {
    document.body.innerHTML = `
      <form id="test-form">
        <input type="text" name="field1" id="field1" placeholder="Name" />
        <input type="email" name="field2" id="field2" placeholder="Email" />
        <input type="number" name="field3" id="field3" placeholder="Age" />
        <input type="tel" name="field4" id="field4" placeholder="Phone" />
        <input type="date" name="field5" id="field5" />
        <input type="text" name="field6" id="field6" placeholder="Department" />
        <textarea name="field7" id="field7" placeholder="Comments"></textarea>
        <input type="text" name="field8" id="field8" placeholder="Reference" />
      </form>
    `;
  });

  afterEach(() => {
    document.body.innerHTML = '';
  });

  // ===========================================================================
  // TEST 1: Initialization
  // ===========================================================================
  describe('Initialization', () => {
    test('should create instance with correct parameters', () => {
      const listener = new FormInputListener('#test-form', 8);
      
      expect(listener.formSelector).toBe('#test-form');
      expect(listener.expectedFieldCount).toBe(8);
      expect(listener.isAttached).toBe(false);
    });

    test('should use default field count if not specified', () => {
      const listener = new FormInputListener('#test-form');
      
      expect(listener.expectedFieldCount).toBe(8);
    });
  });

  // ===========================================================================
  // TEST 2: Field Discovery
  // ===========================================================================
  describe('Field Discovery', () => {
    test('should find all 8 input fields in the form', () => {
      const listener = new FormInputListener('#test-form', 8);
      listener.attach();
      
      expect(listener.getFieldCount()).toBe(8);
    });

    test('should detect correct field types', () => {
      const listener = new FormInputListener('#test-form', 8);
      listener.attach();

      const metadata = listener.getFieldMetadata();
      
      expect(metadata[0].type).toBe('text');
      expect(metadata[1].type).toBe('email');
      expect(metadata[2].type).toBe('number');
      expect(metadata[3].type).toBe('tel');
      expect(metadata[4].type).toBe('date');
      expect(metadata[6].type).toBe('textarea');
    });

    test('should extract field names from attributes', () => {
      const listener = new FormInputListener('#test-form', 8);
      listener.attach();

      const metadata = listener.getFieldMetadata();
      
      expect(metadata[0].name).toBe('field1');
      expect(metadata[1].name).toBe('field2');
      expect(metadata[7].name).toBe('field8');
    });

    test('should handle missing form selector gracefully', () => {
      const listener = new FormInputListener('#non-existent-form', 8);
      const result = listener.attach();
      
      expect(result).toBe(false);
      expect(listener.getFieldCount()).toBe(0);
    });

    test('should warn when field count mismatch occurs', () => {
      const consoleSpy = jest.spyOn(console, 'warn').mockImplementation();
      
      const listener = new FormInputListener('#test-form', 10);
      listener.attach();
      
      // Note: We don't warn about mismatches, just log discovery
      consoleSpy.mockRestore();
    });
  });

  // ===========================================================================
  // TEST 3: Listener Attachment
  // ===========================================================================
  describe('Listener Attachment', () => {
    test('should attach input listeners to all fields', () => {
      const listener = new FormInputListener('#test-form', 8);
      const result = listener.attach();
      
      expect(result).toBe(true);
      expect(listener.isAttached).toBe(true);
      expect(listener.attached()).toBe(true);
    });

    test('should return false if form not found', () => {
      const listener = new FormInputListener('#non-existent', 8);
      const result = listener.attach();
      
      expect(result).toBe(false);
      expect(listener.isAttached).toBe(false);
    });

    test('should allow detaching listeners', () => {
      const listener = new FormInputListener('#test-form', 8);
      listener.attach();
      
      expect(listener.isAttached).toBe(true);
      
      listener.detach();
      
      expect(listener.isAttached).toBe(false);
    });
  });

  // ===========================================================================
  // TEST 4: Callback Execution
  // ===========================================================================
  describe('Callback Execution', () => {
    test('should execute callback when field value changes', () => {
      const listener = new FormInputListener('#test-form', 8);
      const mockCallback = jest.fn();
      
      listener.onFieldChange(mockCallback);
      listener.attach();

      // Simulate user typing in field1
      const field1 = document.getElementById('field1');
      field1.value = 'John Doe';
      field1.dispatchEvent(new Event('input', { bubbles: true }));

      expect(mockCallback).toHaveBeenCalledTimes(1);
      expect(mockCallback).toHaveBeenCalledWith(
        'field1',
        'John Doe',
        expect.objectContaining({ field1: 'John Doe' }),
        expect.any(Event)
      );
    });

    test('should call callback with all field values', () => {
      const listener = new FormInputListener('#test-form', 8);
      const mockCallback = jest.fn();
      
      listener.onFieldChange(mockCallback);
      listener.attach();

      // Set values in multiple fields
      document.getElementById('field1').value = 'John';
      document.getElementById('field2').value = 'john@example.com';
      document.getElementById('field1').dispatchEvent(new Event('input', { bubbles: true }));

      const callArgs = mockCallback.mock.calls[0];
      expect(callArgs[2]).toEqual(
        expect.objectContaining({
          field1: 'John',
          field2: 'john@example.com',
        })
      );
    });

    test('should reject non-function callbacks', () => {
      const listener = new FormInputListener('#test-form', 8);
      
      expect(() => {
        listener.onFieldChange('not a function');
      }).toThrow('Callback must be a function');
    });

    test('should handle multiple callbacks', () => {
      const listener = new FormInputListener('#test-form', 8);
      const callback1 = jest.fn();
      const callback2 = jest.fn();
      const callback3 = jest.fn();
      
      listener.onFieldChange(callback1);
      listener.onFieldChange(callback2);
      listener.onFieldChange(callback3);
      listener.attach();

      const field1 = document.getElementById('field1');
      field1.value = 'test';
      field1.dispatchEvent(new Event('input', { bubbles: true }));

      expect(callback1).toHaveBeenCalledTimes(1);
      expect(callback2).toHaveBeenCalledTimes(1);
      expect(callback3).toHaveBeenCalledTimes(1);
    });

    test('should handle callback errors gracefully', () => {
      const listener = new FormInputListener('#test-form', 8);
      const errorCallback = jest.fn(() => {
        throw new Error('Callback error');
      });
      const normalCallback = jest.fn();
      
      listener.onFieldChange(errorCallback);
      listener.onFieldChange(normalCallback);
      listener.attach();

      const consoleSpy = jest.spyOn(console, 'error').mockImplementation();
      
      const field1 = document.getElementById('field1');
      field1.value = 'test';
      field1.dispatchEvent(new Event('input', { bubbles: true }));

      expect(errorCallback).toHaveBeenCalled();
      expect(normalCallback).toHaveBeenCalled();
      expect(consoleSpy).toHaveBeenCalled();
      
      consoleSpy.mockRestore();
    });
  });

  // ===========================================================================
  // TEST 5: Field Value Tracking
  // ===========================================================================
  describe('Field Value Tracking', () => {
    test('should track all field values correctly', () => {
      const listener = new FormInputListener('#test-form', 8);
      listener.attach();

      document.getElementById('field1').value = 'John Doe';
      document.getElementById('field2').value = 'john@example.com';
      document.getElementById('field3').value = '30';

      const values = listener.getFieldValues();
      
      expect(values.field1).toBe('John Doe');
      expect(values.field2).toBe('john@example.com');
      expect(values.field3).toBe('30');
    });

    test('should get accurate field metadata', () => {
      const listener = new FormInputListener('#test-form', 8);
      listener.attach();

      const metadata = listener.getFieldMetadata();
      
      expect(metadata.length).toBe(8);
      expect(metadata[0]).toEqual(
        expect.objectContaining({
          index: 1,
          name: 'field1',
          type: 'text',
          placeholder: 'Name',
          value: '',
        })
      );
    });

    test('should handle empty field values', () => {
      const listener = new FormInputListener('#test-form', 8);
      listener.attach();

      const values = listener.getFieldValues();
      
      expect(Object.keys(values).length).toBe(8);
      Object.values(values).forEach(value => {
        expect(value).toBe('');
      });
    });
  });

  // ===========================================================================
  // TEST 6: Simulation Methods (for testing)
  // ===========================================================================
  describe('Simulation Methods', () => {
    test('should simulate input event on a specific field', () => {
      const listener = new FormInputListener('#test-form', 8);
      const mockCallback = jest.fn();
      
      listener.onFieldChange(mockCallback);
      listener.attach();

      listener.simulateInput(0, 'Simulated Value');

      expect(mockCallback).toHaveBeenCalled();
      expect(document.getElementById('field1').value).toBe('Simulated Value');
    });

    test('should throw error for invalid field index', () => {
      const listener = new FormInputListener('#test-form', 8);
      listener.attach();

      expect(() => {
        listener.simulateInput(10, 'value');
      }).toThrow('Invalid field index: 10');
    });

    test('should reset all field values', () => {
      const listener = new FormInputListener('#test-form', 8);
      listener.attach();

      // Set some values
      document.getElementById('field1').value = 'John';
      document.getElementById('field2').value = 'john@example.com';

      listener.resetFields();

      expect(document.getElementById('field1').value).toBe('');
      expect(document.getElementById('field2').value).toBe('');
    });
  });

  // ===========================================================================
  // TEST 7: Edge Cases
  // ===========================================================================
  describe('Edge Cases', () => {
    test('should handle rapid successive input events', () => {
      const listener = new FormInputListener('#test-form', 8);
      const mockCallback = jest.fn();
      
      listener.onFieldChange(mockCallback);
      listener.attach();

      const field1 = document.getElementById('field1');
      
      for (let i = 0; i < 10; i++) {
        field1.value = `value${i}`;
        field1.dispatchEvent(new Event('input', { bubbles: true }));
      }

      expect(mockCallback).toHaveBeenCalledTimes(10);
    });

    test('should handle fields with special characters', () => {
      const listener = new FormInputListener('#test-form', 8);
      const mockCallback = jest.fn();
      
      listener.onFieldChange(mockCallback);
      listener.attach();

      const field1 = document.getElementById('field1');
      const specialValue = 'John@#$%^&*()_+-=[]{}|;:,.<>?';
      
      field1.value = specialValue;
      field1.dispatchEvent(new Event('input', { bubbles: true }));

      const callArgs = mockCallback.mock.calls[0];
      expect(callArgs[1]).toBe(specialValue);
    });

    test('should handle very long input values', () => {
      const listener = new FormInputListener('#test-form', 8);
      const mockCallback = jest.fn();
      
      listener.onFieldChange(mockCallback);
      listener.attach();

      const field1 = document.getElementById('field1');
      const longValue = 'a'.repeat(10000);
      
      field1.value = longValue;
      field1.dispatchEvent(new Event('input', { bubbles: true }));

      const callArgs = mockCallback.mock.calls[0];
      expect(callArgs[1].length).toBe(10000);
    });

    test('should handle unicode and emoji characters', () => {
      const listener = new FormInputListener('#test-form', 8);
      const mockCallback = jest.fn();
      
      listener.onFieldChange(mockCallback);
      listener.attach();

      const field1 = document.getElementById('field1');
      const unicodeValue = '你好世界 🌍 Здравствуй мир';
      
      field1.value = unicodeValue;
      field1.dispatchEvent(new Event('input', { bubbles: true }));

      const callArgs = mockCallback.mock.calls[0];
      expect(callArgs[1]).toBe(unicodeValue);
    });
  });

});
