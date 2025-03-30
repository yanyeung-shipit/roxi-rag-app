#!/usr/bin/env python
"""
Backup Vector Store

This script creates timestamped backups of the vector store files to prevent data loss.
It uses both a daily backup cycle and a separate versioned backup system.
"""

import os
import shutil
from datetime import datetime
import logging
import sys

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("backup_vector_store.log"),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)

# Configuration
VECTOR_FILES = ['document_data.pkl', 'faiss_index.bin']
BACKUP_DIR = './backups'
VERSION_BACKUP_DIR = os.path.join(BACKUP_DIR, 'versions')
DAILY_BACKUP_DIR = os.path.join(BACKUP_DIR, 'daily')
MAX_DAILY_BACKUPS = 7   # Keep at most 7 daily backups
MAX_VERSION_BACKUPS = 30  # Keep at most 30 version backups


def ensure_backup_dirs():
    """Create backup directories if they don't exist."""
    for directory in [BACKUP_DIR, VERSION_BACKUP_DIR, DAILY_BACKUP_DIR]:
        if not os.path.exists(directory):
            os.makedirs(directory, exist_ok=True)
            logger.info(f"Created backup directory: {directory}")


def get_timestamp():
    """Get the current timestamp in a sortable format."""
    return datetime.now().strftime('%Y%m%d%H%M%S')


def create_daily_backup():
    """Create a daily backup of vector store files."""
    # Use date only for daily backups
    date_str = datetime.now().strftime('%Y%m%d')
    
    success = True
    for file in VECTOR_FILES:
        if os.path.exists(file):
            dest = os.path.join(DAILY_BACKUP_DIR, f"{date_str}_{file}")
            try:
                shutil.copy2(file, dest)
                logger.info(f"Created daily backup: {dest}")
            except Exception as e:
                logger.error(f"Failed to create daily backup for {file}: {e}")
                success = False
        else:
            logger.warning(f"Source file {file} does not exist, skipping daily backup")
            success = False
    
    return success


def create_version_backup():
    """Create a versioned backup of vector store files."""
    timestamp = get_timestamp()
    
    success = True
    for file in VECTOR_FILES:
        if os.path.exists(file):
            dest = os.path.join(VERSION_BACKUP_DIR, f"{timestamp}_{file}")
            try:
                shutil.copy2(file, dest)
                logger.info(f"Created version backup: {dest}")
            except Exception as e:
                logger.error(f"Failed to create version backup for {file}: {e}")
                success = False
        else:
            logger.warning(f"Source file {file} does not exist, skipping version backup")
            success = False
    
    return success


def clean_old_backups():
    """Remove old backups to save space."""
    # Clean old daily backups
    try:
        # Get list of daily backups for document_data.pkl (as a reference)
        daily_backups = []
        for file in os.listdir(DAILY_BACKUP_DIR):
            if file.endswith(VECTOR_FILES[0]):  # document_data.pkl
                daily_backups.append(file)
        
        # Sort by date (first part of filename)
        daily_backups.sort()
        
        # Remove oldest backups if we have too many
        if len(daily_backups) > MAX_DAILY_BACKUPS:
            backups_to_remove = daily_backups[:-MAX_DAILY_BACKUPS]
            for old_backup in backups_to_remove:
                date_prefix = old_backup.split('_')[0]
                for file in VECTOR_FILES:
                    old_file = os.path.join(DAILY_BACKUP_DIR, f"{date_prefix}_{file}")
                    if os.path.exists(old_file):
                        os.remove(old_file)
                        logger.info(f"Removed old daily backup: {old_file}")
    except Exception as e:
        logger.error(f"Error cleaning old daily backups: {e}")

    # Clean old version backups
    try:
        # Get list of version backups for document_data.pkl (as a reference)
        version_backups = []
        for file in os.listdir(VERSION_BACKUP_DIR):
            if file.endswith(VECTOR_FILES[0]):  # document_data.pkl
                version_backups.append(file)
        
        # Sort by timestamp (first part of filename)
        version_backups.sort()
        
        # Remove oldest backups if we have too many
        if len(version_backups) > MAX_VERSION_BACKUPS:
            backups_to_remove = version_backups[:-MAX_VERSION_BACKUPS]
            for old_backup in backups_to_remove:
                timestamp_prefix = old_backup.split('_')[0]
                for file in VECTOR_FILES:
                    old_file = os.path.join(VERSION_BACKUP_DIR, f"{timestamp_prefix}_{file}")
                    if os.path.exists(old_file):
                        os.remove(old_file)
                        logger.info(f"Removed old version backup: {old_file}")
    except Exception as e:
        logger.error(f"Error cleaning old version backups: {e}")


def check_and_backup():
    """Check and create backups if needed."""
    ensure_backup_dirs()
    
    # Always create a version backup with timestamp
    version_success = create_version_backup()
    
    # Check if we need a daily backup (based on date in filename)
    create_daily = True
    date_str = datetime.now().strftime('%Y%m%d')
    
    # Check if today's daily backup already exists
    for file in os.listdir(DAILY_BACKUP_DIR):
        if file.startswith(date_str) and file.endswith(VECTOR_FILES[0]):
            create_daily = False
            break
    
    if create_daily:
        daily_success = create_daily_backup()
        logger.info(f"Daily backup created: {daily_success}")
    else:
        logger.info("Daily backup already exists for today, skipping")
    
    # Clean up old backups
    clean_old_backups()
    
    return version_success


if __name__ == "__main__":
    logger.info("Starting vector store backup process")
    result = check_and_backup()
    if result:
        logger.info("Backup completed successfully")
    else:
        logger.warning("Backup completed with some issues. Check the logs for details.")