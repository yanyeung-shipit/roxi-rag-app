document.addEventListener('DOMContentLoaded', () => {
    console.log("Document Manager script loaded");
    
    // Check if we are on the manage page
    if (!document.getElementById('documentsTableBody')) {
        console.log("Not on manage page, exiting script");
        return;
    }
    
    // DOM element references - all elements are optional and get checked before use
    const elements = {
        // Document elements
        documentsTableBody: document.getElementById('documentsTableBody'),
        documentDetailContainer: document.getElementById('documentDetailContainer'),
        documentsTableContainer: document.getElementById('documentsTableContainer'),
        documentDetailContent: document.getElementById('documentDetailContent'),
        backToDocumentsBtn: document.getElementById('backToDocumentsBtn'),
        refreshDocumentsBtn: document.getElementById('refreshDocumentsBtn'),
        
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

    // Initialize
    loadDocuments();
    loadCollections();

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
        
        // Document navigation
        safeAddEventListener('refreshDocumentsBtn', 'click', loadDocuments);
        safeAddEventListener('backToDocumentsBtn', 'click', () => {
            if (elements.documentDetailContainer && elements.documentsTableContainer) {
                elements.documentDetailContainer.classList.add('d-none');
                elements.documentsTableContainer.classList.remove('d-none');
            }
        });
        
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
                return;
            }
        } catch (error1) {
            console.warn("Bootstrap 5 modal hide failed:", error1);
        }
        
        try {
            // Try jQuery way
            $(modalElement).modal('hide');
            console.log("Modal hidden using jQuery");
            return;
        } catch (error2) {
            console.warn("jQuery modal hide failed:", error2);
            
            try {
                // Manual way
                modalElement.classList.remove('show');
                modalElement.style.display = 'none';
                document.body.classList.remove('modal-open');
                
                // Remove backdrop
                const backdrop = document.querySelector('.modal-backdrop');
                if (backdrop) {
                    backdrop.parentNode.removeChild(backdrop);
                }
                console.log("Modal hidden manually by DOM manipulation");
            } catch (error3) {
                console.error("Manual modal hide failed:", error3);
            }
        }
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
            
            const item = document.createElement('a');
            item.href = '#';
            item.className = 'list-group-item list-group-item-action d-flex justify-content-between align-items-center';
            item.dataset.id = collection.id;
            
            const documentCount = collection.document_count || 0;
            
            item.innerHTML = `
                <div>
                    <i class="fas fa-folder me-2"></i>
                    <span>${collection.name || 'Unnamed Collection'}</span>
                </div>
                <span class="badge bg-primary rounded-pill">${documentCount}</span>
            `;
            
            elements.collectionsList.appendChild(item);
            
            // Add click event
            item.addEventListener('click', (e) => {
                e.preventDefault();
                viewCollection(collection.id);
            });
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
});