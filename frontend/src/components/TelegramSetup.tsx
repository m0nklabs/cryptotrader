import React, { useState } from 'react';
import { X, ExternalLink } from 'lucide-react';

interface TelegramSetupProps {
  onClose: () => void;
}

export function TelegramSetup({ onClose }: TelegramSetupProps) {
  const [botToken, setBotToken] = useState('');
  const [chatId, setChatId] = useState('');
  const [isSaving, setIsSaving] = useState(false);

  const handleSave = async () => {
    if (!botToken || !chatId) {
      alert('Please provide both bot token and chat ID');
      return;
    }

    setIsSaving(true);

    try {
      // Note: In production, this should be stored securely on the backend
      // For now, we'll just update the settings with the chat ID
      const response = await fetch(`${import.meta.env.VITE_API_URL || 'http://localhost:8000'}/notifications/settings`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          telegram_enabled: true,
          telegram_chat_id: chatId,
        }),
      });

      if (!response.ok) {
        throw new Error('Failed to save Telegram settings');
      }

      alert('Telegram settings saved! Please set TELEGRAM_BOT_TOKEN in your environment.');
      onClose();
    } catch (error) {
      console.error('Failed to save Telegram settings:', error);
      alert('Failed to save settings. Please try again.');
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-gray-900 rounded-lg p-6 border border-gray-700 w-full max-w-md">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-gray-200">Telegram Setup</h2>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-300 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="space-y-4">
          {/* Instructions */}
          <div className="bg-gray-800 rounded p-4 space-y-2 text-xs text-gray-400">
            <p className="font-medium text-gray-300">Setup Instructions:</p>
            <ol className="list-decimal list-inside space-y-1">
              <li>Create a bot with @BotFather on Telegram</li>
              <li>Copy the bot token</li>
              <li>Send a message to your bot</li>
              <li>Get your chat ID from @userinfobot</li>
            </ol>
            <a
              href="https://core.telegram.org/bots#how-do-i-create-a-bot"
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-1 text-blue-400 hover:text-blue-300 mt-2"
            >
              Learn more
              <ExternalLink className="w-3 h-3" />
            </a>
          </div>

          {/* Bot Token */}
          <div>
            <label className="block text-xs font-medium text-gray-400 mb-2">
              Bot Token
            </label>
            <input
              type="password"
              value={botToken}
              onChange={(e) => setBotToken(e.target.value)}
              placeholder="1234567890:ABCdefGHIjklMNOpqrsTUVwxyz"
              className="w-full bg-gray-800 text-gray-300 rounded px-3 py-2 text-sm border border-gray-700 focus:outline-none focus:border-blue-500"
            />
            <p className="text-xs text-gray-500 mt-1">
              Store as TELEGRAM_BOT_TOKEN environment variable
            </p>
          </div>

          {/* Chat ID */}
          <div>
            <label className="block text-xs font-medium text-gray-400 mb-2">
              Chat ID
            </label>
            <input
              type="text"
              value={chatId}
              onChange={(e) => setChatId(e.target.value)}
              placeholder="123456789"
              className="w-full bg-gray-800 text-gray-300 rounded px-3 py-2 text-sm border border-gray-700 focus:outline-none focus:border-blue-500"
            />
          </div>
        </div>

        {/* Actions */}
        <div className="flex gap-2 mt-6">
          <button
            onClick={onClose}
            disabled={isSaving}
            className="flex-1 px-4 py-2 rounded bg-gray-800 text-gray-300 hover:bg-gray-700 transition-colors text-sm disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Cancel
          </button>
          <button
            onClick={handleSave}
            disabled={isSaving || !botToken || !chatId}
            className="flex-1 px-4 py-2 rounded bg-blue-600 text-white hover:bg-blue-700 transition-colors text-sm disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isSaving ? 'Saving...' : 'Save'}
          </button>
        </div>
      </div>
    </div>
  );
}
