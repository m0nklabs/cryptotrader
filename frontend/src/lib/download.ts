/**
 * Trigger a file download in the browser.
 *
 * @param blob - The file content as a Blob
 * @param filename - The name to save the file as
 */
export function downloadBlob(blob: Blob, filename: string): void {
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  window.URL.revokeObjectURL(url);
}

/**
 * Download data as a JSON file.
 *
 * @param data - The data to export (will be JSON.stringify'd)
 * @param filename - The name to save the file as
 */
export function downloadJSON(data: any, filename: string): void {
  const json = JSON.stringify(data, null, 2);
  const blob = new Blob([json], { type: 'application/json' });
  downloadBlob(blob, filename);
}

/**
 * Download text content as a file.
 *
 * @param content - The text content to save
 * @param filename - The name to save the file as
 * @param mimeType - The MIME type (default: text/plain)
 */
export function downloadText(content: string, filename: string, mimeType: string = 'text/plain'): void {
  const blob = new Blob([content], { type: mimeType });
  downloadBlob(blob, filename);
}

/**
 * Download CSV content.
 *
 * @param content - The CSV content as a string
 * @param filename - The name to save the file as
 */
export function downloadCSV(content: string, filename: string): void {
  downloadText(content, filename, 'text/csv');
}
