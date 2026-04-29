chrome.action.onClicked.addListener((tab) => {
    // Prevent errors on chrome:// and other restricted URLs
    if (tab.url && (tab.url.startsWith("chrome://") || tab.url.startsWith("edge://") || tab.url.startsWith("about:"))) {
        console.warn("ClauseWise cannot run on restricted browser pages.");
        return;
    }

    // Send a message to the content script in the active tab
    chrome.tabs.sendMessage(tab.id, { action: "toggle_sidebar" }).catch(err => {
        console.warn("Could not toggle sidebar. The page may need to be refreshed.", err);
    });
});
