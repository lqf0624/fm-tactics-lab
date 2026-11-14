'use strict';

const desktopInvoke = window.__TAURI__?.core?.invoke;

async function editorRequest(target, data, asText = false) {
 const body = data === undefined ? undefined : JSON.stringify(data);
 if (desktopInvoke) {
  const result = await desktopInvoke('editor_request', {target, body}).catch(error => {
   throw Error(error?.message || String(error));
  });
  if (result.status >= 400) throw Error(result.data?.error || '请求失败');
  return result.data;
 }
 const response = await fetch(target, body === undefined ? {} : {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body
 });
 if (!response.ok) {
  const error = await response.json();
  throw Error(error.error || '请求失败');
 }
 return asText ? response.text() : response.json();
}
