import React, { useState } from 'react';
import { Bell, Send, Settings } from 'lucide-react';
import { TelegramSetup } from './TelegramSetup';
import { DiscordSetup } from './DiscordSetup';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

interface NotificationSettings {
  telegram_enabled: boolean;
  discord_enabled: boolean;
  telegram_configured: boolean;
}

export function NotificationSettings() {
  const [settings, setSettings] = useState<NotificationSettings>({
    telegram_enabled: false,
    discord_enabled: false,
    telegram_configured: false,
  });
  const [showTelegramSetup, setShowTelegramSetup] = useState(false);
  const [showDiscordSetup, setShowDiscordSetup] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [isTesting, setIsTesting] = useState(false);

  // Fetch current settings
  React.useEffect(() => {
    fetchSettings();
  }, []);

  const fetchSettings = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/notifications/settings`);
      if (response.ok) {
        const data = await response.json();
        setSettings(data);
      }
    } catch (error) {
      console.error('Failed to fetch notification settings:', error);
    }
  };

  const handleSave = async () => {
    setIsSaving(true);

    try {
      const response = await fetch(`${API_BASE_URL}/notifications/settings`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          telegram_enabled: settings.telegram_enabled,
          discord_enabled: settings.discord_enabled,
        }),
      });

      if (!response.ok) {
        throw new Error('Failed to save settings');
      }

      alert('Notification settings saved successfully');
    } catch (error) {
      console.error('Failed to save settings:', error);
      alert('Failed to save settings. Please try again.');
    } finally {
      setIsSaving(false);
    }
  };

  const handleTest = async (channel: 'telegram' | 'discord') => {
    setIsTesting(true);

    try {
      const response = await fetch(`${API_BASE_URL}/notifications/test/${channel}`, {
        method: 'POST',
      });

      if (!response.ok) {
        throw new Error('Test notification failed');
      }

      alert(`Test notification sent to ${channel}!`);
    } catch (error) {
      console.error('Test notification failed:', error);
      alert(`Failed to send test notification to ${channel}. Check your configuration.`);
    } finally {
      setIsTesting(false);
    }
  };

  return (
    <div className="bg-gray-900 rounded-lg p-6 border border-gray-700">
      <div className="flex items-center gap-2 mb-6">
        <Bell className="w-5 h-5 text-gray-400" />
        <h2 className="text-lg font-semibold text-gray-200">Notification Settings</h2>
      </div>

      <div className="space-y-6">
        {/* Telegram */}
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <label className="text-sm font-medium text-gray-300">Telegram</label>
              {settings.telegram_configured && (
                <span className="text-xs text-green-500">Configured</span>
              )}
              {!settings.telegram_configured && (
                <span className="text-xs text-yellow-500">Not configured</span>
              )}
            </div>
            <div className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={settings.telegram_enabled}
                onChange={(e) =>
                  setSettings({ ...settings, telegram_enabled: e.target.checked })
                }
                className="rounded bg-gray-800 border-gray-700 text-blue-600 focus:ring-blue-600 focus:ring-offset-gray-900"
                disabled={!settings.telegram_configured}
              />
              <span className="text-xs text-gray-400">Enable</span>
            </div>
          </div>

          <div className="flex gap-2">
            <button
              onClick={() => setShowTelegramSetup(true)}
              className="flex items-center gap-2 px-3 py-2 rounded bg-gray-800 text-gray-300 hover:bg-gray-700 transition-colors text-sm"
            >
              <Settings className="w-4 h-4" />
              Configure
            </button>
            {settings.telegram_configured && (
              <button
                onClick={() => handleTest('telegram')}
                disabled={isTesting || !settings.telegram_enabled}
                className="flex items-center gap-2 px-3 py-2 rounded bg-blue-600 text-white hover:bg-blue-700 transition-colors text-sm disabled:opacity-50 disabled:cursor-not-allowed"
              >
                <Send className="w-4 h-4" />
                Test
              </button>
            )}
          </div>
        </div>

        {/* Discord */}
        <div className="space-y-3 pt-6 border-t border-gray-800">
          <div className="flex items-center justify-between">
            <label className="text-sm font-medium text-gray-300">Discord</label>
            <div className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={settings.discord_enabled}
                onChange={(e) =>
                  setSettings({ ...settings, discord_enabled: e.target.checked })
                }
                className="rounded bg-gray-800 border-gray-700 text-blue-600 focus:ring-blue-600 focus:ring-offset-gray-900"
              />
              <span className="text-xs text-gray-400">Enable</span>
            </div>
          </div>

          <div className="flex gap-2">
            <button
              onClick={() => setShowDiscordSetup(true)}
              className="flex items-center gap-2 px-3 py-2 rounded bg-gray-800 text-gray-300 hover:bg-gray-700 transition-colors text-sm"
            >
              <Settings className="w-4 h-4" />
              Configure
            </button>
            <button
              onClick={() => handleTest('discord')}
              disabled={isTesting || !settings.discord_enabled}
              className="flex items-center gap-2 px-3 py-2 rounded bg-blue-600 text-white hover:bg-blue-700 transition-colors text-sm disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <Send className="w-4 h-4" />
              Test
            </button>
          </div>
        </div>

        {/* Save Button */}
        <div className="pt-6 border-t border-gray-800">
          <button
            onClick={handleSave}
            disabled={isSaving}
            className="w-full px-4 py-2 rounded bg-blue-600 text-white hover:bg-blue-700 transition-colors text-sm disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isSaving ? 'Saving...' : 'Save Settings'}
          </button>
        </div>
      </div>

      {/* Setup Modals */}
      {showTelegramSetup && (
        <TelegramSetup
          onClose={() => {
            setShowTelegramSetup(false);
            fetchSettings();
          }}
        />
      )}
      {showDiscordSetup && (
        <DiscordSetup
          onClose={() => {
            setShowDiscordSetup(false);
            fetchSettings();
          }}
        />
      )}
    </div>
  );
}
