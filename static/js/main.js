document.addEventListener('DOMContentLoaded', () => {
    // Form elements
    const queryForm = document.getElementById('queryForm');
    
    // Results containers
    const answerContent = document.getElementById('answerContent');
    const sourcesList = document.getElementById('sourcesList');
    const sourcesHeader = document.getElementById('sourcesHeader');
    const answerSpinner = document.getElementById('answerSpinner');
    

    
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
