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
                        <div>Processing website... (this may take a minute or two)</div>
                    </div>
                    <div class="small mt-2">For sites like rheum.reviews, we carefully extract content while managing memory usage. Please be patient.</div>
                </div>
            `;
            
            const response = await fetch('/add_website', {
                method: 'POST',
                body: formData,
                // Add a longer timeout for larger websites
                signal: AbortSignal.timeout(300000) // 5-minute timeout 
            });
            
            // Check if the response is ok before parsing
            if (!response.ok) {
                if (response.status === 500) {
                    // Server error might be due to memory issues
                    throw new Error("The website processing failed, possibly due to the site being too large or complex. Try with a specific page URL instead of the homepage.");
                }
                const errorText = await response.text();
                throw new Error(`Server error: ${response.status} ${errorText.substring(0, 100)}`);
            }
            
            const data = await response.json();
            
            if (data.success) {
                showResult(websiteResult, `${data.message} (${data.chunks} chunks extracted)`, true);
                fetchStats();
            } else {
                if (data.message && data.message.includes("memory")) {
                    // Specific memory error message
                    showResult(websiteResult, `${data.message}. Try using a more specific URL instead of the homepage.`, false);
                } else {
                    showResult(websiteResult, data.message, false);
                }
            }
        } catch (error) {
            // Handle specific error types
            if (error.name === 'AbortError') {
                showResult(websiteResult, `Processing timed out. The website might be too large or complex. Try using a more specific URL instead of the homepage.`, false);
            } else if (error.message.includes('Unexpected token')) {
                showResult(websiteResult, `Error parsing server response. This often happens when the website is too large to process. Try using a more specific URL instead of the homepage.`, false);
            } else {
                showResult(websiteResult, `Error: ${error.message}`, false);
            }
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
                    
                    // Clear existing sources first
                    sourcesList.innerHTML = '';
                    
                    // Create a numbered list for sources
                    const sourceOlElement = document.createElement('ol');
                    sourceOlElement.className = 'source-list ps-3';
                    sourcesList.appendChild(sourceOlElement);
                    
                    data.sources.forEach((source, index) => {
                        const sourceItem = document.createElement('li');
                        sourceItem.className = 'source-item mb-2';
                        sourceItem.id = `source-${index + 1}`;
                        
                        // Get citation text - use APA citation if available, otherwise use default
                        let citationText = '';
                        
                        if (source.citation) {
                            // Use provided citation in APA format
                            citationText = source.citation;
                        } else if (source.source_type === 'pdf') {
                            // Fallback for PDF without citation
                            const title = source.title || "Unnamed PDF Document";
                            if (source.pages && source.pages.length > 0) {
                                // Use the pages array if available
                                const pageText = source.pages.length === 1 ? 'page' : 'pages';
                                citationText = `${title} (${pageText} ${source.pages.join(', ')})`;
                            } else {
                                // Fallback to single page if no pages array
                                const page = source.page || "unknown";
                                citationText = `${title} (page ${page})`;
                            }
                        } else {
                            // Fallback for website without citation
                            const title = source.title || "Unnamed Source";
                            const url = source.url || "#";
                            citationText = `${title}. Retrieved from ${url}`;
                        }
                        
                        // Get safe source title
                        const safeTitle = source.title || (source.source_type === 'pdf' ? 'PDF Document' : 'Website');
                        const sourceType = source.source_type || 'unknown';
                        
                        // Build and set the HTML
                        sourceItem.innerHTML = `
                            <div class="source-title">
                                <span class="badge bg-info me-2">${index + 1}</span>
                                ${sourceType === 'pdf' ? 
                                    `<i class="fas fa-file-pdf me-1"></i>` : 
                                    `<i class="fas fa-globe me-1"></i>`
                                }
                                ${safeTitle}
                            </div>
                            <div class="source-citation">${citationText}</div>
                        `;
                        
                        sourceOlElement.appendChild(sourceItem);
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
                // Create FormData to include clear_database parameter
                const formData = new FormData();
                formData.append('clear_database', 'true');
                
                const response = await fetch('/clear', {
                    method: 'POST',
                    body: formData
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
        
        // Remove any "Sources:" section that might appear at the end of the answer
        // This pattern matches "Sources:" followed by anything to the end of the string
        answer = answer.replace(/\s*Sources:[\s\S]*$/i, '');
        
        // Replace citation placeholders with clickable citation numbers
        sources.forEach((source, index) => {
            const citation = `<span class="citation" onclick="document.getElementById('source-${index + 1}').scrollIntoView({behavior: 'smooth'});">[${index + 1}]</span>`;
            const regex = new RegExp(`\\[${index + 1}\\]`, 'g');
            answer = answer.replace(regex, citation);
        });
        
        return answer;
    }
});
