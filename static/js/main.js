document.addEventListener('DOMContentLoaded', () => {
    // Form elements
    const websiteForm = document.getElementById('websiteForm');
    const pdfForm = document.getElementById('pdfForm');
    const queryForm = document.getElementById('queryForm');
    const clearKnowledgeBtn = document.getElementById('clearKnowledgeBtn');
    
    // Results containers
    const websiteResult = document.getElementById('websiteResult');
    const pdfResult = document.getElementById('pdfResult');
    const answerContent = document.getElementById('answerContent');
    const sourcesList = document.getElementById('sourcesList');
    const sourcesHeader = document.getElementById('sourcesHeader');
    const answerSpinner = document.getElementById('answerSpinner');
    const statsContent = document.getElementById('statsContent');
    
    // Load initial stats
    fetchStats();
    
    // Website form submission
    websiteForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const formData = new FormData(websiteForm);
        const url = formData.get('website_url');
        
        if (!url) {
            showResult(websiteResult, 'Please enter a valid URL', false);
            return;
        }
        
        try {
            websiteResult.innerHTML = `
                <div class="alert alert-info" role="alert">
                    <div class="d-flex align-items-center">
                        <div class="spinner-border spinner-border-sm me-2" role="status">
                            <span class="visually-hidden">Loading...</span>
                        </div>
                        <div>Processing website...</div>
                    </div>
                </div>
            `;
            
            const response = await fetch('/add_website', {
                method: 'POST',
                body: formData
            });
            
            const data = await response.json();
            
            if (data.success) {
                showResult(websiteResult, `${data.message} (${data.chunks} chunks extracted)`, true);
                fetchStats();
            } else {
                showResult(websiteResult, data.message, false);
            }
        } catch (error) {
            showResult(websiteResult, `Error: ${error.message}`, false);
        }
    });
    
    // PDF form submission
    pdfForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const formData = new FormData(pdfForm);
        const file = formData.get('pdf_file');
        
        if (!file || file.size === 0) {
            showResult(pdfResult, 'Please select a PDF file', false);
            return;
        }
        
        try {
            pdfResult.innerHTML = `
                <div class="alert alert-info" role="alert">
                    <div class="d-flex align-items-center">
                        <div class="spinner-border spinner-border-sm me-2" role="status">
                            <span class="visually-hidden">Loading...</span>
                        </div>
                        <div>Processing PDF...</div>
                    </div>
                </div>
            `;
            
            const response = await fetch('/upload_pdf', {
                method: 'POST',
                body: formData,
                // Disable automatic redirect following
                redirect: 'manual'
            });
            
            // Check if the response is ok before parsing
            if (!response.ok) {
                const errorText = await response.text();
                throw new Error(`Server error: ${response.status} ${errorText.substring(0, 100)}`);
            }
            
            const data = await response.json();
            
            if (data.success) {
                showResult(pdfResult, `${data.message} (${data.chunks} chunks extracted)`, true);
                fetchStats();
            } else {
                showResult(pdfResult, data.message, false);
            }
        } catch (error) {
            showResult(pdfResult, `Error: ${error.message}`, false);
        }
    });
    
    // Query form submission
    queryForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const formData = new FormData(queryForm);
        const query = formData.get('query');
        
        if (!query.trim()) {
            return;
        }
        
        // Show spinner, hide content
        answerSpinner.classList.remove('d-none');
        answerContent.innerHTML = '';
        sourcesList.innerHTML = '';
        sourcesHeader.classList.add('d-none');
        
        try {
            const response = await fetch('/query', {
                method: 'POST',
                body: formData
            });
            
            const data = await response.json();
            
            // Hide spinner
            answerSpinner.classList.add('d-none');
            
            if (data.success) {
                // Display answer
                answerContent.innerHTML = `<p>${formatAnswer(data.answer, data.sources)}</p>`;
                
                // Display sources
                if (data.sources && data.sources.length > 0) {
                    sourcesHeader.classList.remove('d-none');
                    
                    data.sources.forEach((source, index) => {
                        const sourceItem = document.createElement('div');
                        sourceItem.className = 'source-item';
                        sourceItem.id = `source-${index + 1}`;
                        
                        // Get citation text - use APA citation if available, otherwise use default
                        let citationText = '';
                        
                        if (source.citation) {
                            // Use provided citation in APA format
                            citationText = source.citation;
                        } else if (source.source_type === 'pdf') {
                            // Fallback for PDF without citation
                            citationText = `${source.title} (page ${source.page})`;
                        } else {
                            // Fallback for website without citation
                            citationText = `${source.title}. Retrieved from ${source.url}`;
                        }
                        
                        sourceItem.innerHTML = `
                            <div class="source-title">
                                <span class="badge bg-info me-2">${index + 1}</span>
                                ${source.source_type === 'pdf' ? 
                                    `<i class="fas fa-file-pdf me-1"></i>` : 
                                    `<i class="fas fa-globe me-1"></i>`
                                }
                            </div>
                            <div class="source-citation">${citationText}</div>
                        `;
                        
                        sourcesList.appendChild(sourceItem);
                    });
                }
            } else {
                answerContent.innerHTML = `
                    <div class="alert alert-danger" role="alert">
                        <i class="fas fa-exclamation-circle me-2"></i>
                        ${data.message}
                    </div>
                `;
            }
        } catch (error) {
            answerSpinner.classList.add('d-none');
            answerContent.innerHTML = `
                <div class="alert alert-danger" role="alert">
                    <i class="fas fa-exclamation-circle me-2"></i>
                    Error: ${error.message}
                </div>
            `;
        }
    });
    
    // Clear knowledge base button
    clearKnowledgeBtn.addEventListener('click', async () => {
        if (confirm('Are you sure you want to clear all knowledge base data? This cannot be undone.')) {
            try {
                const response = await fetch('/clear', {
                    method: 'POST'
                });
                
                const data = await response.json();
                
                if (data.success) {
                    fetchStats();
                    alert('Knowledge base cleared successfully.');
                } else {
                    alert(`Error: ${data.message}`);
                }
            } catch (error) {
                alert(`Error: ${error.message}`);
            }
        }
    });
    
    // Fetch and display knowledge base stats
    async function fetchStats() {
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
            } else {
                statsContent.innerHTML = `
                    <div class="alert alert-danger" role="alert">
                        <i class="fas fa-exclamation-circle me-2"></i>
                        ${data.message}
                    </div>
                `;
            }
        } catch (error) {
            statsContent.innerHTML = `
                <div class="alert alert-danger" role="alert">
                    <i class="fas fa-exclamation-circle me-2"></i>
                    Error loading stats: ${error.message}
                </div>
            `;
        }
    }
    
    // Display result message
    function showResult(element, message, isSuccess) {
        element.innerHTML = `
            <div class="alert alert-${isSuccess ? 'success' : 'danger'}" role="alert">
                <i class="fas fa-${isSuccess ? 'check-circle' : 'exclamation-circle'} me-2"></i>
                ${message}
            </div>
        `;
    }
    
    // Format answer with citation numbers
    function formatAnswer(answer, sources) {
        if (!sources || sources.length === 0) {
            return answer;
        }
        
        // Replace citation placeholders with clickable citation numbers
        sources.forEach((source, index) => {
            const citation = `<span class="citation" onclick="document.getElementById('source-${index + 1}').scrollIntoView({behavior: 'smooth'});">[${index + 1}]</span>`;
            const regex = new RegExp(`\\[${index + 1}\\]`, 'g');
            answer = answer.replace(regex, citation);
        });
        
        return answer;
    }
});
