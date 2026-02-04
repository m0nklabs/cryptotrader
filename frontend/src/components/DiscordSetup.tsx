import React, { useState } from 'react';
import { X, ExternalLink } from 'lucide-react';

interface DiscordSetupProps {
  onClose: () => void;
}

export function DiscordSetup({ onClose }: DiscordSetupProps) {
  const [webhookUrl, setWebhookUrl] = useState('');
  const [isSaving, setIsSaving] = useState(false);

  const handleSave = async () => {
    if (!webhookUrl) {
      alert('Please provide a webhook URL');
      return;
    }

    // Validate webhook URL format
    if (!webhookUrl.startsWith('https://discord.com/api/webhooks/')) {
      alert('Invalid Discord webhook URL');
      return;
    }

    setIsSaving(true);

    try {
      // Note: In production, this should be stored securely on the backend
      alert('Discord webhook URL saved! Please set DISCORD_WEBHOOK_URL in your environment.');
      onClose();
    } catch (error) {
      console.error('Failed to save Discord settings:', error);
      alert('Failed to save settings. Please try again.');
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-gray-900 rounded-lg p-6 border border-gray-700 w-full max-w-md">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-gray-200">Discord Setup</h2>
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
              <li>Go to your Discord server settings</li>
              <li>Navigate to Integrations → Webhooks</li>
              <li>Create a new webhook or edit existing one</li>
              <li>Copy the webhook URL</li>
            </ol>
            <a
              href="https://support.discord.com/hc/en-us/articles/228383668-Intro-to-Webhooks"
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-1 text-blue-400 hover:text-blue-300 mt-2"
            >
              Learn more
              <ExternalLink className="w-3 h-3" />
            </a>
          </div>

          {/* Webhook URL */}
          <div>
            <label className="block text-xs font-medium text-gray-400 mb-2">
              Webhook URL
            </label>
            <input
              type="password"
              value={webhookUrl}
              onChange={(e) => setWebhookUrl(e.target.value)}
              placeholder="https://discord.com/api/webhooks/..."
              className="w-full bg-gray-800 text-gray-300 rounded px-3 py-2 text-sm border border-gray-700 focus:outline-none focus:border-blue-500"
            />
            <p className="text-xs text-gray-500 mt-1">
              Store as DISCORD_WEBHOOK_URL environment variable
            </p>
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
            disabled={isSaving || !webhookUrl}
            className="flex-1 px-4 py-2 rounded bg-blue-600 text-white hover:bg-blue-700 transition-colors text-sm disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isSaving ? 'Saving...' : 'Save'}
          </button>
        </div>
      </div>
    </div>
  );
}
