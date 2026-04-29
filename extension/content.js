// Extract readable text from the current webpage
function extractPageText() {
    return document.body.innerText || document.body.textContent || "";
}

let sidebarIframe = null;

// Listen for messages from the background script or sidebar
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    if (request.action === "toggle_sidebar") {
        if (sidebarIframe) {
            // Toggle visibility
            if (sidebarIframe.style.display === "none") {
                sidebarIframe.style.display = "block";
                document.body.style.paddingRight = "min(380px, 100vw)";
            } else {
                sidebarIframe.style.display = "none";
                document.body.style.paddingRight = "0px";
            }
        } else {
            // Create the sidebar iframe
            sidebarIframe = document.createElement("iframe");
            sidebarIframe.src = chrome.runtime.getURL("sidebar.html");
            sidebarIframe.id = "clausewise-sidebar";
            
            // Style the iframe
            Object.assign(sidebarIframe.style, {
                position: "fixed",
                top: "0",
                right: "0",
                width: "min(380px, 100vw)",
                height: "100vh",
                border: "none",
                borderLeft: "1px solid rgba(255,255,255,0.1)",
                zIndex: "2147483647",
                boxShadow: "-5px 0 15px rgba(0,0,0,0.3)",
                display: "block",
                backgroundColor: "#1a1d29",
                colorScheme: "dark"
            });
            
            document.body.appendChild(sidebarIframe);
            document.body.style.paddingRight = "min(380px, 100vw)";
        }
        sendResponse({status: "success"});
    }

    if (request.action === "extract_text") {
        sendResponse({ text: extractPageText(), url: window.location.href });
    }
    
    if (request.action === "close_sidebar") {
        if (sidebarIframe) {
            sidebarIframe.style.display = "none";
            document.body.style.paddingRight = "0px";
        }
        sendResponse({status: "success"});
    }

    if (request.action === "highlight_phrases") {
        const phrases = request.phrases || [];
        if (phrases.length === 0) return;

        // Extremely safe TreeWalker approach to highlight phrases in text nodes
        // without breaking existing HTML elements, event listeners, or React states.
        const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, null, false);
        let node;
        const nodesToReplace = [];

        while (node = walker.nextNode()) {
            // Skip text inside scripts, styles, or the iframe itself
            if (node.parentNode && (
                node.parentNode.nodeName === "SCRIPT" || 
                node.parentNode.nodeName === "STYLE" || 
                node.parentNode.id === "clausewise-sidebar" ||
                node.parentNode.nodeName === "NOSCRIPT"
            )) continue;

            const text = node.nodeValue;
            let shouldReplace = false;
            let newHtml = text;

            phrases.forEach(phrase => {
                // Use a simple case-insensitive search
                const regex = new RegExp(`(${phrase})`, "gi");
                if (regex.test(newHtml)) {
                    shouldReplace = true;
                    // Add the visual styling inline
                    newHtml = newHtml.replace(regex, `<mark style="background-color: rgba(245, 158, 11, 0.4); border-bottom: 2px solid #ef4444; color: inherit; border-radius: 2px;">$1</mark>`);
                }
            });

            if (shouldReplace) {
                nodesToReplace.push({ node: node, html: newHtml });
            }
        }

        // Apply replacements after traversal to avoid DOM mutation errors
        nodesToReplace.forEach(item => {
            const span = document.createElement("span");
            span.innerHTML = item.html;
            item.node.parentNode.replaceChild(span, item.node);
        });
        
        console.log(`ClauseWise: Highlighted ${nodesToReplace.length} risky phrases.`);
        sendResponse({status: "success"});
    }

    if (request.action === "scrollToSection") {
        const textToFind = request.sectionText;
        if (!textToFind) {
            sendResponse({status: "failed"});
            return;
        }

        // Reset any previous selection
        window.getSelection().removeAllRanges();

        // Find the text in the page
        const found = window.find(textToFind, false, false, true, false, true, false);
        
        if (found) {
            const selection = window.getSelection();
            if (selection.rangeCount > 0) {
                const range = selection.getRangeAt(0);
                
                // Only wrap if the selection doesn't already cross node boundaries
                // (window.find can select text across multiple nodes, which surroundContents fails on)
                try {
                    const span = document.createElement('span');
                    span.style.backgroundColor = 'rgba(250, 204, 21, 0.5)'; // bright yellow tint
                    span.style.borderBottom = '2px solid #eab308';
                    span.style.padding = '2px 0';
                    span.style.borderRadius = '2px';
                    span.style.transition = 'background-color 1s ease-in-out';
                    
                    range.surroundContents(span);
                    
                    // Scroll into view
                    span.scrollIntoView({ behavior: 'smooth', block: 'center' });
                    
                    // Pulse animation effect
                    setTimeout(() => { span.style.backgroundColor = 'transparent'; }, 2000);
                } catch (e) {
                    // Fallback: If it crosses boundaries, just scroll to the start of the selection
                    const anchorNode = selection.anchorNode;
                    if (anchorNode && anchorNode.parentElement) {
                        anchorNode.parentElement.scrollIntoView({ behavior: 'smooth', block: 'center' });
                    }
                }
            }
        }
        sendResponse({status: "success"});
    }
});
