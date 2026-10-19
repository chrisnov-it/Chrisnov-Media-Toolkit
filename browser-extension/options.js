document.addEventListener('DOMContentLoaded', () => {
  const tokenInput = document.getElementById('token');
  const portInput = document.getElementById('port');
  const status = document.getElementById('status');

  browser.storage.local.get(['token', 'port']).then((res) => {
    if (res.token) tokenInput.value = res.token;
    if (res.port) portInput.value = res.port;
  });

  document.getElementById('save').addEventListener('click', () => {
    const token = tokenInput.value.trim();
    const port = parseInt(portInput.value, 10) || 8765;
    browser.storage.local.set({ token, port }).then(() => {
      status.textContent = 'Saved.';
      setTimeout(() => { status.textContent = ''; }, 2000);
    });
  });
});
