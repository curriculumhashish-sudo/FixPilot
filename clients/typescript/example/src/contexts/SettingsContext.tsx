import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import { Settings } from '../components/SettingsModal';
import { loadSettings, saveSettings, isFirstVisit, markVisited } from '../utils/settings';

interface SettingsContextType {
  settings: Settings;
  updateSettings: (newSettings: Settings) => void;
  isModalOpen: boolean;
  openModal: () => void;
  closeModal: () => void;
  isFirstVisit: boolean;
}

const SettingsContext = createContext<SettingsContextType | undefined>(undefined);

interface SettingsProviderProps {
  children: ReactNode;
}

export const SettingsProvider: React.FC<SettingsProviderProps> = ({ children }) => {
  const [settings, setSettings] = useState<Settings>(loadSettings());
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [firstVisit, setFirstVisit] = useState(true);

  useEffect(() => {
    // 检查这是否是第一次访问
    const isFirst = isFirstVisit();
    setFirstVisit(isFirst);
    
    if (isFirst) {
      // 首次访问时打开模式
      setIsModalOpen(true);
      // 标记为已访问
      markVisited();
    }
  }, []);

  const updateSettings = (newSettings: Settings) => {
    setSettings(newSettings);
    saveSettings(newSettings);
  };

  const openModal = () => {
    setIsModalOpen(true);
  };

  const closeModal = () => {
    setIsModalOpen(false);
  };

  const value: SettingsContextType = {
    settings,
    updateSettings,
    isModalOpen,
    openModal,
    closeModal,
    isFirstVisit: firstVisit,
  };

  return (
    <SettingsContext.Provider value={value}>
      {children}
    </SettingsContext.Provider>
  );
};

export const useSettings = (): SettingsContextType => {
  const context = useContext(SettingsContext);
  if (context === undefined) {
    throw new Error('useSettings must be used within a SettingsProvider');
  }
  return context;
};