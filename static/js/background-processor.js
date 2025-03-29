/**
 * Background Processor Status Module
 * Handles fetching and displaying the status of the background processing service.
 */

// Load background processing status
async function loadBackgroundStatus() {
    try {
        console.log("Loading background processing status...");
        
        const backgroundStatusContent = document.getElementById('background-status-content');
        if (!backgroundStatusContent) {
            console.error("Cannot load background status: background-status-content element not found");
            return;
        }
        
        // Show loading spinner
        backgroundStatusContent.innerHTML = `
            <div class="d-flex justify-content-center">
                <div class="spinner-border text-info" role="status">
                    <span class="visually-hidden">Loading...</span>
                </div>
            </div>
        `;
        
        // Call the API
        const response = await fetch('/background_status');
        const data = await response.json();
        
        if (data.success) {
            console.log("Background status:", data);
            
            const status = data.status;
            const unprocessedCount = data.unprocessed_documents;
            const waitingForMoreContent = status.documents_waiting_for_more_content || 0;
            
            // Format the last run time
            let lastRunText = "Never";
            if (status.last_run) {
                const lastRunDate = new Date(status.last_run);
                lastRunText = lastRunDate.toLocaleString();
            }
            
            // Create card with status information
            backgroundStatusContent.innerHTML = `
                <div class="card bg-dark border-secondary">
                    <div class="card-body">
                        <div class="row">
                            <div class="col-md-6">
                                <h5 class="card-title">
                                    <span class="badge ${status.running ? 'bg-success' : 'bg-danger'} me-2">
                                        ${status.running ? 'Running' : 'Stopped'}
                                    </span>
                                    Background Processor
                                </h5>
                                <p class="text-muted mb-0">Processing documents in the background</p>
                            </div>
                            <div class="col-md-6">
                                <div class="d-flex justify-content-end">
                                    <div class="text-end">
                                        <div><strong>Last Activity:</strong> ${lastRunText}</div>
                                        <div><strong>Documents Processed:</strong> ${status.documents_processed}</div>
                                        <div><strong>Unprocessed Documents:</strong> ${unprocessedCount}</div>
                                        <div><strong>Documents Pending More Content:</strong> ${waitingForMoreContent}</div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
                
                <div class="mt-3 small text-muted">
                    <p>
                        <i class="fas fa-info-circle me-1"></i>
                        The background processor automatically processes new documents and loads additional content for documents that have more chunks available. It processes one document at a time to avoid overloading the server.
                    </p>
                    ${unprocessedCount > 0 || waitingForMoreContent > 0 ? 
                        `<div class="alert alert-info">
                            <i class="fas fa-sync fa-spin me-2"></i>
                            ${unprocessedCount > 0 ? `${unprocessedCount} document(s) queued for initial processing.<br>` : ''}
                            ${waitingForMoreContent > 0 ? `${waitingForMoreContent} document(s) waiting for additional content to be loaded.<br>` : ''}
                            Processing will happen automatically in the background.
                        </div>` : 
                        `<div class="alert alert-success">
                            <i class="fas fa-check-circle me-2"></i>
                            All documents have been fully processed.
                        </div>`
                    }
                </div>
            `;
            
        } else {
            console.error("Error loading background status:", data.message);
            backgroundStatusContent.innerHTML = `
                <div class="alert alert-danger">
                    <i class="fas fa-exclamation-circle me-2"></i>
                    Error: ${data.message}
                </div>
            `;
        }
    } catch (error) {
        console.error("Exception loading background status:", error);
        const backgroundStatusContent = document.getElementById('background-status-content');
        if (backgroundStatusContent) {
            backgroundStatusContent.innerHTML = `
                <div class="alert alert-danger">
                    <i class="fas fa-exclamation-circle me-2"></i>
                    Error loading background status: ${error.message}
                </div>
            `;
        }
    }
}

// Setup refresh button event listener
document.addEventListener('DOMContentLoaded', function() {
    // Initial load
    loadBackgroundStatus();
    
    // Setup refresh button
    const refreshBtn = document.getElementById('refresh-background-status');
    if (refreshBtn) {
        refreshBtn.addEventListener('click', function() {
            loadBackgroundStatus();
        });
    }
    
    // Setup automatic refresh every 30 seconds
    setInterval(loadBackgroundStatus, 30000);
});