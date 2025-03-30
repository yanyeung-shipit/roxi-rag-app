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
        statusDiv.dataset.lastUpdated = new Date().toISOString(); // Track when we last updated
        
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
    
    // Add event listeners to the manual refresh buttons
    setupRefreshButtons();
}

// Load background processing status
async function loadBackgroundStatus(forceRefresh = false) {
    try {
        // Check if we're in deep sleep mode and not forcing a refresh
        const statusElement = document.getElementById('background-processor-status');
        if (statusElement && statusElement.dataset.deepSleep === 'true' && !forceRefresh) {
            console.log("System in deep sleep mode, skipping automatic refresh");
            return; // Skip refresh if in deep sleep mode
        }
        
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
            
            // Update tracking element data attributes
            if (statusElement) {
                const wasInDeepSleep = statusElement.dataset.deepSleep === 'true';
                statusElement.dataset.deepSleep = status.in_deep_sleep ? 'true' : 'false';
                statusElement.dataset.vectorUnloaded = status.vector_store_unloaded ? 'true' : 'false';
                statusElement.dataset.lastUpdated = new Date().toISOString();
                
                // Log state change
                if (wasInDeepSleep !== (status.in_deep_sleep ? 'true' : 'false')) {
                    console.log(`Deep sleep mode changed: ${wasInDeepSleep ? 'ON' : 'OFF'} → ${status.in_deep_sleep ? 'ON' : 'OFF'}`);
                }
            } else {
                console.warn("background-processor-status element not found, cannot update deep sleep attribute");
            }
            
            // Create the status display HTML
            const autoRefreshState = status.in_deep_sleep 
                ? '<span class="badge bg-warning text-dark me-2">Auto-refresh paused</span>' 
                : '';
            
            backgroundStatusContent.innerHTML = `
                <div class="card bg-dark border-secondary">
                    <div class="card-body">
                        <div class="row">
                            <div class="col-md-6">
                                <h5 class="card-title">
                                    <span class="badge ${status.in_deep_sleep ? 'bg-warning text-dark' : (status.running ? 'bg-success' : 'bg-danger')} me-2">
                                        ${status.in_deep_sleep ? 'Deep Sleep' : (status.running ? 'Running' : 'Stopped')}
                                    </span>
                                    Background Processor
                                </h5>
                                <p class="text-muted mb-0">
                                    Processing documents in the background
                                    ${autoRefreshState}
                                </p>
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
                    ${status.in_deep_sleep ? 
                    `<div class="alert alert-warning">
                        <i class="fas fa-moon me-2"></i>
                        <strong>Deep Sleep Mode Active</strong> - System is conserving resources.
                        ${status.vector_store_unloaded ? 'Vector store is unloaded to save memory. ' : ''}
                        <div class="mt-2">
                            <span class="text-info">
                                <i class="fas fa-info-circle me-1"></i>
                                Auto-refresh is disabled. Use the manual refresh button above.
                            </span>
                        </div>
                    </div>` : 
                    `<p>
                        <i class="fas fa-info-circle me-1"></i>
                        The background processor automatically processes new documents and loads additional content for documents that have more chunks available. It processes one document at a time to avoid overloading the server.
                    </p>`}
                    
                    ${unprocessedCount > 0 || waitingForMoreContent > 0 ? 
                        `<div class="alert alert-info">
                            <i class="fas fa-sync fa-spin me-2"></i>
                            ${unprocessedCount > 0 ? `${unprocessedCount} document(s) queued for initial processing.<br>` : ''}
                            ${waitingForMoreContent > 0 ? `${waitingForMoreContent} document(s) waiting for additional content to be loaded.<br>` : ''}
                            Processing will happen automatically in the background.
                        </div>` : 
                        (status.in_deep_sleep ? `` : 
                        `<div class="alert alert-success">
                            <i class="fas fa-check-circle me-2"></i>
                            All documents have been fully processed.
                            ${status.consecutive_idle_cycles > 3 ? 
                            `<span class="ms-2"><strong>Energy Saving Mode</strong> - Processor is using adaptive sleep (${status.current_sleep_time}s) to conserve resources.</span>` : 
                            ``}
                        </div>`)
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

// Load system resources
async function loadSystemResources() {
    try {
        // Check if element exists
        const resourcesContent = document.getElementById('system-resources-content');
        if (!resourcesContent) {
            return;
        }
        
        console.log("Loading system resources...");
        
        // Call the API
        const response = await fetch('/background_status');
        const data = await response.json();
        
        if (data.success) {
            const status = data.status || data.processor_status;
            const resources = status.system_resources;
            
            // Format content
            resourcesContent.innerHTML = `
                <div class="card bg-dark border-secondary">
                    <div class="card-body">
                        <h5 class="card-title">System Resources</h5>
                        <div class="mt-3">
                            <div class="d-flex justify-content-between mb-2">
                                <div>CPU Usage:</div>
                                <div class="text-end">${resources.cpu_percent.toFixed(1)}%</div>
                            </div>
                            <div class="progress mb-3" style="height: 20px;">
                                <div class="progress-bar ${resources.cpu_percent > 80 ? 'bg-danger' : resources.cpu_percent > 60 ? 'bg-warning' : 'bg-success'}" 
                                    role="progressbar" style="width: ${resources.cpu_percent}%;" 
                                    aria-valuenow="${resources.cpu_percent}" aria-valuemin="0" aria-valuemax="100">
                                    ${resources.cpu_percent.toFixed(1)}%
                                </div>
                            </div>
                            
                            <div class="d-flex justify-content-between mb-2">
                                <div>Memory Usage:</div>
                                <div class="text-end">${resources.memory_percent.toFixed(1)}%</div>
                            </div>
                            <div class="progress" style="height: 20px;">
                                <div class="progress-bar ${resources.memory_percent > 80 ? 'bg-danger' : resources.memory_percent > 60 ? 'bg-warning' : 'bg-success'}" 
                                    role="progressbar" style="width: ${resources.memory_percent}%;" 
                                    aria-valuenow="${resources.memory_percent}" aria-valuemin="0" aria-valuemax="100">
                                    ${resources.memory_percent.toFixed(1)}%
                                </div>
                            </div>
                            
                            <div class="mt-3 text-muted">
                                <small>Available Memory: ${resources.memory_available_mb.toFixed(1)} MB</small>
                                <br>
                                <small>Resource Limited: ${resources.resource_limited ? 'Yes' : 'No'}</small>
                            </div>
                        </div>
                    </div>
                </div>
            `;
        } else {
            console.error("Error loading system resources:", data.message);
            resourcesContent.innerHTML = `
                <div class="alert alert-danger">
                    <i class="fas fa-exclamation-circle me-2"></i>
                    Error: ${data.message}
                </div>
            `;
        }
    } catch (error) {
        console.error("Exception loading system resources:", error);
    }
}

// Load processing metrics
async function loadProcessingMetrics() {
    try {
        // Check if we're in deep sleep mode and skip if we are
        const statusElement = document.getElementById('background-processor-status');
        if (statusElement && statusElement.dataset.deepSleep === 'true') {
            console.log("System in deep sleep mode, skipping processing metrics refresh");
            return; // Skip refresh if in deep sleep mode
        }
        
        // Check if element exists
        const metricsContent = document.getElementById('processing-metrics-content');
        if (!metricsContent) {
            return;
        }
        
        console.log("Loading processing metrics...");
        
        // Call the API
        const response = await fetch('/background_status');
        const data = await response.json();
        
        if (data.success) {
            const status = data.status || data.processor_status;
            const metrics = status.processing_metrics || {};
            
            // Calculate percentage for progress bar
            const percentComplete = metrics.percent_complete || 0;
            
            // Format content
            metricsContent.innerHTML = `
                <div class="card bg-dark border-secondary">
                    <div class="card-body">
                        <h5 class="card-title">Processing Metrics</h5>
                        <div class="mt-3">
                            <div class="d-flex justify-content-between mb-2">
                                <div>Progress:</div>
                                <div class="text-end">${percentComplete.toFixed(1)}%</div>
                            </div>
                            <div class="progress mb-3" style="height: 20px;">
                                <div class="progress-bar ${percentComplete > 80 ? 'bg-success' : percentComplete > 40 ? 'bg-info' : 'bg-warning'}" 
                                    role="progressbar" style="width: ${percentComplete}%;" 
                                    aria-valuenow="${percentComplete}" aria-valuemin="0" aria-valuemax="100">
                                    ${percentComplete.toFixed(1)}%
                                </div>
                            </div>
                            
                            <div class="row">
                                <div class="col-md-6">
                                    <p><strong>Processed Chunks:</strong> ${metrics.processed_chunks || 0} / ${metrics.total_chunks || 0}</p>
                                    <p><strong>Total Documents:</strong> ${metrics.total_documents || 0}</p>
                                </div>
                                <div class="col-md-6">
                                    <p><strong>Processing Rate:</strong> ${metrics.processing_rate_chunks_per_second ? metrics.processing_rate_chunks_per_second.toFixed(2) : 0} chunks/sec</p>
                                    <p><strong>Est. Time Remaining:</strong> ${metrics.estimated_time_remaining || "Unknown"}</p>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            `;
        } else {
            console.error("Error loading processing metrics:", data.message);
            metricsContent.innerHTML = `
                <div class="alert alert-danger">
                    <i class="fas fa-exclamation-circle me-2"></i>
                    Error: ${data.message}
                </div>
            `;
        }
    } catch (error) {
        console.error("Exception loading processing metrics:", error);
    }
}

// Setup refresh button event listeners
/**
 * Set up click handlers for manual refresh buttons
 * This allows refreshing individual cards even during deep sleep mode
 */
function setupRefreshButtons() {
    // System resources refresh button
    const resourcesRefreshBtn = document.getElementById('refresh-system-resources');
    if (resourcesRefreshBtn) {
        // Remove any existing event listeners to prevent duplicates
        // (can't actually remove anonymous functions, but we can replace them)
        resourcesRefreshBtn.onclick = function(e) {
            e.preventDefault();
            console.log("Manual refresh of system resources requested");
            loadSystemResources(); // This always works even in deep sleep mode
        };
    }
    
    // Background status refresh button
    const statusRefreshBtn = document.getElementById('refresh-background-status');
    if (statusRefreshBtn) {
        // Remove any existing event listeners to prevent duplicates
        statusRefreshBtn.onclick = function(e) {
            e.preventDefault();
            console.log("Manual refresh of background status requested");
            loadBackgroundStatus(true); // Force refresh even in deep sleep
        };
    }
}

document.addEventListener('DOMContentLoaded', function() {
    // Ensure status element exists first
    ensureBackgroundProcessorStatus();
    
    // Initial load of all components
    const inManagePage = document.getElementById('background-status-content') !== null;
    
    if (inManagePage) {
        // Load background status metrics
        loadBackgroundStatus(true); // Force initial load
        loadProcessingMetrics();
        loadSystemResources();
        
        // Set up refresh buttons
        setupRefreshButtons();
        
        const metricsRefreshBtn = document.getElementById('refresh-processing-metrics');
        if (metricsRefreshBtn) {
            metricsRefreshBtn.addEventListener('click', function() {
                // Only refresh if not in deep sleep or user explicitly requested
                const statusElement = document.getElementById('background-processor-status');
                const inDeepSleep = statusElement && statusElement.dataset.deepSleep === 'true';
                
                if (inDeepSleep) {
                    alert("System is in deep sleep mode. Processing is paused to conserve resources.");
                } else {
                    loadProcessingMetrics();
                }
            });
        }
        
        const resourcesRefreshBtn = document.getElementById('refresh-system-resources');
        if (resourcesRefreshBtn) {
            resourcesRefreshBtn.addEventListener('click', function() {
                // Resources can always be refreshed without waking up the system
                loadSystemResources();
            });
        }
        
        // Setup automatic refresh timers
        let statusRefreshTimerId = null;
        let metricsRefreshTimerId = null;
        let resourcesRefreshTimerId = null;
        
        // Function to manage refresh timers based on deep sleep status
        function updateRefreshTimers(inDeepSleep) {
            // Clear existing timers
            if (statusRefreshTimerId) clearInterval(statusRefreshTimerId);
            if (metricsRefreshTimerId) clearInterval(metricsRefreshTimerId);
            if (resourcesRefreshTimerId) clearInterval(resourcesRefreshTimerId);
            
            if (inDeepSleep) {
                console.log("Deep sleep mode active - automatic refreshes disabled");
                // Do not set any automatic refresh timers when in deep sleep
            } else {
                console.log("Normal operation mode - setting up refresh timers");
                // Set timers for normal operation
                statusRefreshTimerId = setInterval(loadBackgroundStatus, 30000);
                metricsRefreshTimerId = setInterval(loadProcessingMetrics, 45000);
                resourcesRefreshTimerId = setInterval(loadSystemResources, 60000);
            }
        }
        
        // Check deep sleep status every minute to update refresh behavior
        setInterval(function() {
            const statusElement = document.getElementById('background-processor-status');
            if (statusElement) {
                const inDeepSleep = statusElement.dataset.deepSleep === 'true';
                updateRefreshTimers(inDeepSleep);
            }
        }, 60000);
        
        // Initial setup based on current state
        const statusElement = document.getElementById('background-processor-status');
        const initialDeepSleep = statusElement ? statusElement.dataset.deepSleep === 'true' : false;
        updateRefreshTimers(initialDeepSleep);
    }
});