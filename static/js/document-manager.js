document.addEventListener('DOMContentLoaded', () => {
    // Check if we are on the manage page
    if (!document.getElementById('documentsTableBody')) return;

    // Document elements
    const documentsTableBody = document.getElementById('documentsTableBody');
    const documentDetailContainer = document.getElementById('documentDetailContainer');
    const documentsTableContainer = document.getElementById('documentsTableContainer');
    const documentDetailContent = document.getElementById('documentDetailContent');
    const backToDocumentsBtn = document.getElementById('backToDocumentsBtn');
    const refreshDocumentsBtn = document.getElementById('refreshDocumentsBtn');
    const newCollectionBtn = document.getElementById('newCollectionBtn');
    const createCollectionBtn = document.getElementById('createCollectionBtn');
    const collectionsList = document.getElementById('collectionsList');
    const collectionDetailCard = document.getElementById('collectionDetailCard');
    const collectionDetailTitle = document.getElementById('collectionDetailTitle');
    const collectionDescription = document.getElementById('collectionDescription');
    const collectionDocumentsList = document.getElementById('collectionDocumentsList');
    const addToCollectionBtn = document.getElementById('addToCollectionBtn');
    const documentSelectionList = document.getElementById('documentSelectionList');
    const confirmAddToCollectionBtn = document.getElementById('confirmAddToCollectionBtn');
    const confirmDeleteBtn = document.getElementById('confirmDeleteBtn');

    // Global state
    let currentDocuments = [];
    let currentCollections = [];
    let selectedCollectionId = null;
    let documentToDeleteId = null;

    // Initialize
    loadDocuments();
    loadCollections();

    // Event listeners
    if (refreshDocumentsBtn) {
        refreshDocumentsBtn.addEventListener('click', loadDocuments);
    }

    if (backToDocumentsBtn) {
        backToDocumentsBtn.addEventListener('click', () => {
            documentDetailContainer.classList.add('d-none');
            documentsTableContainer.classList.remove('d-none');
        });
    }

    if (createCollectionBtn) {
        createCollectionBtn.addEventListener('click', createCollection);
    }

    if (confirmAddToCollectionBtn) {
        confirmAddToCollectionBtn.addEventListener('click', addDocumentsToCollection);
    }

    if (confirmDeleteBtn) {
        confirmDeleteBtn.addEventListener('click', deleteDocument);
    }

    // Functions

    // Load all documents
    async function loadDocuments() {
        try {
            documentsTableBody.innerHTML = '<tr><td colspan="5" class="text-center">Loading documents...</td></tr>';
            
            const response = await fetch('/documents');
            const data = await response.json();
            
            if (data.success) {
                currentDocuments = data.documents;
                renderDocumentsTable();
            } else {
                documentsTableBody.innerHTML = `
                    <tr>
                        <td colspan="5" class="text-center text-danger">
                            <i class="fas fa-exclamation-circle me-2"></i>
                            ${data.message}
                        </td>
                    </tr>
                `;
            }
        } catch (error) {
            documentsTableBody.innerHTML = `
                <tr>
                    <td colspan="5" class="text-center text-danger">
                        <i class="fas fa-exclamation-circle me-2"></i>
                        Error loading documents: ${error.message}
                    </td>
                </tr>
            `;
        }
    }

    // Render documents table
    function renderDocumentsTable() {
        if (currentDocuments.length === 0) {
            documentsTableBody.innerHTML = `
                <tr>
                    <td colspan="5" class="text-center">
                        No documents found. Upload documents from the search page.
                    </td>
                </tr>
            `;
            return;
        }

        documentsTableBody.innerHTML = '';
        
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
                sizeInfo = `${doc.chunk_count} chunks`;
            }
            
            row.innerHTML = `
                <td>
                    <strong>${doc.title || doc.filename}</strong>
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
                        <button type="button" class="btn btn-sm btn-outline-danger delete-doc-btn" data-id="${doc.id}" data-title="${doc.title || doc.filename}">
                            <i class="fas fa-trash"></i>
                        </button>
                    </div>
                </td>
            `;
            
            documentsTableBody.appendChild(row);
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
            documentDetailContent.innerHTML = '<p class="text-center">Loading document details...</p>';
            documentDetailContainer.classList.remove('d-none');
            documentsTableContainer.classList.add('d-none');
            
            const response = await fetch(`/documents/${docId}`);
            const data = await response.json();
            
            if (data.success) {
                const doc = data.document;
                const createdDate = new Date(doc.created_at);
                const dateStr = createdDate.toLocaleDateString();
                
                // Build detailed view
                let html = `
                    <h4>${doc.title || doc.filename}</h4>
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
                } else {
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
                            <span>${doc.chunks.length}</span>
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
                const maxChunks = Math.min(3, doc.chunks.length);
                if (doc.chunks.length > 0) {
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
                
                documentDetailContent.innerHTML = html;
                
                // Load collections for this document (Would need to implement this endpoint)
                // loadDocumentCollections(docId);
            } else {
                documentDetailContent.innerHTML = `
                    <div class="alert alert-danger" role="alert">
                        <i class="fas fa-exclamation-circle me-2"></i>
                        ${data.message}
                    </div>
                `;
            }
        } catch (error) {
            documentDetailContent.innerHTML = `
                <div class="alert alert-danger" role="alert">
                    <i class="fas fa-exclamation-circle me-2"></i>
                    Error loading document: ${error.message}
                </div>
            `;
        }
    }

    // Load all collections
    async function loadCollections() {
        try {
            collectionsList.innerHTML = '<div class="list-group-item list-group-item-dark">Loading collections...</div>';
            
            const response = await fetch('/collections');
            const data = await response.json();
            
            if (data.success) {
                currentCollections = data.collections;
                renderCollectionsList();
            } else {
                collectionsList.innerHTML = `
                    <div class="list-group-item list-group-item-dark text-danger">
                        <i class="fas fa-exclamation-circle me-2"></i>
                        ${data.message}
                    </div>
                `;
            }
        } catch (error) {
            collectionsList.innerHTML = `
                <div class="list-group-item list-group-item-dark text-danger">
                    <i class="fas fa-exclamation-circle me-2"></i>
                    Error loading collections: ${error.message}
                </div>
            `;
        }
    }

    // Render collections list
    function renderCollectionsList() {
        if (currentCollections.length === 0) {
            collectionsList.innerHTML = `
                <div class="list-group-item list-group-item-dark">
                    No collections found. Create a new collection to organize your documents.
                </div>
            `;
            return;
        }

        collectionsList.innerHTML = '';
        
        currentCollections.forEach(collection => {
            const item = document.createElement('a');
            item.href = '#';
            item.className = 'list-group-item list-group-item-action d-flex justify-content-between align-items-center';
            item.dataset.id = collection.id;
            
            item.innerHTML = `
                <div>
                    <i class="fas fa-folder me-2"></i>
                    <span>${collection.name}</span>
                </div>
                <span class="badge bg-primary rounded-pill">${collection.document_count}</span>
            `;
            
            collectionsList.appendChild(item);
            
            // Add click event
            item.addEventListener('click', (e) => {
                e.preventDefault();
                viewCollection(collection.id);
            });
        });
    }

    // Create a new collection
    async function createCollection() {
        console.log("Creating collection...");
        const collectionName = document.getElementById('collectionName').value.trim();
        const description = document.getElementById('collectionDescription').value.trim();
        
        if (!collectionName) {
            alert('Please enter a collection name');
            return;
        }
        
        try {
            // Disable the button to prevent multiple submissions
            const createButton = document.getElementById('createCollectionBtn');
            if (createButton) {
                createButton.disabled = true;
                createButton.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Creating...';
            }
            
            console.log("Sending data:", { name: collectionName, description });
            
            const response = await fetch('/collections', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    name: collectionName,
                    description: description
                })
            });
            
            const data = await response.json();
            console.log("Response:", data);
            
            if (data.success) {
                // Close modal - use jQuery method since Bootstrap might not be accessible directly
                $('#newCollectionModal').modal('hide');
                
                // Clear form
                document.getElementById('collectionName').value = '';
                document.getElementById('collectionDescription').value = '';
                
                // Reload collections
                loadCollections();
                
                // Show success message
                alert(`Collection "${collectionName}" created successfully`);
            } else {
                alert(`Error: ${data.message}`);
            }
        } catch (error) {
            alert(`Error creating collection: ${error.message}`);
        }
    }

    // View a single collection
    async function viewCollection(collectionId) {
        selectedCollectionId = collectionId;
        
        // Find the collection in the current list
        const collection = currentCollections.find(c => c.id == collectionId);
        
        if (!collection) {
            alert('Collection not found');
            return;
        }
        
        // Update UI with collection info
        collectionDetailTitle.innerHTML = `<i class="fas fa-folder-open me-2"></i>${collection.name}`;
        collectionDescription.textContent = collection.description || 'No description provided.';
        
        // Show the collection detail card
        collectionDetailCard.style.display = 'block';
        
        // Load documents in this collection (would need to implement this API endpoint)
        // For now, just show a placeholder
        collectionDocumentsList.innerHTML = `
            <li class="list-group-item list-group-item-dark">
                Loading documents in this collection...
            </li>
        `;
        
        // When the add to collection button is clicked
        addToCollectionBtn.onclick = () => prepareAddToCollection(collectionId);
    }

    // Prepare the add to collection modal
    function prepareAddToCollection(collectionId) {
        if (!currentDocuments || currentDocuments.length === 0) {
            documentSelectionList.innerHTML = `
                <div class="list-group-item list-group-item-dark">
                    No documents available to add
                </div>
            `;
            return;
        }
        
        documentSelectionList.innerHTML = '';
        
        currentDocuments.forEach(doc => {
            const item = document.createElement('div');
            item.className = 'list-group-item list-group-item-dark';
            
            item.innerHTML = `
                <div class="form-check">
                    <input class="form-check-input" type="checkbox" value="${doc.id}" id="doc-check-${doc.id}">
                    <label class="form-check-label" for="doc-check-${doc.id}">
                        ${doc.title || doc.filename}
                        <span class="badge bg-${doc.file_type === 'pdf' ? 'warning' : 'info'} ms-1">
                            ${doc.file_type === 'pdf' ? 'PDF' : 'Website'}
                        </span>
                    </label>
                </div>
            `;
            
            documentSelectionList.appendChild(item);
        });
    }

    // Add selected documents to the collection
    async function addDocumentsToCollection() {
        const selectedDocs = Array.from(document.querySelectorAll('#documentSelectionList input[type="checkbox"]:checked'))
            .map(cb => cb.value);
        
        if (selectedDocs.length === 0) {
            alert('Please select at least one document');
            return;
        }
        
        try {
            const successfullyAdded = [];
            
            // Add each document one by one
            for (const docId of selectedDocs) {
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
                    successfullyAdded.push(docId);
                }
            }
            
            // Close modal using jQuery
            $('#addToCollectionModal').modal('hide');
            
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
            alert(`Error adding documents to collection: ${error.message}`);
        }
    }

    // Show delete document confirmation
    function showDeleteConfirmation(docId, title) {
        documentToDeleteId = docId;
        document.getElementById('deleteDocumentName').textContent = title;
        
        // Show the modal
        const modal = new bootstrap.Modal(document.getElementById('deleteDocumentModal'));
        modal.show();
    }

    // Delete a document
    async function deleteDocument() {
        if (!documentToDeleteId) return;
        
        try {
            const response = await fetch(`/documents/${documentToDeleteId}`, {
                method: 'DELETE'
            });
            
            const data = await response.json();
            
            // Close the modal using jQuery
            $('#deleteDocumentModal').modal('hide');
            
            if (data.success) {
                // Reload documents
                loadDocuments();
                // Also reload collections as the document counts may have changed
                loadCollections();
                alert(data.message);
            } else {
                alert(`Error: ${data.message}`);
            }
        } catch (error) {
            alert(`Error deleting document: ${error.message}`);
        }
    }
});