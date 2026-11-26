// Minimal stand-in for the frontend's `hass` object, talking to a real HA websocket.
window.makeHass = async (base, token) => {
  const ws = new WebSocket(base.replace(/^http/, "ws") + "/api/websocket");
  let nextId = 1;
  const pending = new Map();
  const subs = new Map();
  await new Promise((resolve, reject) => {
    ws.onmessage = (ev) => {
      const msg = JSON.parse(ev.data);
      if (msg.type === "auth_required") ws.send(JSON.stringify({ type: "auth", access_token: token }));
      else if (msg.type === "auth_ok") resolve();
      else if (msg.type === "auth_invalid") reject(new Error("auth_invalid"));
    };
  });
  ws.onmessage = (ev) => {
    const msg = JSON.parse(ev.data);
    if (msg.type === "result" && pending.has(msg.id)) {
      const { resolve, reject } = pending.get(msg.id);
      pending.delete(msg.id);
      msg.success ? resolve(msg.result) : reject(msg.error);
    } else if (msg.type === "event" && subs.has(msg.id)) subs.get(msg.id)(msg.event);
  };
  const send = (msg) =>
    new Promise((resolve, reject) => {
      const id = nextId++;
      pending.set(id, { resolve, reject });
      ws.send(JSON.stringify({ ...msg, id }));
    });
  window.__calls = [];
  return {
    connection: {
      sendMessagePromise: send,
      subscribeMessage: async (cb, msg) => {
        const id = nextId;
        subs.set(id, cb);
        await send(msg);
        return () => subs.delete(id);
      },
    },
    callService: (domain, service, service_data, target) => {
      window.__calls.push(service);
      return send({ type: "call_service", domain, service, service_data, target });
    },
  };
};
