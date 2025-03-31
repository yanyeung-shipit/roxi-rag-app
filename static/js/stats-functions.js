/**
 * Knowledge Base Stats Functions
 * These functions handle fetching and displaying knowledge base statistics
 */

// Fetch and display knowledge base stats
async function fetchStats() {
    const statsContent = document.getElementById('statsContent');
    if (!statsContent) return;
    
    try {
        const response = await fetch('/stats');
        const data = await response.json();
        
        if (data.success) {
            statsContent.innerHTML = `
                <ul class="list-group list-group-flush bg-transparent">
                    <li class="list-group-item bg-transparent d-flex justify-content-between">
                        <span>Total Documents:</span>
                        <span class="badge bg-primary rounded-pill">${data.stats.total_documents}</span>
                    </li>
                    <li class="list-group-item bg-transparent d-flex justify-content-between">
                        <span>Website Sources:</span>
                        <span class="badge bg-info rounded-pill">${data.stats.websites}</span>
                    </li>
                    <li class="list-group-item bg-transparent d-flex justify-content-between">
                        <span>PDF Documents:</span>
                        <span class="badge bg-warning rounded-pill">${data.stats.pdfs}</span>
                    </li>
                    <li class="list-group-item bg-transparent d-flex justify-content-between">
                        <span>Text Chunks:</span>
                        <span class="badge bg-success rounded-pill">${data.stats.chunks}</span>
                    </li>
                </ul>
            `;
            
            // Setup clear knowledge base button if it exists
            const clearKnowledgeBtn = document.getElementById('clearKnowledgeBtn');
            if (clearKnowledgeBtn) {
                clearKnowledgeBtn.addEventListener('click', clearKnowledgeBase);
            }
        } else {
            statsContent.innerHTML = `
                <div class="alert alert-danger" role="alert">
                    <i class="fas fa-exclamation-circle me-2"></i>
                    Error: ${data.message}
                </div>
            `;
        }
    } catch (error) {
        statsContent.innerHTML = `
            <div class="alert alert-danger" role="alert">
                <i class="fas fa-exclamation-circle me-2"></i>
                Error: ${error.message}
            </div>
        `;
    }
}

// Clear the knowledge base
async function clearKnowledgeBase() {
    if (!confirm('Are you sure you want to clear the entire knowledge base? This will delete ALL documents and cannot be undone.')) {
        return;
    }
    
    const statsContent = document.getElementById('statsContent');
    const clearBtn = document.getElementById('clearKnowledgeBtn');
    
    if (clearBtn) {
        clearBtn.disabled = true;
        clearBtn.innerHTML = `<i class="fas fa-spinner fa-spin me-1"></i> Clearing...`;
    }
    
    try {
        const response = await fetch('/clear', {
            method: 'POST'
        });
        const data = await response.json();
        
        if (data.success) {
            if (statsContent) {
                statsContent.innerHTML = `
                    <div class="alert alert-success" role="alert">
                        <i class="fas fa-check-circle me-2"></i>
                        ${data.message}
                    </div>
                `;
            }
            
            // Refresh documents list if we're on the manage page
            if (typeof loadDocuments === 'function') {
                loadDocuments();
            }
            
            // Refresh stats after a short delay
            setTimeout(fetchStats, 1500);
        } else {
            if (statsContent) {
                statsContent.innerHTML = `
                    <div class="alert alert-danger" role="alert">
                        <i class="fas fa-exclamation-circle me-2"></i>
                        Error: ${data.message}
                    </div>
                `;
            }
        }
    } catch (error) {
        if (statsContent) {
            statsContent.innerHTML = `
                <div class="alert alert-danger" role="alert">
                    <i class="fas fa-exclamation-circle me-2"></i>
                    Error: ${error.message}
                </div>
            `;
        }
    } finally {
        if (clearBtn) {
            clearBtn.disabled = false;
            clearBtn.innerHTML = `<i class="fas fa-trash me-1"></i> Clear Knowledge Base`;
        }
    }
}