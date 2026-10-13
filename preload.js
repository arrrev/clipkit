'use strict';
const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('clipkit', {
  // history
  getHistory: () => ipcRenderer.invoke('history:get'),
  copy: (text) => ipcRenderer.invoke('history:copy', text),
  copyImage: (hash) => ipcRenderer.invoke('history:copyImage', hash),
  togglePin: (text) => ipcRenderer.invoke('history:togglePin', text),
  togglePinImage: (hash) => ipcRenderer.invoke('history:togglePinImage', hash),
  deleteItem: (text) => ipcRenderer.invoke('history:delete', text),
  deleteImage: (hash) => ipcRenderer.invoke('history:deleteImage', hash),
  clearHistory: () => ipcRenderer.invoke('history:clear'),
  transformFrom: (text) => ipcRenderer.invoke('history:transform', text),
  onHistoryUpdate: (cb) => ipcRenderer.on('history:update', (_e, items) => cb(items)),

  // clipboard
  readClipboard: () => ipcRenderer.invoke('clipboard:read'),
  writeClipboard: (text) => ipcRenderer.invoke('clipboard:write', text),

  // transform window
  onTransformSeed: (cb) => ipcRenderer.on('transform:seed', (_e, text) => cb(text)),

  // settings
  getSettings: () => ipcRenderer.invoke('settings:get'),
  setSettings: (patch) => ipcRenderer.invoke('settings:set', patch),
  getTransformList: () => ipcRenderer.invoke('settings:transforms'),
  onSettingsLoad: (cb) => ipcRenderer.on('settings:load', (_e, s) => cb(s)),

  // output
  saveOutput: (text, ext) => ipcRenderer.invoke('output:save', text, ext),

  // window
  hideWindow: () => ipcRenderer.invoke('window:hide')
});
