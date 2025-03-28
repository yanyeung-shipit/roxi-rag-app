"""
This file contains the route to view PDF files directly in the browser.
To implement this in app.py, add the following code after the get_background_status function.
"""

@app.route('/view_pdf/<int:document_id>', methods=['GET'])
def view_pdf(document_id):
    """Serve the PDF file for direct viewing in the browser."""
    try:
        # Get the document from the database
        document = db.session.get(Document, document_id)
        
        if not document:
            logger.warning(f"Document with ID {document_id} not found")
            abort(404)
            
        # Check if it's a PDF and has a file path
        if document.file_type != "pdf" or not document.file_path:
            logger.warning(f"Document is not a PDF or has no file path: {document.file_path}")
            abort(400, description="Document is not a PDF or file is missing")
            
        # Verify file exists
        if not os.path.exists(document.file_path):
            logger.warning(f"PDF file not found on disk: {document.file_path}")
            abort(404, description="PDF file not found on disk")
            
        # Serve the file with the original filename
        return send_file(
            document.file_path,
            mimetype='application/pdf',
            as_attachment=False,
            download_name=document.filename
        )
        
    except Exception as e:
        logger.exception(f"Error serving PDF: {str(e)}")
        abort(500, description=f"Error serving PDF: {str(e)}")