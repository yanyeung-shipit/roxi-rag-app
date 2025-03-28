document.addEventListener('DOMContentLoaded', () => {
    console.log("Document Manager script loaded");
    
    // Check if we are on the manage page
    if (!document.getElementById('documentsTableBody')) {
        console.log("Not on manage page, exiting script");
        return;
    }
    
    // DOM element references - all elements are optional and get checked before use
    const elements = {
        // Form elements
        pdfForm: document.getElementById('pdf-form'),
        pdfResult: document.getElementById('pdf-result'),
        bulkPdfForm: document.getElementById('bulk-pdf-form'),
        bulkPdfResult: document.getElementById('bulk-pdf-result'),
        websiteForm: document.getElementById('website-form'),
        websiteResult: document.getElementById('website-result'),
        topicPagesForm: document.getElementById('topic-pages-form'),
        topicPagesResult: document.getElementById('topic-pages-result'),
        
        // Document elements
        documentsTableBody: document.getElementById('documentsTableBody'),
        documentDetailContainer: document.getElementById('documentDetailContainer'),
        documentsTableContainer: document.getElementById('documentsTableContainer'),
        documentDetailContent: document.getElementById('documentDetailContent'),
        backToDocumentsBtn: document.getElementById('backToDocumentsBtn'),
        refreshDocumentsBtn: document.getElementById('refreshDocumentsBtn'),
        
        // Background processing
        refreshBackgroundStatusBtn: document.getElementById('refresh-background-status'),
        backgroundStatusContent: document.getElementById('background-status-content'),
        
        // Collection elements
        newCollectionBtn: document.getElementById('newCollectionBtn'),
        createCollectionBtn: document.getElementById('createCollectionBtn'),
        collectionsList: document.getElementById('collectionsList'),
        collectionDetailCard: document.getElementById('collectionDetailCard'),
        collectionDetailTitle: document.getElementById('collectionDetailTitle'),
        collectionDescription: document.getElementById('collectionDescription'),
        collectionDocumentsList: document.getElementById('collectionDocumentsList'),
        addToCollectionBtn: document.getElementById('addToCollectionBtn'),
        documentSelectionList: document.getElementById('documentSelectionList'),
        confirmAddToCollectionBtn: document.getElementById('confirmAddToCollectionBtn'),
        confirmDeleteBtn: document.getElementById('confirmDeleteBtn')
    };
    
    // Log which elements were found or missing
    Object.entries(elements).forEach(([name, element]) => {
        console.log(`Element ${name}: ${element ? 'Found' : 'Missing'}`);
    });

    // Global state
    let currentDocuments = [];
    let currentCollections = [];
    let selectedCollectionId = null;
    let documentToDeleteId = null;
    let collectionToDeleteId = null;

    // Initialize
    loadDocuments();
    loadCollections();
    loadBackgroundStatus();

    // Event listeners - using safe method that checks for null
    setupEventListeners();
    
    function setupEventListeners() {
        console.log("Setting up event listeners");
        
        // Function to safely add event listeners with console logging
        function safeAddEventListener(elementKey, event, handler) {
            const element = elements[elementKey];
            if (element) {
                console.log(`Adding ${event} event listener to ${elementKey}`);
                element.addEventListener(event, handler);
            } else {
                console.warn(`Element ${elementKey} not found, cannot add ${event} event listener`);
            }
        }
        
        // Form submissions
        safeAddEventListener('pdfForm', 'submit', handlePdfFormSubmit);
        safeAddEventListener('bulkPdfForm', 'submit', handleBulkPdfFormSubmit);
        safeAddEventListener('websiteForm', 'submit', handleWebsiteFormSubmit);

        // Bind to the form directly for topic pages to avoid button reference issues
        if (elements.topicPagesForm) {
            console.log('Found topic-pages-form, binding events');
            
            // Bind to the form's submit event
            elements.topicPagesForm.addEventListener('submit', function(event) {
                event.preventDefault();
                handleTopicPagesSubmit(event);
            });
            
            // Also try to bind to the button directly if possible
            const addTopicsBtn = document.getElementById('add-topics-btn');
            if (addTopicsBtn) {
                elements.addTopicsBtn = addTopicsBtn;
                console.log('Found add-topics-btn element, adding click event listener');
                addTopicsBtn.addEventListener('click', function(event) {
                    event.preventDefault();
                    handleTopicPagesSubmit(event);
                });
            } else {
                console.warn('Could not find add-topics-btn element, but form is still bound');
            }
        } else {
            console.error('Topic pages form not found in DOM');
        }
        
        // Document navigation
        safeAddEventListener('refreshDocumentsBtn', 'click', loadDocuments);
        safeAddEventListener('backToDocumentsBtn', 'click', () => {
            if (elements.documentDetailContainer && elements.documentsTableContainer) {
                elements.documentDetailContainer.classList.add('d-none');
                elements.documentsTableContainer.classList.remove('d-none');
            }
        });
        
        // Background processing status
        safeAddEventListener('refreshBackgroundStatusBtn', 'click', loadBackgroundStatus);
        
        // Collection actions
        safeAddEventListener('createCollectionBtn', 'click', createCollection);
        safeAddEventListener('confirmAddToCollectionBtn', 'click', addDocumentsToCollection);
        safeAddEventListener('confirmDeleteBtn', 'click', deleteDocument);
        
        // Setup new collection button modal trigger
        safeAddEventListener('newCollectionBtn', 'click', function() {
            console.log("New collection button clicked");
            const modalId = 'newCollectionModal';
            showModal(modalId);
        });
    }
    
    // Helper function to show a modal
    function showModal(modalId) {
        console.log(`Attempting to show modal: ${modalId}`);
        const modalElement = document.getElementById(modalId);
        
        if (!modalElement) {
            console.error(`Modal element ${modalId} not found`);
            return;
        }
        
        // Try multiple approaches to show modal
        try {
            // Try Bootstrap 5 way
            const bsModal = new bootstrap.Modal(modalElement);
            bsModal.show();
            console.log("Modal shown using Bootstrap 5 API");
            return;
        } catch (error1) {
            console.warn("Bootstrap 5 modal show failed:", error1);
            
            try {
                // Try jQuery way
                $(modalElement).modal('show');
                console.log("Modal shown using jQuery");
                return;
            } catch (error2) {
                console.warn("jQuery modal show failed:", error2);
                
                try {
                    // Manual way
                    modalElement.classList.add('show');
                    modalElement.style.display = 'block';
                    document.body.classList.add('modal-open');
                    
                    // Add backdrop
                    let backdrop = document.querySelector('.modal-backdrop');
                    if (!backdrop) {
                        backdrop = document.createElement('div');
                        backdrop.className = 'modal-backdrop fade show';
                        document.body.appendChild(backdrop);
                    }
                    console.log("Modal shown manually by DOM manipulation");
                } catch (error3) {
                    console.error("Manual modal show failed:", error3);
                }
            }
        }
    }
    
    // Helper function to hide a modal
    function hideModal(modalId) {
        console.log(`Attempting to hide modal: ${modalId}`);
        const modalElement = document.getElementById(modalId);
        
        if (!modalElement) {
            console.error(`Modal element ${modalId} not found`);
            return;
        }
        
        // Try multiple approaches to hide modal
        try {
            // Try Bootstrap 5 way
            const bsModal = bootstrap.Modal.getInstance(modalElement);
            if (bsModal) {
                bsModal.hide();
                console.log("Modal hidden using Bootstrap 5 API");
                
                // Extra cleanup for backdrop
                setTimeout(() => {
                    cleanupModalBackdrop();
                }, 300);
                return;
            }
        } catch (error1) {
            console.warn("Bootstrap 5 modal hide failed:", error1);
        }
        
        try {
            // Try jQuery way
            $(modalElement).modal('hide');
            console.log("Modal hidden using jQuery");
            
            // Extra cleanup for backdrop
            setTimeout(() => {
                cleanupModalBackdrop();
            }, 300);
            return;
        } catch (error2) {
            console.warn("jQuery modal hide failed:", error2);
            
            try {
                // Manual way
                modalElement.classList.remove('show');
                modalElement.style.display = 'none';
                document.body.classList.remove('modal-open');
                
                // Remove backdrop
                cleanupModalBackdrop();
                console.log("Modal hidden manually by DOM manipulation");
            } catch (error3) {
                console.error("Manual modal hide failed:", error3);
            }
        }
    }
    
    // Helper function to clean up modal backdrops
    function cleanupModalBackdrop() {
        console.log("Cleaning up modal backdrop");
        
        // Remove all modal-backdrop elements
        const backdrops = document.querySelectorAll('.modal-backdrop');
        backdrops.forEach(backdrop => {
            backdrop.parentNode.removeChild(backdrop);
        });
        
        // Make sure body doesn't have modal-open class
        document.body.classList.remove('modal-open');
        
        // Remove inline style that might have been added to body
        document.body.style.removeProperty('padding-right');
        document.body.style.removeProperty('overflow');
        
        console.log(`Removed ${backdrops.length} backdrops`);
    }

    // Load all documents
    async function loadDocuments() {
        try {
            console.log("Loading documents...");
            if (elements.documentsTableBody) {
                elements.documentsTableBody.innerHTML = '<tr><td colspan="5" class="text-center">Loading documents...</td></tr>';
            }
            
            const response = await fetch('/documents');
            const data = await response.json();
            
            if (data.success) {
                console.log(`Loaded ${data.documents.length} documents`);
                currentDocuments = data.documents;
                renderDocumentsTable();
            } else {
                console.error("Error loading documents:", data.message);
                if (elements.documentsTableBody) {
                    elements.documentsTableBody.innerHTML = `
                        <tr>
                            <td colspan="5" class="text-center text-danger">
                                <i class="fas fa-exclamation-circle me-2"></i>
                                ${data.message}
                            </td>
                        </tr>
                    `;
                }
            }
        } catch (error) {
            console.error("Exception loading documents:", error);
            if (elements.documentsTableBody) {
                elements.documentsTableBody.innerHTML = `
                    <tr>
                        <td colspan="5" class="text-center text-danger">
                            <i class="fas fa-exclamation-circle me-2"></i>
                            Error loading documents: ${error.message}
                        </td>
                    </tr>
                `;
            }
        }
    }

    // Render documents table
    function renderDocumentsTable() {
        if (!elements.documentsTableBody) {
            console.error("Cannot render documents table: documentsTableBody element not found");
            return;
        }
        
        if (currentDocuments.length === 0) {
            elements.documentsTableBody.innerHTML = `
                <tr>
                    <td colspan="5" class="text-center">
                        No documents found. Upload documents from the search page.
                    </td>
                </tr>
            `;
            return;
        }

        elements.documentsTableBody.innerHTML = '';
        
        currentDocuments.forEach(doc => {
            const row = document.createElement('tr');
            
            // Format the created date
            const createdDate = new Date(doc.created_at);
            const dateStr = createdDate.toLocaleDateString();
            
            // Size or page information
            let sizeInfo = '';
            if (doc.file_type === 'pdf') {
                if (doc.page_count) {
                    sizeInfo = `${doc.page_count} pages`;
                } else if (doc.file_size) {
                    sizeInfo = `${(doc.file_size / 1024 / 1024).toFixed(2)} MB`;
                }
            } else {
                sizeInfo = `${doc.chunk_count || 'Unknown'} chunks`;
            }
            
            const safeTitle = doc.title || doc.filename || 'Untitled Document';
            
            row.innerHTML = `
                <td>
                    <strong>${safeTitle}</strong>
                </td>
                <td>
                    <span class="badge bg-${doc.file_type === 'pdf' ? 'warning' : 'info'}">
                        ${doc.file_type === 'pdf' ? 'PDF' : 'Website'}
                    </span>
                </td>
                <td>${sizeInfo}</td>
                <td>${dateStr}</td>
                <td>
                    <div class="btn-group" role="group">
                        <button type="button" class="btn btn-sm btn-outline-info view-doc-btn" data-id="${doc.id}">
                            <i class="fas fa-eye"></i>
                        </button>
                        <button type="button" class="btn btn-sm btn-outline-danger delete-doc-btn" data-id="${doc.id}" data-title="${safeTitle}">
                            <i class="fas fa-trash"></i>
                        </button>
                    </div>
                </td>
            `;
            
            elements.documentsTableBody.appendChild(row);
        });
        
        // Add event listeners to buttons
        document.querySelectorAll('.view-doc-btn').forEach(btn => {
            btn.addEventListener('click', () => viewDocument(btn.dataset.id));
        });
        
        document.querySelectorAll('.delete-doc-btn').forEach(btn => {
            btn.addEventListener('click', () => showDeleteConfirmation(btn.dataset.id, btn.dataset.title));
        });
    }

    // View a single document
    async function viewDocument(docId) {
        try {
            console.log(`Viewing document: ${docId}`);
            
            if (!elements.documentDetailContent || !elements.documentDetailContainer || !elements.documentsTableContainer) {
                console.error("Cannot view document: required DOM elements not found");
                return;
            }
            
            elements.documentDetailContent.innerHTML = '<p class="text-center">Loading document details...</p>';
            elements.documentDetailContainer.classList.remove('d-none');
            elements.documentsTableContainer.classList.add('d-none');
            
            const response = await fetch(`/documents/${docId}`);
            const data = await response.json();
            
            if (data.success) {
                const doc = data.document;
                const createdDate = new Date(doc.created_at);
                const dateStr = createdDate.toLocaleDateString();
                
                // Build detailed view
                let html = `
                    <h4>${doc.title || doc.filename || 'Untitled Document'}</h4>
                    <div class="row mb-4">
                        <div class="col-md-6">
                            <ul class="list-group list-group-flush bg-transparent">
                                <li class="list-group-item bg-transparent d-flex justify-content-between">
                                    <span>Type:</span>
                                    <span class="badge bg-${doc.file_type === 'pdf' ? 'warning' : 'info'}">
                                        ${doc.file_type === 'pdf' ? 'PDF Document' : 'Website'}
                                    </span>
                                </li>
                                <li class="list-group-item bg-transparent d-flex justify-content-between">
                                    <span>Added:</span>
                                    <span>${dateStr}</span>
                                </li>
                `;
                    
                if (doc.file_type === 'pdf') {
                    html += `
                        <li class="list-group-item bg-transparent d-flex justify-content-between">
                            <span>File Size:</span>
                            <span>${doc.file_size ? (doc.file_size / 1024 / 1024).toFixed(2) + ' MB' : 'N/A'}</span>
                        </li>
                        <li class="list-group-item bg-transparent d-flex justify-content-between">
                            <span>Pages:</span>
                            <span>${doc.page_count || 'N/A'}</span>
                        </li>
                    `;
                    
                    // Add DOI if available
                    if (doc.doi) {
                        html += `
                            <li class="list-group-item bg-transparent">
                                <div><strong>DOI:</strong></div>
                                <div class="mt-1">
                                    <a href="https://doi.org/${doc.doi}" target="_blank" class="text-info">${doc.doi}</a>
                                </div>
                            </li>
                        `;
                    }
                    
                    // Add citation if available
                    if (doc.formatted_citation) {
                        html += `
                            <li class="list-group-item bg-transparent">
                                <div><strong>Citation:</strong></div>
                                <div class="mt-1">
                                    <small>${doc.formatted_citation}</small>
                                </div>
                            </li>
                        `;
                    }
                    
                    // Add process button for unprocessed PDFs
                    if (!doc.processed && doc.file_path) {
                        html += `
                            </ul>
                            <div class="alert alert-secondary mt-3">
                                <p><i class="fas fa-exclamation-circle me-2"></i> This document needs to be processed to extract DOI and citation info.</p>
                                <button id="processDocBtn" class="btn btn-sm btn-primary" onclick="processDocument(${doc.id})">
                                    <i class="fas fa-cogs me-1"></i> Process Document
                                </button>
                                <div id="processStatus" class="mt-2"></div>
                            </div>
                            <ul class="list-group list-group-flush bg-transparent">
                        `;
                    }
                } else if (doc.source_url) {
                    html += `
                        <li class="list-group-item bg-transparent d-flex justify-content-between">
                            <span>Source URL:</span>
                            <span><a href="${doc.source_url}" target="_blank" class="text-info">${doc.source_url}</a></span>
                        </li>
                    `;
                }
                    
                html += `
                        <li class="list-group-item bg-transparent d-flex justify-content-between">
                            <span>Text Chunks:</span>
                            <span>${doc.chunks ? doc.chunks.length : 0}</span>
                        </li>
                    </ul>
                </div>
                
                <div class="col-md-6">
                    <h5 class="mb-3">Collections</h5>
                    <div id="docCollectionsList">Loading...</div>
                </div>
            </div>
            
            <h5>Content Preview</h5>
            <div class="card bg-dark border-secondary mb-4">
                <div class="card-body">
                    <div style="max-height: 300px; overflow-y: auto;">
                `;
                
                // Add content preview (first few chunks)
                if (doc.chunks && doc.chunks.length > 0) {
                    const maxChunks = Math.min(3, doc.chunks.length);
                    for (let i = 0; i < maxChunks; i++) {
                        html += `
                            <div class="mb-3">
                                <span class="badge bg-secondary mb-1">Chunk ${i+1}</span>
                                <p class="text-muted small">${doc.chunks[i].text_content}</p>
                            </div>
                        `;
                        
                        // Add separator between chunks
                        if (i < maxChunks - 1) {
                            html += '<hr class="border-secondary">';
                        }
                    }
                    
                    // Add indication if there are more chunks
                    if (doc.chunks.length > maxChunks) {
                        html += `
                            <div class="text-center mt-3">
                                <span class="badge bg-secondary">+${doc.chunks.length - maxChunks} more chunks</span>
                            </div>
                        `;
                    }
                    
                    // Check if there are more content chunks available to load
                    // file_size is repurposed to store total possible chunks for website documents
                    if (doc.file_type === 'website' && doc.file_size > 0 && doc.chunks.length < doc.file_size) {
                        const remainingChunks = doc.file_size - doc.chunks.length;
                        html += `
                            <div class="alert alert-info mt-3">
                                <div class="d-flex justify-content-between align-items-center">
                                    <div>
                                        <i class="fas fa-info-circle me-2"></i>
                                        Currently showing ${doc.chunks.length} of ${doc.file_size} available chunks.
                                    </div>
                                    <button id="loadMoreContentBtn" class="btn btn-primary btn-sm" 
                                            onclick="loadMoreContent(${doc.id})">
                                        <i class="fas fa-cloud-download-alt me-2"></i>
                                        Load More Content (${Math.min(5, remainingChunks)} of ${remainingChunks})
                                    </button>
                                </div>
                                <div id="loadMoreStatus" class="mt-2" style="display: none;"></div>
                            </div>
                        `;
                    }
                } else {
                    html += '<p class="text-center text-muted">No content available for preview</p>';
                }
                
                html += `
                        </div>
                    </div>
                </div>
                `;
                
                elements.documentDetailContent.innerHTML = html;
                
                // Load collections for this document (Would need to implement this endpoint)
                // loadDocumentCollections(docId);
            } else {
                elements.documentDetailContent.innerHTML = `
                    <div class="alert alert-danger" role="alert">
                        <i class="fas fa-exclamation-circle me-2"></i>
                        ${data.message || 'Error loading document details'}
                    </div>
                `;
            }
        } catch (error) {
            console.error("Error viewing document:", error);
            if (elements.documentDetailContent) {
                elements.documentDetailContent.innerHTML = `
                    <div class="alert alert-danger" role="alert">
                        <i class="fas fa-exclamation-circle me-2"></i>
                        Error loading document: ${error.message}
                    </div>
                `;
            }
        }
    }

    // Load all collections
    async function loadCollections() {
        try {
            console.log("Loading collections...");
            if (!elements.collectionsList) {
                console.error("Cannot load collections: collectionsList element not found");
                return;
            }
            
            elements.collectionsList.innerHTML = '<div class="list-group-item list-group-item-dark">Loading collections...</div>';
            
            const response = await fetch('/collections');
            const data = await response.json();
            
            if (data.success) {
                console.log(`Loaded ${data.collections.length} collections`);
                currentCollections = data.collections;
                renderCollectionsList();
            } else {
                console.error("Error loading collections:", data.message);
                elements.collectionsList.innerHTML = `
                    <div class="list-group-item list-group-item-dark text-danger">
                        <i class="fas fa-exclamation-circle me-2"></i>
                        ${data.message || 'Error loading collections'}
                    </div>
                `;
            }
        } catch (error) {
            console.error("Exception loading collections:", error);
            if (elements.collectionsList) {
                elements.collectionsList.innerHTML = `
                    <div class="list-group-item list-group-item-dark text-danger">
                        <i class="fas fa-exclamation-circle me-2"></i>
                        Error loading collections: ${error.message}
                    </div>
                `;
            }
        }
    }

    // Render collections list
    function renderCollectionsList() {
        if (!elements.collectionsList) {
            console.error("Cannot render collections list: collectionsList element not found");
            return;
        }
        
        if (!currentCollections || currentCollections.length === 0) {
            elements.collectionsList.innerHTML = `
                <div class="list-group-item list-group-item-dark">
                    No collections found. Create a new collection to organize your documents.
                </div>
            `;
            return;
        }

        elements.collectionsList.innerHTML = '';
        
        currentCollections.forEach(collection => {
            if (!collection || !collection.id) {
                console.warn("Skipping invalid collection in renderCollectionsList");
                return;
            }
            
            const item = document.createElement('div');
            item.className = 'list-group-item list-group-item-dark d-flex justify-content-between align-items-center';
            item.dataset.id = collection.id;
            
            const documentCount = collection.document_count || 0;
            
            item.innerHTML = `
                <a href="#" class="text-decoration-none collection-link" data-id="${collection.id}">
                    <div class="d-flex align-items-center">
                        <i class="fas fa-folder me-2"></i>
                        <span>${collection.name || 'Unnamed Collection'}</span>
                        <span class="badge bg-primary rounded-pill ms-2">${documentCount}</span>
                    </div>
                </a>
                <div class="btn-group btn-group-sm">
                    <button class="btn btn-outline-info btn-sm edit-collection" data-id="${collection.id}" title="Edit Collection">
                        <i class="fas fa-edit"></i>
                    </button>
                    <button class="btn btn-outline-danger btn-sm delete-collection" data-id="${collection.id}" title="Delete Collection">
                        <i class="fas fa-trash"></i>
                    </button>
                </div>
            `;
            
            elements.collectionsList.appendChild(item);
            
            // Add click events
            const collectionLink = item.querySelector('.collection-link');
            if (collectionLink) {
                collectionLink.addEventListener('click', (e) => {
                    e.preventDefault();
                    viewCollection(collection.id);
                });
            }
            
            const editBtn = item.querySelector('.edit-collection');
            if (editBtn) {
                editBtn.addEventListener('click', (e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    showEditCollectionModal(collection);
                });
            }
            
            const deleteBtn = item.querySelector('.delete-collection');
            if (deleteBtn) {
                deleteBtn.addEventListener('click', (e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    showDeleteCollectionConfirmation(collection.id, collection.name);
                });
            }
        });
    }

    // Create a new collection
    async function createCollection() {
        try {
            console.log("Creating collection function called");
            
            // Get form field references using more specific selectors
            const collectionNameInput = document.querySelector('#newCollectionForm #collectionName');
            const descriptionInput = document.querySelector('#newCollectionForm #collectionDescription');
            
            console.log("Form element lookup results:", {
                nameInput: collectionNameInput ? "found" : "missing",
                descriptionInput: descriptionInput ? "found" : "missing"
            });
            
            // Check if name input was found
            if (!collectionNameInput) {
                console.error("Collection name input not found");
                alert('Error: Collection name input not found');
                return;
            }
            
            // Safely get values
            const collectionName = collectionNameInput.value ? collectionNameInput.value.trim() : '';
            const description = descriptionInput && descriptionInput.value ? descriptionInput.value.trim() : '';
            
            console.log("Form values:", { collectionName, description });
            
            if (!collectionName) {
                console.warn("Collection name is empty");
                alert('Please enter a collection name');
                return;
            }
            
            // Disable the create button and show spinner
            if (elements.createCollectionBtn) {
                elements.createCollectionBtn.disabled = true;
                elements.createCollectionBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Creating...';
                console.log("Button disabled and spinner shown");
            }
            
            // Prepare request data
            const payload = {
                name: collectionName,
                description: description
            };
            console.log("Sending data:", payload);
            
            // Make the API request
            const response = await fetch('/collections', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(payload)
            });
            
            console.log("Response status:", response.status);
            
            // Parse response
            let data;
            try {
                data = await response.json();
                console.log("Response data:", data);
            } catch (parseError) {
                console.error("Error parsing JSON response:", parseError);
                const responseText = await response.text();
                console.log("Raw response:", responseText);
                throw new Error("Invalid response format");
            }
            
            // Close the modal regardless of success/failure
            hideModal('newCollectionModal');
            
            if (data.success) {
                console.log("Collection created successfully");
                
                // Clear form
                if (collectionNameInput) collectionNameInput.value = '';
                if (descriptionInput) descriptionInput.value = '';
                
                // Show success message
                alert(`Collection "${collectionName}" created successfully`);
                
                // Reload collections to show the new one
                loadCollections();
            } else {
                console.error("Error from server:", data.message);
                alert(`Error: ${data.message || 'Unknown error creating collection'}`);
            }
        } catch (error) {
            console.error("Exception creating collection:", error);
            alert(`Error creating collection: ${error.message}`);
        } finally {
            // Re-enable the button
            if (elements.createCollectionBtn) {
                elements.createCollectionBtn.disabled = false;
                elements.createCollectionBtn.innerHTML = 'Create Collection';
                console.log("Button re-enabled");
            }
        }
    }

    // View a single collection
    async function viewCollection(collectionId) {
        try {
            console.log(`Viewing collection: ${collectionId}`);
            
            if (!elements.collectionDetailTitle || !elements.collectionDescription || !elements.collectionDetailCard || !elements.collectionDocumentsList) {
                console.error("Cannot view collection: required DOM elements not found");
                return;
            }
            
            selectedCollectionId = collectionId;
            
            // Find the collection in the current list
            const collection = currentCollections.find(c => c.id == collectionId);
            
            if (!collection) {
                console.error(`Collection with ID ${collectionId} not found`);
                alert('Collection not found');
                return;
            }
            
            // Update UI with collection info
            elements.collectionDetailTitle.innerHTML = `<i class="fas fa-folder-open me-2"></i>${collection.name || 'Unnamed Collection'}`;
            elements.collectionDescription.textContent = collection.description || 'No description provided.';
            
            // Show the collection detail card
            elements.collectionDetailCard.style.display = 'block';
            
            // Load documents in this collection (would need to implement this API endpoint)
            // For now, just show a placeholder
            elements.collectionDocumentsList.innerHTML = `
                <li class="list-group-item list-group-item-dark">
                    Loading documents in this collection...
                </li>
            `;
            
            // When the add to collection button is clicked
            if (elements.addToCollectionBtn) {
                elements.addToCollectionBtn.onclick = () => {
                    prepareAddToCollection(collectionId);
                    showModal('addToCollectionModal');
                };
            }
        } catch (error) {
            console.error("Error viewing collection:", error);
            alert(`Error viewing collection: ${error.message}`);
        }
    }

    // Prepare the add to collection modal
    function prepareAddToCollection(collectionId) {
        try {
            console.log(`Preparing document selection for collection ${collectionId}`);
            
            if (!elements.documentSelectionList) {
                console.error("Cannot prepare document selection: documentSelectionList element not found");
                return;
            }
            
            if (!currentDocuments || currentDocuments.length === 0) {
                elements.documentSelectionList.innerHTML = `
                    <div class="list-group-item list-group-item-dark">
                        No documents available to add
                    </div>
                `;
                return;
            }
            
            elements.documentSelectionList.innerHTML = '';
            
            currentDocuments.forEach(doc => {
                if (!doc || !doc.id) {
                    console.warn("Skipping invalid document in prepareAddToCollection");
                    return;
                }
                
                const item = document.createElement('div');
                item.className = 'list-group-item list-group-item-dark';
                
                const safeTitle = doc.title || doc.filename || 'Untitled Document';
                
                item.innerHTML = `
                    <div class="form-check">
                        <input class="form-check-input" type="checkbox" value="${doc.id}" id="doc-check-${doc.id}">
                        <label class="form-check-label" for="doc-check-${doc.id}">
                            ${safeTitle}
                            <span class="badge bg-${doc.file_type === 'pdf' ? 'warning' : 'info'} ms-1">
                                ${doc.file_type === 'pdf' ? 'PDF' : 'Website'}
                            </span>
                        </label>
                    </div>
                `;
                
                elements.documentSelectionList.appendChild(item);
            });
        } catch (error) {
            console.error("Error preparing add to collection:", error);
            alert(`Error preparing document selection: ${error.message}`);
        }
    }

    // Add selected documents to the collection
    async function addDocumentsToCollection() {
        try {
            console.log("Adding documents to collection");
            
            if (!selectedCollectionId) {
                console.error("No collection selected");
                alert('Error: No collection selected');
                return;
            }
            
            const checkboxes = document.querySelectorAll('#documentSelectionList input[type="checkbox"]:checked');
            if (!checkboxes || checkboxes.length === 0) {
                console.warn("No documents selected");
                alert('Please select at least one document');
                return;
            }
            
            const selectedDocs = Array.from(checkboxes).map(cb => cb.value);
            console.log(`Selected ${selectedDocs.length} documents to add to collection ${selectedCollectionId}`);
            
            const successfullyAdded = [];
            
            // Add each document one by one
            for (const docId of selectedDocs) {
                try {
                    console.log(`Adding document ${docId} to collection ${selectedCollectionId}`);
                    
                    const response = await fetch(`/collections/${selectedCollectionId}/documents`, {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json'
                        },
                        body: JSON.stringify({
                            document_id: docId
                        })
                    });
                    
                    const data = await response.json();
                    
                    if (data.success) {
                        console.log(`Successfully added document ${docId} to collection`);
                        successfullyAdded.push(docId);
                    } else {
                        console.error(`Failed to add document ${docId} to collection:`, data.message);
                    }
                } catch (innerError) {
                    console.error(`Error adding document ${docId} to collection:`, innerError);
                }
            }
            
            // Close the modal
            hideModal('addToCollectionModal');
            
            // Show result
            if (successfullyAdded.length > 0) {
                if (successfullyAdded.length === selectedDocs.length) {
                    alert(`${successfullyAdded.length} document(s) added to collection successfully`);
                } else {
                    alert(`${successfullyAdded.length} of ${selectedDocs.length} document(s) added to collection`);
                }
                
                // Refresh the collection view
                viewCollection(selectedCollectionId);
            } else {
                alert('Failed to add any documents to collection');
            }
        } catch (error) {
            console.error("Error adding documents to collection:", error);
            alert(`Error adding documents to collection: ${error.message}`);
        }
    }

    // Show delete document confirmation
    function showDeleteConfirmation(docId, title) {
        try {
            console.log(`Showing delete confirmation for document ${docId}: "${title}"`);
            
            documentToDeleteId = docId;
            
            const nameElement = document.getElementById('deleteDocumentName');
            if (nameElement) {
                nameElement.textContent = title || 'this document';
            }
            
            // Show the modal
            showModal('deleteDocumentModal');
        } catch (error) {
            console.error("Error showing delete confirmation:", error);
            
            // Fallback if modal doesn't work
            const confirmDelete = confirm(`Do you want to delete "${title || 'this document'}"?`);
            if (confirmDelete) {
                deleteDocument();
            }
        }
    }

    // Delete a document
    async function deleteDocument() {
        try {
            if (!documentToDeleteId) {
                console.error("No document selected for deletion");
                return;
            }
            
            console.log(`Deleting document ${documentToDeleteId}`);
            
            const response = await fetch(`/documents/${documentToDeleteId}`, {
                method: 'DELETE'
            });
            
            const data = await response.json();
            
            // Close the modal
            hideModal('deleteDocumentModal');
            
            if (data.success) {
                console.log("Document deleted successfully");
                
                // Reload documents and collections
                loadDocuments();
                loadCollections();
                
                alert(data.message || 'Document deleted successfully');
            } else {
                console.error("Error deleting document:", data.message);
                alert(`Error: ${data.message || 'Unknown error deleting document'}`);
            }
        } catch (error) {
            console.error("Error deleting document:", error);
            alert(`Error deleting document: ${error.message}`);
        }
    }
    
    // Show edit collection modal
    function showEditCollectionModal(collection) {
        try {
            console.log(`Showing edit modal for collection ${collection.id}: "${collection.name}"`);
            
            const idInput = document.getElementById('editCollectionId');
            const nameInput = document.getElementById('editCollectionName');
            const descriptionInput = document.getElementById('editCollectionDescription');
            
            if (idInput) idInput.value = collection.id;
            if (nameInput) nameInput.value = collection.name || '';
            if (descriptionInput) descriptionInput.value = collection.description || '';
            
            // Show the modal
            showModal('editCollectionModal');
            
            // Set up update button click handler
            const updateBtn = document.getElementById('updateCollectionBtn');
            if (updateBtn) {
                // Remove any existing event listeners to prevent duplicates
                const newUpdateBtn = updateBtn.cloneNode(true);
                updateBtn.parentNode.replaceChild(newUpdateBtn, updateBtn);
                
                newUpdateBtn.addEventListener('click', updateCollection);
            }
        } catch (error) {
            console.error("Error showing edit collection modal:", error);
            alert(`Error preparing collection edit: ${error.message}`);
        }
    }
    
    // Update collection
    async function updateCollection() {
        try {
            console.log("Updating collection");
            
            const idInput = document.getElementById('editCollectionId');
            const nameInput = document.getElementById('editCollectionName');
            const descriptionInput = document.getElementById('editCollectionDescription');
            
            if (!idInput || !idInput.value) {
                console.error("No collection ID for update");
                alert('Error: Missing collection ID');
                return;
            }
            
            const collectionId = idInput.value;
            const name = nameInput ? nameInput.value.trim() : '';
            const description = descriptionInput ? descriptionInput.value.trim() : '';
            
            if (!name) {
                alert('Please enter a collection name');
                return;
            }
            
            // Disable the update button
            const updateBtn = document.getElementById('updateCollectionBtn');
            if (updateBtn) {
                updateBtn.disabled = true;
                updateBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Updating...';
            }
            
            // Prepare request data
            const payload = {
                name: name,
                description: description
            };
            
            console.log(`Updating collection ${collectionId} with data:`, payload);
            
            // Make the API request
            const response = await fetch(`/collections/${collectionId}`, {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(payload)
            });
            
            const data = await response.json();
            
            // Hide the modal
            hideModal('editCollectionModal');
            
            if (data.success) {
                console.log("Collection updated successfully");
                alert(data.message || 'Collection updated successfully');
                
                // Refresh collections
                loadCollections();
            } else {
                console.error("Error updating collection:", data.message);
                alert(`Error: ${data.message || 'Unknown error updating collection'}`);
            }
        } catch (error) {
            console.error("Error updating collection:", error);
            alert(`Error updating collection: ${error.message}`);
        } finally {
            // Re-enable the button
            const updateBtn = document.getElementById('updateCollectionBtn');
            if (updateBtn) {
                updateBtn.disabled = false;
                updateBtn.innerHTML = 'Save Changes';
            }
        }
    }
    
    // Show delete collection confirmation
    function showDeleteCollectionConfirmation(collectionId, name) {
        try {
            console.log(`Showing delete confirmation for collection ${collectionId}: "${name}"`);
            
            // Store the collection ID for deletion
            collectionToDeleteId = collectionId;
            
            // Set the name in the confirmation dialog
            const nameElement = document.getElementById('deleteCollectionName');
            if (nameElement) {
                nameElement.textContent = name || 'this collection';
            }
            
            // Show the modal
            showModal('deleteCollectionModal');
            
            // Set up delete button click handler
            const deleteBtn = document.getElementById('confirmDeleteCollectionBtn');
            if (deleteBtn) {
                // Remove any existing event listeners to prevent duplicates
                const newDeleteBtn = deleteBtn.cloneNode(true);
                deleteBtn.parentNode.replaceChild(newDeleteBtn, deleteBtn);
                
                newDeleteBtn.addEventListener('click', deleteCollection);
            }
        } catch (error) {
            console.error("Error showing delete collection confirmation:", error);
            
            // Fallback if modal doesn't work
            const confirmDelete = confirm(`Do you want to delete "${name || 'this collection'}"?`);
            if (confirmDelete) {
                deleteCollection();
            }
        }
    }
    
    // Delete a collection
    async function deleteCollection() {
        try {
            if (!collectionToDeleteId) {
                console.error("No collection selected for deletion");
                return;
            }
            
            console.log(`Deleting collection ${collectionToDeleteId}`);
            
            // Disable the delete button
            const deleteBtn = document.getElementById('confirmDeleteCollectionBtn');
            if (deleteBtn) {
                deleteBtn.disabled = true;
                deleteBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Deleting...';
            }
            
            const response = await fetch(`/collections/${collectionToDeleteId}`, {
                method: 'DELETE'
            });
            
            const data = await response.json();
            
            // Hide the modal
            hideModal('deleteCollectionModal');
            
            if (data.success) {
                console.log("Collection deleted successfully");
                
                // Reload collections
                loadCollections();
                
                // If we're viewing the deleted collection, clear the view
                if (selectedCollectionId == collectionToDeleteId) {
                    selectedCollectionId = null;
                    if (elements.collectionDetailCard) {
                        elements.collectionDetailCard.style.display = 'none';
                    }
                }
                
                alert(data.message || 'Collection deleted successfully');
            } else {
                console.error("Error deleting collection:", data.message);
                alert(`Error: ${data.message || 'Unknown error deleting collection'}`);
            }
        } catch (error) {
            console.error("Error deleting collection:", error);
            alert(`Error deleting collection: ${error.message}`);
        } finally {
            // Re-enable the button
            const deleteBtn = document.getElementById('confirmDeleteCollectionBtn');
            if (deleteBtn) {
                deleteBtn.disabled = false;
                deleteBtn.innerHTML = 'Delete Collection';
            }
        }
    }
    
    // Handle PDF form submission
    async function handlePdfFormSubmit(event) {
        event.preventDefault();
        
        if (!elements.pdfForm || !elements.pdfResult) {
            console.error("Cannot handle PDF form submit: required DOM elements not found");
            return;
        }
        
        // Validate form
        if (!elements.pdfForm.checkValidity()) {
            elements.pdfForm.classList.add('was-validated');
            return;
        }
        
        // Prepare UI for submission
        elements.pdfResult.innerHTML = '<div class="alert alert-info">Uploading PDF...</div>';
        const submitBtn = elements.pdfForm.querySelector('button[type="submit"]');
        submitBtn.disabled = true;
        
        try {
            // Get form data
            const formData = new FormData(elements.pdfForm);
            
            // Send request
            const response = await fetch('/upload_pdf', {
                method: 'POST',
                body: formData
            });
            
            const data = await response.json();
            
            if (data.success) {
                // Success message
                elements.pdfResult.innerHTML = `
                    <div class="alert alert-success">
                        <i class="fas fa-check-circle me-2"></i>
                        ${data.message}
                    </div>
                `;
                // Reset form
                elements.pdfForm.reset();
                elements.pdfForm.classList.remove('was-validated');
                
                // Refresh documents list
                loadDocuments();
            } else {
                // Error message
                elements.pdfResult.innerHTML = `
                    <div class="alert alert-danger">
                        <i class="fas fa-exclamation-circle me-2"></i>
                        ${data.message}
                    </div>
                `;
            }
        } catch (error) {
            // Exception message
            elements.pdfResult.innerHTML = `
                <div class="alert alert-danger">
                    <i class="fas fa-exclamation-circle me-2"></i>
                    Error: ${error.message}
                </div>
            `;
        } finally {
            // Re-enable submit button
            submitBtn.disabled = false;
        }
    }
    
    // Handle bulk PDF form submission
    async function handleBulkPdfFormSubmit(event) {
        event.preventDefault();
        
        if (!elements.bulkPdfForm || !elements.bulkPdfResult) {
            console.error("Cannot handle bulk PDF form submit: required DOM elements not found");
            return;
        }
        
        // Validate form
        if (!elements.bulkPdfForm.checkValidity()) {
            elements.bulkPdfForm.classList.add('was-validated');
            return;
        }
        
        // Check file count limit
        const fileInput = document.getElementById('bulk-pdf-files');
        if (fileInput.files.length > 5) {
            elements.bulkPdfResult.innerHTML = `
                <div class="alert alert-danger">
                    <i class="fas fa-exclamation-circle me-2"></i>
                    Too many files. Maximum 5 files allowed at once for reliable processing.
                </div>
            `;
            return;
        }
        
        if (fileInput.files.length === 0) {
            elements.bulkPdfResult.innerHTML = `
                <div class="alert alert-danger">
                    <i class="fas fa-exclamation-circle me-2"></i>
                    Please select at least one PDF file.
                </div>
            `;
            return;
        }
        
        // Prepare UI for submission - Step 1: Uploading
        const selectedFileCount = fileInput.files.length;
        elements.bulkPdfResult.innerHTML = `
            <div class="alert alert-info">
                <div class="d-flex align-items-center">
                    <div class="spinner-border spinner-border-sm me-2" role="status">
                        <span class="visually-hidden">Loading...</span>
                    </div>
                    <div>
                        <strong>Step 1/2:</strong> Uploading ${selectedFileCount} PDF file${selectedFileCount !== 1 ? 's' : ''}...
                        <div class="small text-muted mt-1">Please wait while the files are being uploaded...</div>
                    </div>
                </div>
            </div>
        `;
        
        const submitBtn = elements.bulkPdfForm.querySelector('button[type="submit"]');
        submitBtn.disabled = true;
        
        try {
            // Get form data
            const formData = new FormData(elements.bulkPdfForm);
            
            // Step 1: Upload files with a more reliable approach
            try {
                const uploadResponse = await fetch('/bulk_upload_pdfs', {
                    method: 'POST',
                    body: formData
                });
                
                // Check if response is valid
                if (!uploadResponse.ok) {
                    throw new Error(`Server returned ${uploadResponse.status}: ${uploadResponse.statusText}`);
                }
                
                const contentType = uploadResponse.headers.get('content-type');
                if (!contentType || !contentType.includes('application/json')) {
                    throw new Error('Server returned an invalid response format. The server might be overloaded.');
                }
                
                const uploadData = await uploadResponse.json();
                
                if (!uploadData.success) {
                    throw new Error(uploadData.message || 'Failed to upload files');
                }
                
                // If we reach here, upload was successful
                const uploadedCount = uploadData.document_ids ? uploadData.document_ids.length : selectedFileCount;
                elements.bulkPdfResult.innerHTML = `
                    <div class="alert alert-info">
                        <div class="d-flex align-items-center">
                            <div class="spinner-border spinner-border-sm me-2" role="status">
                                <span class="visually-hidden">Loading...</span>
                            </div>
                            <div>
                                <strong>Step 2/2:</strong> Processing ${uploadedCount} PDF file${uploadedCount !== 1 ? 's' : ''} with citation extraction...
                                <div class="small text-muted mt-1">This may take several minutes. You can continue using the app.</div>
                                <div class="small text-muted mt-1">Processing large PDFs may take 1-2 minutes per file.</div>
                                <div class="progress mt-2">
                                    <div class="progress-bar progress-bar-striped progress-bar-animated" 
                                        role="progressbar" style="width: 0%" 
                                        aria-valuenow="0" aria-valuemin="0" aria-valuemax="100">0%</div>
                                </div>
                            </div>
                        </div>
                    </div>
                `;
                
                // Reset form
                elements.bulkPdfForm.reset();
                elements.bulkPdfForm.classList.remove('was-validated');
                
                // Refresh documents list to show the pending documents
                loadDocuments();
                
                // Show success message and indicate background processing
                setTimeout(() => {
                    // Use the same uploaded count variable we defined earlier
                    elements.bulkPdfResult.innerHTML = `
                        <div class="alert alert-success">
                            <i class="fas fa-check-circle me-2"></i>
                            Successfully uploaded ${uploadedCount} PDF file${uploadedCount !== 1 ? 's' : ''}. 
                            ${uploadedCount > 0 ? 'The first document should be processed immediately and viewable now.' : ''}
                            ${uploadedCount > 1 ? 'Additional documents will be processed in the background.' : ''}
                            <div class="small text-muted mt-1">You can continue using the app while processing completes.</div>
                        </div>
                    `;
                }, 3000);
                
            } catch (uploadError) {
                // Handle upload errors
                console.error("Upload error:", uploadError);
                elements.bulkPdfResult.innerHTML = `
                    <div class="alert alert-danger">
                        <i class="fas fa-exclamation-circle me-2"></i>
                        Upload failed: ${uploadError.message}
                    </div>
                `;
            }
            
        } catch (error) {
            // Final exception fallback
            elements.bulkPdfResult.innerHTML = `
                <div class="alert alert-danger">
                    <i class="fas fa-exclamation-circle me-2"></i>
                    Error: ${error.message}
                </div>
            `;
        } finally {
            // Re-enable submit button
            submitBtn.disabled = false;
        }
    }
    
    // Handle website form submission
    async function handleWebsiteFormSubmit(event) {
        event.preventDefault();
        
        if (!elements.websiteForm || !elements.websiteResult) {
            console.error("Cannot handle website form submit: required DOM elements not found");
            return;
        }
        
        // Validate form
        if (!elements.websiteForm.checkValidity()) {
            elements.websiteForm.classList.add('was-validated');
            return;
        }
        
        // Prepare UI for submission
        elements.websiteResult.innerHTML = '<div class="alert alert-info">Processing website... This may take a minute or two.</div>';
        const submitBtn = elements.websiteForm.querySelector('button[type="submit"]');
        submitBtn.disabled = true;
        
        try {
            // Get form data
            const formData = new FormData(elements.websiteForm);
            
            // Send request
            const response = await fetch('/add_website', {
                method: 'POST',
                body: formData
            });
            
            const data = await response.json();
            
            if (data.success) {
                // Success message
                elements.websiteResult.innerHTML = `
                    <div class="alert alert-success">
                        <i class="fas fa-check-circle me-2"></i>
                        ${data.message}
                    </div>
                `;
                // Reset form
                elements.websiteForm.reset();
                elements.websiteForm.classList.remove('was-validated');
                
                // Refresh documents list
                loadDocuments();
            } else {
                // Error message
                elements.websiteResult.innerHTML = `
                    <div class="alert alert-danger">
                        <i class="fas fa-exclamation-circle me-2"></i>
                        ${data.message}
                    </div>
                `;
            }
        } catch (error) {
            // Exception message
            elements.websiteResult.innerHTML = `
                <div class="alert alert-danger">
                    <i class="fas fa-exclamation-circle me-2"></i>
                    Error: ${error.message}
                </div>
            `;
        } finally {
            // Re-enable submit button
            submitBtn.disabled = false;
        }
    }
    
    // Handle topic pages form submission with button click
    async function handleTopicPagesSubmit(event) {
        event.preventDefault();
        
        if (!elements.topicPagesForm || !elements.topicPagesResult) {
            console.error("Cannot handle topic pages form submit: required DOM elements not found");
            return;
        }
        
        // Validate form
        if (!elements.topicPagesForm.checkValidity()) {
            elements.topicPagesForm.classList.add('was-validated');
            return;
        }
        
        // Get topics from textarea (use elements object which is more reliable)
        const topicListElement = document.getElementById('topic-list');
        if (!topicListElement) {
            elements.topicPagesResult.innerHTML = `
                <div class="alert alert-danger">
                    <i class="fas fa-exclamation-circle me-2"></i>
                    Error: Unable to find topic list textarea. Please try refreshing the page.
                </div>
            `;
            return;
        }
        
        const topicList = topicListElement.value.trim();
        if (!topicList) {
            elements.topicPagesResult.innerHTML = `
                <div class="alert alert-danger">
                    <i class="fas fa-exclamation-circle me-2"></i>
                    Please enter at least one topic.
                </div>
            `;
            return;
        }
        
        // Split topics by line
        const topics = topicList.split('\n')
            .map(topic => topic.trim())
            .filter(topic => topic.length > 0);
        
        if (topics.length === 0) {
            elements.topicPagesResult.innerHTML = `
                <div class="alert alert-danger">
                    <i class="fas fa-exclamation-circle me-2"></i>
                    Please enter at least one valid topic.
                </div>
            `;
            return;
        }
        
        if (topics.length > 5) {
            elements.topicPagesResult.innerHTML = `
                <div class="alert alert-danger">
                    <i class="fas fa-exclamation-circle me-2"></i>
                    You can only process up to 5 topics at once. Please reduce the number of topics.
                </div>
            `;
            return;
        }
        
        // Prepare UI for submission
        elements.topicPagesResult.innerHTML = `
            <div class="alert alert-info">
                <i class="fas fa-spinner fa-spin me-2"></i>
                Processing ${topics.length} topic pages... This may take several minutes.
            </div>
        `;
        const submitBtn = document.getElementById('add-topics-btn');
        submitBtn.disabled = true;
        
        try {
            // Send request using simple URLSearchParams for better compatibility
            const formData = new URLSearchParams();
            formData.append('topic_list', topics.join('\n'));
            
            const response = await fetch('/add_topic_pages', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded',
                },
                body: formData
            });
            
            // Check if response is OK and contains JSON
            if (!response.ok) {
                throw new Error(`Server returned status ${response.status}: ${response.statusText}`);
            }
            
            // Try to parse as JSON with error handling
            let data;
            try {
                const text = await response.text();
                data = JSON.parse(text);
            } catch (parseError) {
                console.error("Error parsing JSON response:", parseError);
                throw new Error("Server returned an invalid response format. Please try again.");
            }
            
            if (data.success) {
                // Success message
                let successHtml = `
                    <div class="alert alert-success">
                        <i class="fas fa-check-circle me-2"></i>
                        ${data.message}
                    </div>
                `;
                
                // Add details if available
                if (data.processed && data.processed.length > 0) {
                    successHtml += '<div class="mt-3"><h6>Successfully processed topics:</h6><ul class="list-group">';
                    data.processed.forEach(item => {
                        successHtml += `
                            <li class="list-group-item bg-dark text-light">
                                <strong>${item.topic}</strong> - ${item.chunks} chunks
                            </li>
                        `;
                    });
                    successHtml += '</ul></div>';
                }
                
                // Add failed topics if any
                if (data.failed && data.failed.length > 0) {
                    successHtml += '<div class="mt-3"><h6>Failed topics:</h6><ul class="list-group">';
                    data.failed.forEach(item => {
                        successHtml += `
                            <li class="list-group-item bg-dark text-light border-danger">
                                <strong>${item.topic}</strong> - ${item.reason}
                            </li>
                        `;
                    });
                    successHtml += '</ul></div>';
                }
                
                elements.topicPagesResult.innerHTML = successHtml;
                
                // Reset form
                elements.topicPagesForm.reset();
                elements.topicPagesForm.classList.remove('was-validated');
                
                // Refresh documents list
                loadDocuments();
            } else {
                // Error message
                elements.topicPagesResult.innerHTML = `
                    <div class="alert alert-danger">
                        <i class="fas fa-exclamation-circle me-2"></i>
                        ${data.message}
                    </div>
                `;
                
                // Add failed topics if any
                if (data.failed && data.failed.length > 0) {
                    let errorHtml = '<div class="mt-3"><h6>Failed topics:</h6><ul class="list-group">';
                    data.failed.forEach(item => {
                        errorHtml += `
                            <li class="list-group-item bg-dark text-light border-danger">
                                <strong>${item.topic}</strong> - ${item.reason}
                            </li>
                        `;
                    });
                    errorHtml += '</ul></div>';
                    elements.topicPagesResult.innerHTML += errorHtml;
                }
            }
        } catch (error) {
            // Exception message
            elements.topicPagesResult.innerHTML = `
                <div class="alert alert-danger">
                    <i class="fas fa-exclamation-circle me-2"></i>
                    Error: ${error.message}
                </div>
            `;
        } finally {
            // Re-enable submit button (safely)
            if (submitBtn) {
                submitBtn.disabled = false;
            } else {
                // Try to find it another way if the reference is lost
                const altBtn = document.getElementById('add-topics-btn');
                if (altBtn) {
                    altBtn.disabled = false;
                }
            }
        }
    }
});

// Global function to load more content for a document
async function loadMoreContent(documentId) {
    try {
        const loadMoreBtn = document.getElementById('loadMoreContentBtn');
        const statusEl = document.getElementById('loadMoreStatus');
        
        if (!loadMoreBtn || !statusEl) {
            console.error("Load more button or status element not found");
            return;
        }
        
        // Show loading state
        loadMoreBtn.disabled = true;
        loadMoreBtn.innerHTML = `
            <span class="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span>
            Loading...
        `;
        statusEl.style.display = 'block';
        statusEl.innerHTML = `
            <div class="alert alert-secondary">
                <i class="fas fa-sync fa-spin me-2"></i>
                Loading additional content for this document...
            </div>
        `;
        
        // Call API to load more content
        const response = await fetch(`/documents/${documentId}/load_more_content`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        });
        
        const data = await response.json();
        
        if (data.success) {
            // Show success message
            statusEl.innerHTML = `
                <div class="alert alert-success">
                    <i class="fas fa-check-circle me-2"></i>
                    Successfully loaded ${data.chunks_loaded} additional chunks! 
                    Now showing ${data.total_chunks_now} of ${data.total_possible_chunks} chunks.
                </div>
            `;
            
            // Reload the document view to show updated chunks
            setTimeout(() => {
                viewDocument(documentId);
            }, 1500);
        } else {
            // Show error message
            statusEl.innerHTML = `
                <div class="alert alert-danger">
                    <i class="fas fa-exclamation-circle me-2"></i>
                    ${data.message || 'Error loading additional content'}
                </div>
            `;
            
            // Re-enable the button
            loadMoreBtn.disabled = false;
            loadMoreBtn.innerHTML = `
                <i class="fas fa-cloud-download-alt me-2"></i>
                Try Again
            `;
        }
    } catch (error) {
        console.error("Error loading more content:", error);
        
        const statusEl = document.getElementById('loadMoreStatus');
        const loadMoreBtn = document.getElementById('loadMoreContentBtn');
        
        if (statusEl) {
            statusEl.style.display = 'block';
            statusEl.innerHTML = `
                <div class="alert alert-danger">
                    <i class="fas fa-exclamation-circle me-2"></i>
                    Error: ${error.message}
                </div>
            `;
        }
        
        if (loadMoreBtn) {
            loadMoreBtn.disabled = false;
            loadMoreBtn.innerHTML = `
                <i class="fas fa-cloud-download-alt me-2"></i>
                Try Again
            `;
        }
    }
}

// Global function to manually process a document
async function processDocument(documentId) {
    try {
        const processBtn = document.getElementById('processDocBtn');
        const statusEl = document.getElementById('processStatus');
        
        if (!processBtn || !statusEl) {
            console.error("Process button or status element not found");
            return;
        }
        
        // Show loading state
        processBtn.disabled = true;
        processBtn.innerHTML = `
            <span class="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span>
            Processing...
        `;
        
        statusEl.innerHTML = `
            <div class="alert alert-info">
                <i class="fas fa-sync fa-spin me-2"></i>
                Processing document. This may take a minute or two...
            </div>
        `;
        
        // Call API to process the document
        const response = await fetch(`/documents/${documentId}/process`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        });
        
        const data = await response.json();
        
        if (data.success) {
            // Show success message
            statusEl.innerHTML = `
                <div class="alert alert-success">
                    <i class="fas fa-check-circle me-2"></i>
                    ${data.message}
                    ${data.doi_found ? '<div>✓ DOI information extracted</div>' : ''}
                    ${data.citation_found ? '<div>✓ Citation information extracted</div>' : ''}
                    ${data.chunks_added > 0 ? `<div>✓ ${data.chunks_added} content chunks processed</div>` : ''}
                </div>
            `;
            
            // Reload the document view to show updated information
            setTimeout(() => {
                viewDocument(documentId);
            }, 2000);
        } else {
            // Show error message
            statusEl.innerHTML = `
                <div class="alert alert-danger">
                    <i class="fas fa-exclamation-circle me-2"></i>
                    ${data.message || 'Error processing document'}
                </div>
            `;
            
            // Re-enable the button
            processBtn.disabled = false;
            processBtn.innerHTML = `
                <i class="fas fa-cogs me-1"></i> Process Document
            `;
        }
    } catch (error) {
        console.error("Error processing document:", error);
        
        const statusEl = document.getElementById('processStatus');
        const processBtn = document.getElementById('processDocBtn');
        
        if (statusEl) {
            statusEl.innerHTML = `
                <div class="alert alert-danger">
                    <i class="fas fa-exclamation-circle me-2"></i>
                    Error: ${error.message}
                </div>
            `;
        }
        
        if (processBtn) {
            processBtn.disabled = false;
            processBtn.innerHTML = `
                <i class="fas fa-cogs me-1"></i> Process Document
            `;
        }
    }
}