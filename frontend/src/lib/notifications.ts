/**
 * Browser notification wrapper for Web Notifications API.
 */

/**
 * Request browser notification permission.
 */
export async function requestNotificationPermission(): Promise<NotificationPermission> {
  if (!('Notification' in window)) {
    console.warn('Browser does not support notifications')
    return 'denied'
  }

  if (Notification.permission === 'granted') {
    return 'granted'
  }

  if (Notification.permission !== 'denied') {
    const permission = await Notification.requestPermission()
    return permission
  }

  return Notification.permission
}

/**
 * Check if browser notifications are supported and permitted.
 */
export function isNotificationSupported(): boolean {
  return 'Notification' in window && Notification.permission === 'granted'
}

/**
 * Show a browser notification.
 */
export function showNotification(title: string, options?: NotificationOptions): Notification | null {
  if (!isNotificationSupported()) {
    console.warn('Notifications not supported or not permitted')
    return null
  }

  try {
    const notification = new Notification(title, {
      icon: '/favicon.ico',
      badge: '/favicon.ico',
      ...options,
    })

    // Auto-close after 10 seconds
    setTimeout(() => notification.close(), 10000)

    return notification
  } catch (error) {
    console.error('Failed to show notification:', error)
    return null
  }
}

/**
 * Show an alert notification.
 */
export function showAlertNotification(
  symbol: string,
  message: string,
  options?: { price?: number; type?: string }
): Notification | null {
  const title = `🔔 Alert: ${symbol}`
  const body = options?.price
    ? `${message}\nPrice: $${options.price.toFixed(2)}`
    : message

  return showNotification(title, {
    body,
    tag: `alert-${symbol}`,
    requireInteraction: false,
    ...options,
  })
}
