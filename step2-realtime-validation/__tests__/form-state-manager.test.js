/**
 * Jest Tests for FormStateManager (Module 2)
 */

const FormStateManager = require('../modules/form-state-manager');

describe('FormStateManager - Module 2: Form State Manager', () => {

  beforeEach(() => {
    localStorage.clear();
    jest.clearAllMocks();
  });

  afterEach(() => {
    localStorage.clear();
  });

  // ===========================================================================
  // TEST 1: Initialization
  // ===========================================================================
  describe('Initialization', () => {
    test('should create instance with correct parameters', () => {
      const manager = new FormStateManager('test-form', 8);

      expect(manager.formName).toBe('test-form');
      expect(manager.fieldCount).toBe(8);
      expect(manager.useLocalStorage).toBe(true);
      expect(manager.isDirty).toBe(false);
    });

    test('should initialize state with 8 empty fields', () => {
      const manager = new FormStateManager('test-form', 8);
      const state = manager.getState();

      expect(Object.keys(state).length).toBe(8);
      expect(state.field1).toBe('');
      expect(state.field8).toBe('');
    });

    test('should create correct storage key', () => {
      const manager = new FormStateManager('my-form', 8);
      
      expect(manager.storageKey).toBe('form_state_my-form');
    });

    test('should allow disabling localStorage', () => {
      const manager = new FormStateManager('test-form', 8, false);
      
      expect(manager.useLocalStorage).toBe(false);
    });
  });

  // ===========================================================================
  // TEST 2: State Updates
  // ===========================================================================
  describe('State Updates', () => {
    test('should update single field value', () => {
      const manager = new FormStateManager('test-form', 8);

      manager.updateState('field1', 'John Doe');

      expect(manager.getFieldValue('field1')).toBe('John Doe');
    });

    test('should mark state as dirty after update', () => {
      const manager = new FormStateManager('test-form', 8);

      expect(manager.isDirty).toBe(false);

      manager.updateState('field1', 'value');

      expect(manager.isDirty).toBe(true);
    });

    test('should track last modified timestamp', () => {
      const manager = new FormStateManager('test-form', 8);
      const before = new Date();

      manager.updateState('field1', 'value');

      const after = new Date();
      expect(manager.lastModified).toBeTruthy();
      expect(manager.lastModified.getTime()).toBeGreaterThanOrEqual(before.getTime());
      expect(manager.lastModified.getTime()).toBeLessThanOrEqual(after.getTime());
    });

    test('should update multiple fields at once', () => {
      const manager = new FormStateManager('test-form', 8);

      manager.updateMultiple({
        field1: 'John',
        field2: 'john@example.com',
        field3: '30',
      });

      expect(manager.getFieldValue('field1')).toBe('John');
      expect(manager.getFieldValue('field2')).toBe('john@example.com');
      expect(manager.getFieldValue('field3')).toBe('30');
    });

    test('should not trigger callbacks for no-change updates', () => {
      const manager = new FormStateManager('test-form', 8);
      const callback = jest.fn();

      manager.onStateChange(callback);
      manager.updateState('field1', 'value');
      manager.updateState('field1', 'value');

      expect(callback).toHaveBeenCalledTimes(1);
    });

    test('should add to history on update', () => {
      const manager = new FormStateManager('test-form', 8);

      manager.updateState('field1', 'value1');
      manager.updateState('field1', 'value2');

      const history = manager.getHistory();
      expect(history.length).toBe(2);
      expect(history[0].field).toBe('field1');
      expect(history[0].newValue).toBe('value1');
      expect(history[1].newValue).toBe('value2');
    });
  });

  // ===========================================================================
  // TEST 3: Storage Operations
  // ===========================================================================
  describe('Storage Operations', () => {
    test('should save state to localStorage', () => {
      const manager = new FormStateManager('test-form', 8);

      manager.updateState('field1', 'John');
      manager.updateState('field2', 'john@example.com');
      const saved = manager.saveState();

      expect(saved).toBe(true);
      expect(manager.isDirty).toBe(false);

      const stored = localStorage.getItem('form_state_test-form');
      expect(stored).toBeTruthy();
      
      const data = JSON.parse(stored);
      expect(data.state.field1).toBe('John');
      expect(data.state.field2).toBe('john@example.com');
    });

    test('should load state from localStorage', () => {
      // First manager saves
      const manager1 = new FormStateManager('test-form', 8);
      manager1.updateState('field1', 'John');
      manager1.saveState();

      // Second manager loads
      const manager2 = new FormStateManager('test-form', 8);
      const loaded = manager2.loadState();

      expect(loaded).toBeTruthy();
      expect(loaded.field1).toBe('John');
      expect(manager2.getFieldValue('field1')).toBe('John');
    });

    test('should check if stored state exists', () => {
      const manager = new FormStateManager('test-form', 8);

      expect(manager.hasStoredState()).toBe(false);

      manager.updateState('field1', 'value');
      manager.saveState();

      expect(manager.hasStoredState()).toBe(true);
    });

    test('should return null when loading non-existent state', () => {
      const manager = new FormStateManager('non-existent-form', 8);

      const loaded = manager.loadState();

      expect(loaded).toBeNull();
    });

    test('should clear state from memory and storage', () => {
      const manager = new FormStateManager('test-form', 8);

      manager.updateState('field1', 'value');
      manager.saveState();

      expect(manager.hasStoredState()).toBe(true);
      expect(manager.getFieldValue('field1')).toBe('value');

      manager.clearState();

      expect(manager.hasStoredState()).toBe(false);
      expect(manager.getFieldValue('field1')).toBe('');
      expect(manager.isDirty).toBe(false);
    });

    test('should not save if localStorage is disabled', () => {
      const manager = new FormStateManager('test-form', 8, false);

      manager.updateState('field1', 'value');
      const saved = manager.saveState();

      expect(saved).toBe(false);
      expect(localStorage.getItem('form_state_test-form')).toBeNull();
    });

    test('should get storage data for debugging', () => {
      const manager = new FormStateManager('test-form', 8);

      manager.updateState('field1', 'John');
      manager.saveState();

      const storageData = manager.getStorageData();

      expect(storageData).toBeTruthy();
      expect(storageData.state.field1).toBe('John');
      expect(storageData.formName).toBe('test-form');
    });
  });

  // ===========================================================================
  // TEST 4: Callbacks
  // ===========================================================================
  describe('Callbacks', () => {
    test('should trigger state change callback', () => {
      const manager = new FormStateManager('test-form', 8);
      const callback = jest.fn();

      manager.onStateChange(callback);
      manager.updateState('field1', 'value');

      expect(callback).toHaveBeenCalledTimes(1);
      expect(callback).toHaveBeenCalledWith(
        'field1',
        'value',
        expect.objectContaining({ field1: 'value' })
      );
    });

    test('should handle multiple state change callbacks', () => {
      const manager = new FormStateManager('test-form', 8);
      const callback1 = jest.fn();
      const callback2 = jest.fn();

      manager.onStateChange(callback1);
      manager.onStateChange(callback2);
      manager.updateState('field1', 'value');

      expect(callback1).toHaveBeenCalledTimes(1);
      expect(callback2).toHaveBeenCalledTimes(1);
    });

    test('should trigger save callback on successful save', () => {
      const manager = new FormStateManager('test-form', 8);
      const callback = jest.fn();

      manager.onSave(callback);
      manager.updateState('field1', 'value');
      manager.saveState();

      expect(callback).toHaveBeenCalledWith(true, 'form_state_test-form');
    });

    test('should reject non-function callbacks', () => {
      const manager = new FormStateManager('test-form', 8);

      expect(() => {
        manager.onStateChange('not a function');
      }).toThrow('Callback must be a function');
    });

    test('should handle callback errors gracefully', () => {
      const manager = new FormStateManager('test-form', 8);
      const errorCallback = jest.fn(() => {
        throw new Error('Callback error');
      });
      const normalCallback = jest.fn();

      manager.onStateChange(errorCallback);
      manager.onStateChange(normalCallback);

      const consoleSpy = jest.spyOn(console, 'error').mockImplementation();

      manager.updateState('field1', 'value');

      expect(errorCallback).toHaveBeenCalled();
      expect(normalCallback).toHaveBeenCalled();

      consoleSpy.mockRestore();
    });
  });

  // ===========================================================================
  // TEST 5: Getters and Utilities
  // ===========================================================================
  describe('Getters and Utilities', () => {
    test('should get state as copy', () => {
      const manager = new FormStateManager('test-form', 8);

      manager.updateState('field1', 'value');
      const state = manager.getState();

      state.field1 = 'modified';

      expect(manager.getFieldValue('field1')).toBe('value');
    });

    test('should get filled fields', () => {
      const manager = new FormStateManager('test-form', 8);

      manager.updateState('field1', 'John');
      manager.updateState('field2', 'john@example.com');
      manager.updateState('field3', '');

      const filled = manager.getFilledFields();

      expect(filled).toContain('field1');
      expect(filled).toContain('field2');
      expect(filled.length).toBe(2);
    });

    test('should get field count stats', () => {
      const manager = new FormStateManager('test-form', 8);

      manager.updateState('field1', 'John');
      manager.updateState('field2', 'john@example.com');

      const stats = manager.getFieldCountStats();

      expect(stats.filled).toBe(2);
      expect(stats.total).toBe(8);
      expect(stats.percentage).toBe(25);
    });

    test('should validate state', () => {
      const manager = new FormStateManager('test-form', 8);

      expect(manager.isValid()).toBe(true);

      manager.state.extra = 'field';

      expect(manager.isValid()).toBe(false);
    });

    test('should convert to JSON', () => {
      const manager = new FormStateManager('test-form', 8);

      manager.updateState('field1', 'John');
      const json = manager.toJSON();

      expect(json).toBeTruthy();
      expect(json).toContain('test-form');
      expect(json).toContain('John');
    });

    test('should get metadata', () => {
      const manager = new FormStateManager('test-form', 8);

      manager.updateState('field1', 'value');
      manager.saveState();

      const metadata = manager.getMetadata();

      expect(metadata.formName).toBe('test-form');
      expect(metadata.fieldCount).toBe(8);
      expect(metadata.isDirty).toBe(false);
      expect(metadata.hasStoredState).toBe(true);
    });

    test('should get history', () => {
      const manager = new FormStateManager('test-form', 8);

      manager.updateState('field1', 'value1');
      manager.updateState('field1', 'value2');
      manager.updateState('field2', 'value3');

      const history = manager.getHistory();

      expect(history.length).toBe(3);
      expect(history[0].field).toBe('field1');
      expect(history[1].field).toBe('field1');
      expect(history[2].field).toBe('field2');
    });
  });

  // ===========================================================================
  // TEST 6: Edge Cases
  // ===========================================================================
  describe('Edge Cases', () => {
    test('should handle very long field values', () => {
      const manager = new FormStateManager('test-form', 8);
      const longValue = 'a'.repeat(10000);

      manager.updateState('field1', longValue);

      expect(manager.getFieldValue('field1').length).toBe(10000);
    });

    test('should handle special characters', () => {
      const manager = new FormStateManager('test-form', 8);
      const specialValue = '@#$%^&*()_+-=[]{}|;:,.<>?';

      manager.updateState('field1', specialValue);

      expect(manager.getFieldValue('field1')).toBe(specialValue);
    });

    test('should handle unicode characters', () => {
      const manager = new FormStateManager('test-form', 8);
      const unicodeValue = '你好 🌍 مرحبا';

      manager.updateState('field1', unicodeValue);

      expect(manager.getFieldValue('field1')).toBe(unicodeValue);
    });

    test('should preserve state across save/load cycles', () => {
      const manager1 = new FormStateManager('test-form', 8);

      manager1.updateState('field1', 'John');
      manager1.updateState('field2', 'john@example.com');
      manager1.saveState();

      const manager2 = new FormStateManager('test-form', 8);
      manager2.loadState();

      expect(manager2.getFieldValue('field1')).toBe('John');
      expect(manager2.getFieldValue('field2')).toBe('john@example.com');

      manager2.updateState('field3', '30');
      manager2.saveState();

      const manager3 = new FormStateManager('test-form', 8);
      manager3.loadState();

      expect(manager3.getFieldValue('field1')).toBe('John');
      expect(manager3.getFieldValue('field2')).toBe('john@example.com');
      expect(manager3.getFieldValue('field3')).toBe('30');
    });

    test('should handle rapid updates', () => {
      const manager = new FormStateManager('test-form', 8);
      const callback = jest.fn();

      manager.onStateChange(callback);

      for (let i = 0; i < 100; i++) {
        manager.updateState('field1', `value${i}`);
      }

      expect(callback).toHaveBeenCalledTimes(100);
      expect(manager.getFieldValue('field1')).toBe('value99');
    });

    test('should handle multiple forms independently', () => {
      const manager1 = new FormStateManager('form1', 8);
      const manager2 = new FormStateManager('form2', 8);

      manager1.updateState('field1', 'Form 1 Value');
      manager2.updateState('field1', 'Form 2 Value');

      manager1.saveState();
      manager2.saveState();

      const manager1Loaded = new FormStateManager('form1', 8);
      const manager2Loaded = new FormStateManager('form2', 8);

      manager1Loaded.loadState();
      manager2Loaded.loadState();

      expect(manager1Loaded.getFieldValue('field1')).toBe('Form 1 Value');
      expect(manager2Loaded.getFieldValue('field1')).toBe('Form 2 Value');
    });
  });

});
