function getConfig() {
  return browser.storage.local.get(['token', 'port']);
}

async function queueUrl(url) {
  const cfg = await getConfig();
  const token = cfg.token || '';
  const port = cfg.port || 8765;
  if (!token) {
    browser.runtime.openOptionsPage();
    return;
  }
  const endpoint = `http://127.0.0.1:${port}/queue?url=${encodeURIComponent(url)}&token=${encodeURIComponent(token)}`;
  try {
    const res = await fetch(endpoint);
    const data = await res.json();
    if (data && data.ok) {
      browser.notifications.create({
        type: 'basic',
        title: 'Chrisnov Media Toolkit',
        message: 'Queued: ' + (data.queued || url)
      });
    } else {
      throw new Error((data && data.error) || 'Unknown error');
    }
  } catch (e) {
    browser.notifications.create({
      type: 'basic',
      title: 'Chrisnov Media Toolkit',
      message: 'Failed to queue: ' + e.message
    });
  }
}

browser.contextMenus.create({
  id: 'cmt-queue-link',
  title: 'Download with Chrisnov Media Toolkit',
  contexts: ['link']
});

browser.contextMenus.create({
  id: 'cmt-queue-page',
  title: 'Download page with Chrisnov Media Toolkit',
  contexts: ['page']
});

browser.contextMenus.onClicked.addListener((info) => {
  const url = info.linkUrl || info.pageUrl;
  if (url) queueUrl(url);
});
