/**
 * Background Processor Status Module
 * Handles fetching and displaying the status of the background processing service.
 */

// Function to create the status element if it doesn't exist
function ensureBackgroundProcessorStatus() {
    // Check if we already have the element that will store our deep sleep status
    if (!document.getElementById('background-processor-status')) {
        // Create a new div to hold the status data attributes
        const statusDiv = document.createElement('div');
        statusDiv.id = 'background-processor-status';
        statusDiv.style.display = 'none'; // Hidden element for data only
        statusDiv.dataset.deepSleep = 'false'; // Default value
        statusDiv.dataset.vectorUnloaded = 'false'; // Default value
        
        // Add it to the body or better, near the content
        const contentElement = document.getElementById('background-status-content');
        if (contentElement && contentElement.parentNode) {
            contentElement.parentNode.insertBefore(statusDiv, contentElement);
            console.log("Created background-processor-status element for status tracking");
        } else {
            document.body.appendChild(statusDiv);
            console.log("Added background-processor-status to body (fallback)");
        }
    }
}

// Load background processing status
async function loadBackgroundStatus() {
    try {
        console.log("Loading background processing status...");
        
        // Ensure we have the status tracking element
        ensureBackgroundProcessorStatus();
        
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
            
            // Use status key for backward compatibility, fallback to processor_status
            const status = data.status || data.processor_status;
            // Use the dedicated unprocessed_documents count
            const unprocessedCount = data.unprocessed_documents || data.total_unprocessed_count || 0;
            // Get count of documents waiting for more content
            const waitingForMoreContent = status ? (status.documents_waiting_for_more_content || 0) : 0;
            
            // Format the last run time
            let lastRunText = "Never";
            if (status.last_run) {
                const lastRunDate = new Date(status.last_run);
                lastRunText = lastRunDate.toLocaleString();
            }
            
            // Create card with status information
            // Add a data attribute to the parent element for the refresh timer to detect deep sleep
            const statusElement = document.getElementById('background-processor-status');
            if (statusElement) {
                statusElement.dataset.deepSleep = status.in_deep_sleep ? 'true' : 'false';
                statusElement.dataset.vectorUnloaded = status.vector_store_unloaded ? 'true' : 'false';
            } else {
                console.warn("background-processor-status element not found, cannot update deep sleep attribute");
            }
            
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
                                        <div><strong>Sleep Time:</strong> ${status.current_sleep_time}s</div>
                                        ${status.in_deep_sleep ? 
                                          `<div class="text-warning"><strong>Deep Sleep Mode:</strong> Active</div>` : 
                                          ``}
                                        ${status.vector_store_unloaded ? 
                                          `<div class="text-info"><strong>Vector Store:</strong> Unloaded (Memory-Saving Mode)</div>` : 
                                          ``}
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
                        `<div class="alert ${status.in_deep_sleep ? 'alert-warning' : 'alert-success'}">
                            <i class="fas ${status.in_deep_sleep ? 'fa-moon' : 'fa-check-circle'} me-2"></i>
                            All documents have been fully processed.
                            ${status.in_deep_sleep ? 
                              `<span class="ms-2"><strong>Deep Sleep Mode Active</strong> - ${status.vector_store_unloaded ? 'Vector store unloaded to save memory. ' : ''}Processor is conserving resources. Will wake instantly when new documents are added.</span>` : 
                              (status.consecutive_idle_cycles > 3 ? 
                               `<span class="ms-2"><strong>Energy Saving Mode</strong> - Processor is using adaptive sleep (${status.current_sleep_time}s) to conserve resources.</span>` : 
                               ``)}
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
    // Ensure status element exists first
    ensureBackgroundProcessorStatus();
    
    // Initial load
    loadBackgroundStatus();
    
    // Setup refresh button
    const refreshBtn = document.getElementById('refresh-background-status');
    if (refreshBtn) {
        refreshBtn.addEventListener('click', function() {
            loadBackgroundStatus();
        });
    }
    
    // Variables to control refresh rate
    let refreshInterval = 30000; // Default 30 seconds
    let deepSleepInterval = 300000; // Deep sleep mode: 5 minutes
    let inDeepSleep = false;
    let refreshTimerId = null;
    
    // Function to update refresh interval based on status
    function updateRefreshInterval(isInDeepSleep) {
        // Clear existing timer
        if (refreshTimerId) {
            clearInterval(refreshTimerId);
        }
        
        // Set appropriate interval based on sleep status
        if (isInDeepSleep) {
            inDeepSleep = true;
            refreshInterval = deepSleepInterval;
            console.log("Background processor in deep sleep mode, reducing status refresh rate to 5 minutes");
        } else {
            inDeepSleep = false;
            refreshInterval = 30000;
            console.log("Background processor active, using normal status refresh rate (30 seconds)");
        }
        
        // Set new timer
        refreshTimerId = setInterval(loadBackgroundStatus, refreshInterval);
    }
    
    // Initial setup with the regular interval
    refreshTimerId = setInterval(async function() {
        await loadBackgroundStatus();
        
        // Check deep sleep status and adjust if needed
        const statusElement = document.getElementById('background-processor-status');
        if (statusElement && statusElement.dataset && statusElement.dataset.deepSleep === 'true' && !inDeepSleep) {
            updateRefreshInterval(true);
        } else if (statusElement && statusElement.dataset && statusElement.dataset.deepSleep === 'false' && inDeepSleep) {
            updateRefreshInterval(false);
        }
    }, refreshInterval);
});