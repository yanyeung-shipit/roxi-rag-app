import os
import logging
from app import app, db
from utils.background_processor import initialize_background_processor

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Create all database tables
with app.app_context():
    db.create_all()
    logger.info("Database tables created successfully!")
    
    # Initialize the background processor for vector store rebuilding
    from utils.vector_store import VectorStore
    vector_store = VectorStore()
    vector_stats = vector_store.get_stats()
    logger.info(f"Vector store initialized with {vector_stats.get('total_documents', 0)} documents")
    
    # Start the background processor
    initialize_background_processor()
    logger.info("Background document processor started")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
