import { Settings } from '../components/SettingsModal';

const SETTINGS_KEY = 'openhands-settings';
const FIRST_VISIT_KEY = 'openhands-first-visit';

export const DEFAULT_SETTINGS: Settings = {
  agentServerUrl: 'http://localhost:8000',
  modelName: 'gpt-4',
  apiKey: '',
  agentServerApiKey: ''
};

/**
 * 从 localStorage 加载设置
 */
export const loadSettings = (): Settings => {
  try {
    const stored = localStorage.getItem(SETTINGS_KEY);
    if (stored) {
      const parsed = JSON.parse(stored);
      // 与默认值合并以确保所有必填字段都存在
      return { ...DEFAULT_SETTINGS, ...parsed };
    }
  } catch (error) {
    console.warn('Failed to load settings from localStorage:', error);
  }
  return DEFAULT_SETTINGS;
};

/**
 * 将设置保存到 localStorage
 */
export const saveSettings = (settings: Settings): void => {
  try {
    localStorage.setItem(SETTINGS_KEY, JSON.stringify(settings));
  } catch (error) {
    console.error('Failed to save settings to localStorage:', error);
  }
};

/**
 * 检查这是否是用户第一次访问
 */
export const isFirstVisit = (): boolean => {
  try {
    return !localStorage.getItem(FIRST_VISIT_KEY);
  } catch (error) {
    console.warn('Failed to check first visit status:', error);
    return true; // 如果我们无法检查，则默认为首次访问
  }
};

/**
 * 标记用户已访问该应用
 */
export const markVisited = (): void => {
  try {
    localStorage.setItem(FIRST_VISIT_KEY, 'true');
  } catch (error) {
    console.error('Failed to mark app as visited:', error);
  }
};

/**
 * 检查是否配置了设置（具有非默认值）
 */
export const areSettingsConfigured = (settings: Settings): boolean => {
  return (
    settings.agentServerUrl !== DEFAULT_SETTINGS.agentServerUrl ||
    settings.modelName !== DEFAULT_SETTINGS.modelName ||
    settings.apiKey !== DEFAULT_SETTINGS.apiKey ||
    settings.agentServerApiKey !== DEFAULT_SETTINGS.agentServerApiKey
  );
};

/**
 * 清除所有存储的设置和首次访问标志
 */
export const clearAllSettings = (): void => {
  try {
    localStorage.removeItem(SETTINGS_KEY);
    localStorage.removeItem(FIRST_VISIT_KEY);
  } catch (error) {
    console.error('Failed to clear settings:', error);
  }
};