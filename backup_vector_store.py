#!/usr/bin/env python
"""
Backup Vector Store

This script creates timestamped backups of the vector store files to prevent data loss.
It uses both a daily backup cycle and a separate versioned backup system.
"""

import os
import sys
import shutil
import logging
import time
from datetime import datetime

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
DAILY_BACKUP_DIR = os.path.join(BACKUP_DIR, 'daily')
VERSION_BACKUP_DIR = os.path.join(BACKUP_DIR, 'versions')
MAX_DAILY_BACKUPS = 7  # Keep one week of daily backups
MAX_VERSION_BACKUPS = 10  # Keep 10 version backups


def ensure_backup_dirs():
    """Create backup directories if they don't exist."""
    os.makedirs(DAILY_BACKUP_DIR, exist_ok=True)
    os.makedirs(VERSION_BACKUP_DIR, exist_ok=True)
    logger.info(f"Backup directories created/verified: {BACKUP_DIR}")


def get_timestamp():
    """Get the current timestamp in a sortable format."""
    return datetime.now().strftime('%Y%m%d%H%M%S')


def create_daily_backup():
    """Create a daily backup of vector store files."""
    today = datetime.now().strftime('%Y%m%d')
    backup_path_base = os.path.join(DAILY_BACKUP_DIR, today)
    
    # Check if we already have a backup for today
    if any(f.startswith(today) for f in os.listdir(DAILY_BACKUP_DIR)):
        logger.info(f"Daily backup for {today} already exists, skipping")
        return False
    
    success = True
    for file in VECTOR_FILES:
        if not os.path.exists(file):
            logger.warning(f"Vector store file {file} does not exist, skipping")
            success = False
            continue
        
        backup_path = f"{backup_path_base}_{file}"
        try:
            shutil.copy2(file, backup_path)
            logger.info(f"Created daily backup: {backup_path}")
        except Exception as e:
            logger.error(f"Failed to create daily backup for {file}: {e}")
            success = False
    
    return success


def create_version_backup():
    """Create a versioned backup of vector store files."""
    timestamp = get_timestamp()
    backup_path_base = os.path.join(VERSION_BACKUP_DIR, timestamp)
    
    success = True
    for file in VECTOR_FILES:
        if not os.path.exists(file):
            logger.warning(f"Vector store file {file} does not exist, skipping")
            success = False
            continue
        
        backup_path = f"{backup_path_base}_{file}"
        try:
            shutil.copy2(file, backup_path)
            logger.info(f"Created version backup: {backup_path}")
        except Exception as e:
            logger.error(f"Failed to create version backup for {file}: {e}")
            success = False
    
    return success


def clean_old_backups():
    """Remove old backups to save space."""
    # Clean old daily backups
    daily_backups = []
    for file in os.listdir(DAILY_BACKUP_DIR):
        # Group files by date part
        date_part = file.split('_')[0]
        if date_part not in [item[0] for item in daily_backups]:
            daily_backups.append((date_part, os.path.join(DAILY_BACKUP_DIR, file)))
    
    # Sort by date (newest first)
    daily_backups.sort(reverse=True)
    
    # Remove old daily backups
    for date_part, file_path in daily_backups[MAX_DAILY_BACKUPS:]:
        try:
            os.remove(file_path)
            logger.info(f"Removed old daily backup: {file_path}")
        except Exception as e:
            logger.error(f"Failed to remove old daily backup {file_path}: {e}")
    
    # Clean old version backups (more sophisticated approach for versions)
    version_files = {}
    for file in os.listdir(VERSION_BACKUP_DIR):
        timestamp = file.split('_')[0]
        if timestamp not in version_files:
            version_files[timestamp] = []
        version_files[timestamp].append(os.path.join(VERSION_BACKUP_DIR, file))
    
    # Sort timestamps (newest first)
    timestamps = sorted(version_files.keys(), reverse=True)
    
    # Remove old version backups
    for timestamp in timestamps[MAX_VERSION_BACKUPS:]:
        for file_path in version_files[timestamp]:
            try:
                os.remove(file_path)
                logger.info(f"Removed old version backup: {file_path}")
            except Exception as e:
                logger.error(f"Failed to remove old version backup {file_path}: {e}")


def check_and_backup():
    """Check and create backups if needed."""
    logger.info("Starting backup process")
    ensure_backup_dirs()
    
    # Create daily backup if needed
    daily_result = create_daily_backup()
    
    # Create version backup (at greater intervals than daily)
    version_result = create_version_backup()
    
    # Clean old backups
    clean_old_backups()
    
    logger.info("Backup process completed")
    return daily_result or version_result


if __name__ == "__main__":
    check_and_backup()