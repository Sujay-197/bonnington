// WebSocket link to the backend on 127.0.0.1. Reconnects every second while down.
export function connect(url, onEvent) {
  let ws;
  function open() {
    ws = new WebSocket(url);
    ws.onmessage = (m) => { try { onEvent(JSON.parse(m.data)); } catch { /* ignore bad frames */ } };
    ws.onclose = () => setTimeout(open, 1000);
    ws.onerror = () => ws.close();
  }
  open();
}
